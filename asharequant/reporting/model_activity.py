"""Read-only training evidence and separate trial/acceptance report panels."""
from html import escape as e
from pathlib import Path
import json
import math
import sqlite3
import pandas as pd
from ..core import now
from ..paper_account import digest, get
from .iteration_status import REASONS, SLOT_REASONS, percent, time_text


FEATURES = {'r1':'1日涨跌幅','r5':'5日涨跌幅','r20':'20日涨跌幅',
            'r60':'60日涨跌幅','vol20':'20日波动','vol60':'60日波动',
            'range20':'20日价格振幅','volume_ratio':'成交量变化','trend20':'20日价格趋势'}


def table(headers, rows, empty):
    rows=list(rows)
    if not rows:return '<p>'+e(empty)+'</p>'
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
        '<tr>'+''.join('<td>'+e(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def recipe_text(recipe):
    if not recipe:return '原记录未保存可核对的参数方案'
    features=recipe.get('features') or []
    names='、'.join(FEATURES.get(x,'未收录名称的特征') for x in features)
    return str(len(features))+'项输入（'+names+'）；拟合约束强度 '+str(recipe.get('alpha','未记录'))


def trained_rows(payload, specs):
    """Count saved final fits, not CV folds, searches, or inferred training caps."""
    day=payload['asof'];generated=pd.Timestamp(payload['generated_at'])
    if generated.tzinfo is None or generated>pd.Timestamp(now()):raise ValueError('UNVERIFIED_TIME')
    if str(pd.Timestamp(day).date())!=day or generated.tz_convert('Asia/Shanghai').date()<pd.Timestamp(day).date():
        raise ValueError('UNVERIFIED_DATE')
    spec=specs.get(payload.get('model'),{});rows={};seen=set();invalid=0
    for stock in payload.get('forecasts',[]):
        for h,f in stock.get('forecasts',{}).items():
            slot=str(stock['symbol'])+'/'+str(h)
            if slot in seen:raise ValueError('DUPLICATE_FIT')
            seen.add(slot)
            try:
                a=f['model_parameters'];n=len(a['coefficients'])
                assert h in ('1','5','20') and n>0
                assert len(a['means'])==len(a['scales'])==n
                assert all(math.isfinite(float(v)) for k in ('means','scales','coefficients') for v in a[k])
                assert math.isfinite(float(a['intercept'])) and all(float(v)>0 for v in a['scales'])
                label=f['final_training_last_label_end']
                assert str(pd.Timestamp(label).date())==label and label<=day
                assert math.isfinite(float(f['predicted_return'])) and f['forecast_target_date']>day
            except (KeyError,ValueError,TypeError,AssertionError):
                invalid+=1;continue
            upgrade=f.get('prediction_upgrade') or {}
            # Old records can resolve their recipe only against the saved matching version.
            recipe=upgrade.get('recipe') or spec.get('candidate') or {}
            if f.get('model_features'):recipe={**recipe,'features':f['model_features']}
            if len(recipe.get('features',[]))!=n:recipe={}
            trial=bool(upgrade.get('experiment') and upgrade.get('slot')==slot and upgrade.get('scope')=='RESEARCH_TRIAL_ONLY')
            rows[slot]=dict(slot=slot,name=stock.get('name',stock['symbol']),horizon=h,
                features=n,recipe=recipe,last_label=label,trial=trial,
                experiment=upgrade.get('experiment'),scope=upgrade.get('scope'),date=day)
    return dict(date=day,generated_at=payload['generated_at'],rows=rows,invalid=invalid,
                minimum=payload.get('config',{}).get('minimum_train'),cap=payload.get('config',{}).get('training_cap'))


def collect(root, session):
    """No registry calls, schema creation, model fitting, or ledger writes."""
    root=Path(root);path=root/'data/research_paper.sqlite3'
    result=dict(days=[],active=None,issues=[])
    predictions={};specs={}
    if not path.is_file():
        result['issues'].append('尚无封存训练记录，不能确认每日训练是否完成。')
    else:
        try:
            with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                predictions=get(db,'predictions')
                specs={s['version']:s for kind in ('spec','spec_revisions') for s in get(db,kind).values()}
        except (sqlite3.Error,ValueError,KeyError,TypeError):
            predictions={};result['issues'].append('训练记录读取或完整性核对失败，暂不宣称训练完成。')
    verified={}
    for key,payload in sorted(predictions.items()):
        try:
            if key!=payload['asof']:raise ValueError('DATE_MISMATCH')
            if key>session:continue
            day=trained_rows(payload,specs);result['days'].append(day);verified[digest(payload)]=day
        except (KeyError,TypeError,ValueError):
            result['issues'].append('一条封存预测的日期或内容无法核对，未计入已训练数量。')
    folder=root/'data/dynamic/model_inputs';independent={}
    for path in sorted((folder/'versions').glob('*.json')):
        try:
            bundle=json.loads(path.read_text())
            if digest(bundle)!=path.stem or pd.Timestamp(bundle['available_at'])>pd.Timestamp(now()):raise ValueError('UNVERIFIED_INPUT')
            payload=bundle['predictions']
            if payload['asof']>session:continue
            spec=bundle['spec'];day=trained_rows(payload,{spec['version']:spec})
            independent[path.stem]=day;verified[digest(payload)]=day
        except (OSError,ValueError,KeyError,TypeError):
            result['issues'].append('一条独立模型输入未通过完整性或时间核验，未计入训练。')
    result['days']=sorted({day['date']:day for day in sorted(verified.values(),key=lambda d:d['generated_at'])}.values(),key=lambda d:d['date'])
    if independent:
        result['issues']=[message for message in result['issues'] if message!='尚无封存训练记录，不能确认每日训练是否完成。']
    try:
        from ..dynamic_service import enabled
        if folder.exists() or enabled(root):
            pointer=json.loads((folder/'latest.json').read_text())
            result['active']=independent.get(pointer['sha256'])
        else:
            payload=json.loads((root/'reports/active_research/latest/report.json').read_text())['predictions']
            result['active']=verified.get(digest(payload))
        if result['active'] is None:raise ValueError('UNVERIFIED_ACTIVE_SOURCE')
    except (OSError,ValueError,KeyError,TypeError):
        result['issues'].append('盘中服务来源文件缺失或无法与封存预测对应，不能确认其采用的方案。')
    return result


def training_panel(data,session):
    days=data['days'];latest=days[-1] if days else None
    today=next((d for d in days if d['date']==session),None)
    text='<h2>每日训练：模型每天学了什么</h2>'
    text+='<p>训练用已有、已到期的历史行情重新计算输入的标准化参数、各项特征权重和截距，生成1／5／20交易日预测。独立验收还在等待，不表示没有训练。</p>'
    text+='<p>这里只统计已封存预测中可核对的最终拟合结果，不把候选搜索次数、回测分段数或报告刷新次数算成训练完成次数。</p>'
    if today:
        text+='<p class="callout"><strong>'+e(session)+'：已保存 '+str(len(today['rows']))+' 组最终拟合与预测。</strong> 生成于 '+e(time_text(today['generated_at']))+'。</p>'
    else:text+='<p class="callout">本页数据日 '+e(session)+' 尚无可核对的封存训练结果；以下展示最近记录，不能当作今日已完成。</p>'
    for issue in data['issues']:text+='<p class="bad">'+e(issue)+'</p>'
    for day in reversed(days):
        rows=list(day['rows'].values());stocks=len({r['slot'].split('/')[0] for r in rows})
        features='／'.join(map(str,sorted({r['features'] for r in rows}))) or '未确认'
        text+='<details'+(' open' if day is latest else '')+'><summary>'+e(day['date'])+' · '+str(stocks)+'只股票 · '+str(len(rows))+'组最终拟合 · '+features+'项输入</summary>'
        text+='<p>保存时间：'+e(time_text(day['generated_at']))+'。本次更新：输入均值与尺度、预测权重、截距及三期限预测；每组实际输入与标签截止日见下表。</p>'
        text+='<p>当时配置的训练样本下限：'+e(str(day['minimum'] or '未记录'))+'；上限：'+e(str(day['cap'] or '未记录'))+'。这是历史样本限制，不是从现在起等待的天数。原记录未保存最终训练样本数及开始日期，不以配置上限冒充实际数量。</p>'
        if day['invalid']:text+='<p class="bad">另有 '+str(day['invalid'])+' 组缺少完整的拟合参数或时间证据，未计入完成数量。</p>'
        text+=table(['股票／期限','训练内容（输入与参数方案）','训练实际结果最晚日期','预测所用方案'],
            ([r['name']+' '+r['slot'].split('/')[0]+' / '+r['horizon']+'日',recipe_text(r['recipe']),r['last_label'],
              '研究试用方案' if r['trial'] else '独立验收后的预测方案' if r['scope']=='PREDICTION_RECIPE_ONLY' else '原研究方案'] for r in rows),
            '本次尚无完整、可核对的最终训练结果。')+'</details>'
    if not days:text+='<p>取得可靠历史数据并完成日常预测后，这里会按数据日列出训练内容。</p>'
    return text


def trial_panel(data,report):
    p=report.get('research_progress',{});last=p.get('last_slot_study') or {}
    studies=last.get('studies',report.get('slot_studies',[]))
    latest=data['days'][-1] if data['days'] else None;active=data['active']
    eligible=set(report.get('research_trial_slots',[]))
    trained={k:r for k,r in (latest or {}).get('rows',{}).items() if r['trial']}
    loaded={k:r for k,r in (active or {}).get('rows',{}).items() if r['trial']}
    text='<h2>研究试用：获准与实际采用分别记录</h2>'
    text+='<p>当前可研究试用 '+str(len(eligible))+' 组；最近封存预测实际采用试用方案 '+str(len(trained))+' 组；盘中来源文件采用试用方案 '+str(len(loaded))+' 组。</p>'
    if latest:text+='<p>最近封存预测数据日：'+e(latest['date'])+'；保存时间：'+e(time_text(latest['generated_at']))+'。</p>'
    if active:text+='<p>盘中服务当前来源文件的预测数据日：'+e(active['date'])+'。这是服务读取的模型来源；不代表此刻已经成功推理或成交。</p>'
    if latest and active and latest['date']!=active['date']:text+='<p class="callout">两个来源日期不同。盘中使用上一个完整交易日的模型；收盘后新训练完成不等于盘中来源文件立即切换。下一交易日仍须通过原时效检查，过期会暂停相关推理。</p>'
    if eligible and not trained:text+='<p class="callout">已有方案获准，但最近封存预测尚未采用这些试用方案。等待下一次未封存的完整预测；不重写今天及历史预测来制造“已试用”。</p>'
    names={r['slot']:r.get('name',r['slot'].split('/')[0]) for r in report.get('slot_progress',[])}
    union=sorted(eligible|set(trained)|set(loaded))
    text+=table(['股票／期限','当前研究资格','最近封存预测','盘中来源文件'],
        ([names.get(s,(trained.get(s) or loaded.get(s) or {}).get('name',s.split('/')[0]))+' '+s.replace('/',' / ')+'日',
          '获准研究试用' if s in eligible else '本次资格列表未列入，需核对研究进度',
          '已采用试用方案' if s in trained else '未见采用记录' if latest else '来源未确认',
          '已采用试用方案' if s in loaded else '未见采用记录' if active else '来源未确认'] for s in union),
        '目前没有可确认的研究试用方案，继续查看原方案的训练记录。')
    text+='<h3>每天研究检查什么</h3><p>每只股票的1／5／20日分别比较已有特征组合和拟合约束强度；根据历史预测与实际结果检查误差、方向表现及稳定性。不再要求统一改善2%。待独立验证的方案保持固定，但每日仍用原算法重新拟合权重。</p>'
    text+='<p><strong>本次状态／等待原因：</strong>'+e(REASONS.get(p.get('status'),'尚无完整研究状态，等待记录。'))+'</p>'
    text+='<p>下一次日常研究：'+e(time_text(p.get('next_review_at')))+'；须有新增到期结果且数据可靠。18:00是启动时间，同一数据日不重复搜索。</p>'
    text+='<h3>上次完成的分组研究</h3><p>数据日 '+e(str(last.get('asof',report.get('asof','未记录'))))+'；完成时间 '+e(time_text(last.get('generated_at',report.get('generated_at'))))+'。</p>'
    comparison=[]
    for row in studies:
        best=row.get('winner') or max(row.get('comparisons',[]),key=lambda x:x.get('mean_gain',float('-inf')),default={})
        if not best:conclusion='缺少可比较结果'
        elif row.get('winner'):conclusion='通过历史试用检查；仍需独立验收'
        else:
            reasons=[]
            if best.get('mean_gain',0)<=0:reasons.append('总体误差未减少')
            if best.get('recent_gain',0)<=0:reasons.append('近期误差未减少')
            if best.get('minimum_positive_folds',0)<3:reasons.append('改善不足3/4段')
            if best.get('recent_direction',0)<best.get('champion_recent_direction',0):reasons.append('近期方向表现退步')
            conclusion='；'.join(reasons) or '与当前方案相同，保持原方案'
        comparison.append([row.get('name','')+' '+row['slot']+'日',row.get('candidate_count','未记录'),
                           percent(best.get('mean_gain')),percent(best.get('recent_gain')),conclusion])
    text+='<details><summary>展开各股票／期限的候选比较结果</summary>'+table(
        ['股票／期限','比较数','平均误差改善','近期误差改善','结果'],comparison,
        '本次没有新的可搜索组，等待原因见上方；这不表示日常训练停止。')+'</details>'
    return text


def acceptance_panel(report):
    text='<h2>独立验收：检验新方案是否可靠</h2>'
    text+='<p>独立预测验证通过 '+str(len(report.get('accepted_slots',[])))+' 组。验证等待与每日训练、研究试用并行，不必等全部验收后才训练。</p>'
    text+='<p>先固定特征和参数方案，再记录之后实际发生的预测与结果。首次验收需1日预测60个起点、5日预测90个起点、20日预测253个起点，并等待末条预测到期。数字表示验证证据要求，不是训练所需等待时间。重复试验可能需要更多证据。</p>'
    rows=[]
    for r in report.get('slot_progress',[]):
        status=r.get('status');metrics=r.get('metrics',{})
        state={'WAITING':'独立验收进行中','ACCEPTED':'独立预测验证通过','REJECTED':'本次未通过','ERROR':'检查异常，暂停推进'}.get(status,'尚待核对')
        due=r.get('earliest',r.get('first_evaluation_at'))
        reason='；'.join(SLOT_REASONS.get(b,'其他验收检查未通过') for b in metrics.get('blockers',[])) or ('尚未验收，不提前查看测试误差来调参。' if status=='WAITING' else '只涉及预测方案，交易资格另行检查。')
        rows.append([r.get('name','')+' '+r['slot']+'日',state,str(r.get('confirmed',metrics.get('observations','未记录')))+' / '+str(r.get('required','已完成')),
                     time_text(due) if due else '后续交易日历尚未齐全，暂不能确定日期',reason])
    text+=table(['股票／期限','状态','已到期／所需起点','最早独立验收时间','说明'],rows,
                '目前没有待验收方案；原模型的每日训练与预测仍按原流程进行。')
    if report.get('errors'):text+='<p class="bad">存在 '+str(len(report['errors']))+' 项数据或流程问题，相关组暂停推进，原始记录保留。</p>'
    return text+'<p>历史改善不等于独立验证通过，预测改善不等于交易盈利。原算法、仓位、费用和风险参数保持不变；试用仅用于研究模拟。</p>'


def render(root, report, session):
    data=collect(root,session)
    return '''<style>.model-activity{max-width:1300px;margin:auto}.model-tabs{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.model-tabs label{cursor:pointer;padding:12px 18px;border:1px solid #c5d4df;border-radius:8px;color:#174665;background:#f1f6fa}.model-choice{position:absolute;opacity:0}.model-panels>section{display:none}#model-training:checked~.model-panels #training,#model-trial:checked~.model-panels #trial,#model-acceptance:checked~.model-panels #acceptance{display:block}#model-training:checked~nav label[for=model-training],#model-trial:checked~nav label[for=model-trial],#model-acceptance:checked~nav label[for=model-acceptance]{background:#174665;color:white}.model-choice:focus-visible~nav{outline:2px solid #267ca2}.model-activity .scroll{overflow:auto;max-height:65vh}.model-activity thead{position:sticky;top:0;background:#edf3f7}.model-activity table{border-collapse:collapse;width:100%}.model-activity td,.model-activity th{padding:10px;border-bottom:1px solid #dce4ea;text-align:left;vertical-align:top}.model-activity details{margin:18px 0;padding:12px;background:#f8fafc;border:1px solid #e0e8ed;border-radius:8px}.model-activity summary{cursor:pointer;font-weight:bold}.model-activity .callout{padding:14px;background:#edf5fa;border-left:4px solid #4484aa}.model-activity .bad{color:#9b3e18}</style>
<div class="model-activity"><h1>模型训练与验证</h1><p>每日训练、研究试用、独立验收分别查看；等待验收不会让训练停下来。</p>'''+ '<p>本页数据日：'+e(session)+'；研究记录数据日：'+e(str(report.get('asof','未记录')))+'</p>'+(''
        if report.get('asof')==session else '<p class="bad">研究记录尚未更新到本页数据日，研究资格及验收表为上次结果。</p>')+'''
<input class="model-choice" type="radio" name="model-view" id="model-training" checked aria-label="每日训练">
<input class="model-choice" type="radio" name="model-view" id="model-trial" aria-label="研究试用">
<input class="model-choice" type="radio" name="model-view" id="model-acceptance" aria-label="独立验收">
<nav class="model-tabs" aria-label="模型栏目"><label for="model-training">01 每日训练</label><label for="model-trial">02 研究试用</label><label for="model-acceptance">03 独立验收</label></nav>
<div class="model-panels"><section id="training">'''+training_panel(data,session)+'</section><section id="trial">'+trial_panel(data,report)+'</section><section id="acceptance">'+acceptance_panel(report)+'</section></div></div>'


def document(root,report,session):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>模型训练与验证</title><style>body{font:16px/1.65 system-ui;color:#172b41;margin:0;padding:24px;background:white}h1{font-size:28px}h2{font-size:23px}</style><body>'+render(root,report,session)+'</body></html>'
