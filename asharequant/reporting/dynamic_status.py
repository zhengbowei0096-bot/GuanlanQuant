"""Read-only diagnosis of recorded intraday inference, separate from service health.

An idle service or a code deployment is never proof of inference recovery.
Only checksum-verified, complete recorded decisions can supply that evidence.
"""
import datetime as dt
import html
import json
import math
import sqlite3
from zoneinfo import ZoneInfo

from ..paper_account import digest
from .plain_chinese import translate

TZ = ZoneInfo('Asia/Shanghai')


def timestamp(value):
    t = dt.datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError('missing timezone')
    return t.astimezone(TZ)


def display_time(value):
    return timestamp(value).strftime('%Y-%m-%d %H:%M:%S') + '（北京时间）' if value else '尚无记录'


def explanation(reason, universe):
    code, _, symbol = str(reason or '').partition(':')
    text = translate(code)
    if text == code:
        text = '运行记录出现尚未归类的异常，需检查原始诊断记录'
    if symbol in universe:
        text += '：' + universe[symbol] + '（' + symbol + '）'
    return text


def problem(at, result, universe, checked_at):
    if not isinstance(result, dict):
        raise ValueError('invalid result structure')
    if timestamp(at) > timestamp(checked_at):
        return 'DECISION_TIME_INVALID'
    if result.get('reason'):
        return str(result['reason'])
    if result.get('inference_status') == 'UNAVAILABLE_RISK_REDUCTIONS_ONLY':
        return 'UNAVAILABLE_RISK_REDUCTIONS_ONLY'
    rows = result.get('decision_rows', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('invalid decision structure')
    if not rows:
        return 'NO_RECORDED_DECISIONS'
    symbols = [r['symbol'] for r in rows]
    if len(symbols) != len(universe) or set(symbols) != set(universe):
        return 'DECISION_COVERAGE_INCOMPLETE'
    model = result.get('model') or {}
    if not isinstance(model, dict):
        raise ValueError('invalid model structure')
    if set(model.get('stocks', {})) != set(universe):
        return 'MODEL_EVIDENCE_INCOMPLETE'
    model_at = timestamp(model['at'])
    end = timestamp(at)
    if model_at > end or model_at.date() != end.date():
        return 'DECISION_TIME_INVALID'
    for row in rows:
        quote_at = timestamp(row['quote_time'])
        if quote_at > end or quote_at.date() != end.date():
            return 'DECISION_TIME_INVALID'
        if not math.isfinite(row['target_weight']):
            return 'MODEL_EVIDENCE_INCOMPLETE'
    return None


def snapshot(db, universe, checked_at, service_status):
    """SELECT only; neither records nor current_state may be changed here.

    Inspect compact result projections, then verify each selected full record's
    checksum. Stop once the latest success and failure are known. This preserves
    the last failure through closed sessions without using old rows as new ones.
    """
    info = dict(state='WAITING', service_status=service_status,
                latest_attempt_at=None, last_success_at=None, last_failure_at=None,
                recovered_at=None, reason=None, last_failure_reason=None,
                expected_stocks=len(universe), decision_stocks=0,
                quote_problems=[], source_errors=[], rows=[], model_at=None, last_decision_at=None)
    selected = {}
    latest = failure = success = None
    first_success = None
    try:
        query = """SELECT key,json_extract(body,'$.at'),json_extract(body,'$.result')
                   FROM records WHERE kind='cycles' ORDER BY CAST(key AS INTEGER) DESC"""
        for key, at, raw in db.execute(query):
            result = json.loads(raw)
            cause = problem(at, result, universe, checked_at)
            item = (key, at, result, cause)
            if latest is None:
                latest = item;selected[key] = item
            if cause and failure is None:
                failure = item;selected[key] = item
            if not cause:
                if success is None:
                    success = item;selected[key] = item
                if failure is None:
                    first_success = item
            if failure and success:
                break
        if first_success:
            selected[first_success[0]] = first_success
        for key, at, result, _ in selected.values():
            raw, checksum = db.execute("SELECT body,sha256 FROM records WHERE kind='cycles' AND key=?", (key,)).fetchone()
            record = json.loads(raw)
            if digest(record) != checksum or record['at'] != at or record['result'] != result:
                raise ValueError('cycle integrity failed')
        if latest is None:
            return info
        key, at, result, cause = latest
        info.update(latest_attempt_at=at, reason=cause,
                    decision_stocks=len({r['symbol'] for r in result.get('decision_rows', [])}))
        record = json.loads(db.execute("SELECT body FROM records WHERE kind='cycles' AND key=?", (key,)).fetchone()[0])
        info['source_errors']=result.get('source_errors',[])
        info['quote_problems'] = [dict(symbol=k, name=universe.get(k,k),
                                     reasons=[explanation(x, universe) for x in dict.fromkeys(reasons)])
                                  for k, reasons in record.get('checks', {}).items() if reasons]
        if failure:
            info.update(last_failure_at=failure[1], last_failure_reason=failure[3])
        if success:
            info['last_success_at'] = success[1]
        if cause:
            info['state'] = 'BLOCKED'
        else:
            info.update(state='RECOVERED' if failure else 'AVAILABLE',
                        recovered_at=first_success[1] if failure and first_success else None,
                        rows=result['decision_rows'], model_at=result['model']['at'], last_decision_at=at)
        return info
    except (ValueError, TypeError, KeyError, IndexError, sqlite3.DatabaseError):
        # An unreadable or tampered record cannot substantiate recovery.
        return dict(info, state='EVIDENCE_UNVERIFIED', reason='DECISION_EVIDENCE_UNVERIFIED',
                    rows=[], last_decision_at=None, last_success_at=None, recovered_at=None)


def render(info, universe, positions):
    e = lambda x: html.escape(str(x))
    state = info['state']
    labels = {'WAITING':'尚无盘中判断记录', 'BLOCKED':'动态判断受阻，尚未验证恢复',
              'EVIDENCE_UNVERIFIED':'诊断证据无法核验，恢复状态未知',
              'RECOVERED':'最近盘中记录已验证动态判断恢复', 'AVAILABLE':'最近盘中记录已生成完整动态判断'}
    page = '<section id="dynamic-decision-status"><h2>最近动态判断与原排名</h2>'
    page += '<p><strong>' + labels[state] + '</strong></p>'
    page += '<p>服务状态：' + e(translate(info['service_status'])) + '。休市、重启或安装修复不会自动标记动态判断恢复；以下状态以保存的盘中记录为准。</p>'
    page += '<p>最近盘中尝试：' + e(display_time(info['latest_attempt_at'])) + '；判断明细覆盖：' + str(info['decision_stocks']) + ' / ' + str(info['expected_stocks']) + '只。</p>'
    if info.get('reason'):
        page += '<p>本次受阻原因：' + e(explanation(info['reason'], universe)) + '。</p>'
    if info.get('last_failure_at'):
        page += '<p>最近异常：' + e(display_time(info['last_failure_at'])) + '；' + e(explanation(info['last_failure_reason'], universe)) + '。</p>'
    page += '<p>最近成功判断：' + e(display_time(info['last_success_at'])) + '；恢复确认：' + (e(display_time(info['recovered_at'])) if info['recovered_at'] else '尚无异常后的有效盘中恢复记录') + '。</p>'
    if state in ('WAITING', 'BLOCKED', 'EVIDENCE_UNVERIFIED'):
        page += '<p>当前没有可展示的完整动态判断，因此不展示空表，也不沿用旧预测冒充本轮结果。需在后续交易时段取得有效行情并完成全池模型计算后再确认恢复。独立风控减仓与估值另行受行情、账户和交易条件约束；不能据此认定模型推理正常。</p>'
    else:
        page += '<p>以下是保存的最近一次完整判断，记录时间：' + e(display_time(info['last_decision_at'])) + '；模型计算时间：' + e(display_time(info['model_at'])) + '。请核对日期，休市时不会产生新的盘中预测。当前股数来自本页账户状态；没有成交也可能是正常判断结果。</p>'
        page += '<div class="scroll"><table><tr><th>股票</th><th>原始排名</th><th>当前股数</th><th>动态目标</th><th>预测净收益</th><th>报价时间</th><th>依据</th></tr>'
        for row in info['rows']:
            net = row.get('net_expected_return')
            values = [row.get('name',universe[row['symbol']]), row.get('original_rank','未提供'),
                      positions.get(row['symbol'],{}).get('shares',0), f"{row['target_weight']:.2%}",
                      f'{net:.2%}' if isinstance(net,(int,float)) and math.isfinite(net) else '未提供',
                      display_time(row['quote_time']), '；'.join(translate(x) for x in row.get('reasons',[])) or '本轮未附加说明']
            page += '<tr>' + ''.join('<td>'+e(x)+'</td>' for x in values) + '</tr>'
        page += '</table></div>'
    if info['quote_problems']:
        page += '<details><summary>最近一轮行情检查问题（' + str(len(info['quote_problems'])) + '只）</summary><ul>'
        page += ''.join('<li>'+e(p['name']+'（'+p['symbol']+'）：'+'；'.join(p['reasons']))+'</li>' for p in info['quote_problems']) + '</ul></details>'
    if info.get('source_errors'):
        labels={'ReadTimeout':'读取超时','ConnectTimeout':'连接超时','TimeoutError':'请求超时','ConnectionError':'网络连接失败','QUOTE_INVALID':'行情字段缺失或无效','REFERENCE_INVALID':'交易参考资料为空或无法解析'}
        page+='<p>本轮数据请求异常：'+'；'.join(e(str(x.get('source','数据源')))+'：'+e(labels.get(x.get('error'),'数据请求或解析失败')) for x in info['source_errors'])+'。下一轮按原周期重新请求，通过原时效检查后才可使用；不会以旧数据代替。</p>'
    return page + '<p>这里的恢复仅指动态研究判断恢复，不表示独立模型验收通过，也不表示已成交。</p></section>'
