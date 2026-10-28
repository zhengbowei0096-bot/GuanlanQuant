"""Quote-driven paper service, isolated from broker and immutable legacy ledgers."""
from pathlib import Path
import copy
import hashlib
import html
import json
import math
import re
import sqlite3
import sys
import time
import pandas as pd
from .core import now, run_lock, write_json, atomic_text
from .paper_account import get, put, digest, evidence
from .intraday import load_state, save_state, session
from .intraday_data import collect, quality, days
from .intraday_events import snapshot
from .adaptive_policy import adjust
from .order_engine import seed, step, cancel_all, ACTIVE
from .intraday_inference import dynamic_plan, observed_bar

DEFAULTS=dict(enabled=False,mode='PAPER_ONLY',real_orders_enabled=False,refresh_seconds=30,
              model_refresh_seconds=60,decision_cooldown_seconds=300,order_ttl_seconds=120,
              minimum_latency_seconds=1,maximum_quote_jump=.05)


def enabled(root):
    p=Path(root)/'dynamic_config.json'
    return p.exists() and json.loads(p.read_text()).get('enabled') is True


def config(root):
    c={**DEFAULTS,**json.loads((root/'dynamic_config.json').read_text())}
    if c['mode']!='PAPER_ONLY' or c['real_orders_enabled'] or c['refresh_seconds']!=30:raise ValueError('ONLY_PAPER_AUTHORIZED')
    if not 30<=c['model_refresh_seconds']<=300 or not 60<=c['decision_cooldown_seconds'] or not 1<=c['minimum_latency_seconds']<c['order_ttl_seconds']<=300 or not 0<c['maximum_quote_jump']<=.05:raise ValueError('INVALID_EXECUTION_CONFIG')
    from .intraday import configuration
    return configuration(root)|c


def db_open(root):
    path=Path(root)/'data/dynamic/account.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=20);path.chmod(0o600)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,key TEXT,body TEXT,sha256 TEXT,PRIMARY KEY(kind,key))')
    db.execute('CREATE TABLE IF NOT EXISTS current_state(id INTEGER PRIMARY KEY,body TEXT NOT NULL)');db.commit()
    return db


def persist(db,s):
    # Keep immutable execution/event evidence in addition to the current projection.
    for fill in s['executions']:put(db,'fills',fill['id'],fill)
    for item in s['order_events']:put(db,'order_events',digest(item),item)
    revision=db.execute("SELECT COUNT(*) FROM records WHERE kind='state_versions'").fetchone()[0]+1
    put(db,'state_versions',f'{revision:012d}',dict(state_sha=digest(s)))
    save_state(db,s)


def verify_projection(db,s):
    row=db.execute("SELECT body,sha256 FROM records WHERE kind='state_versions' ORDER BY key DESC LIMIT 1").fetchone()
    if row:
        proof=json.loads(row[0])
        if digest(proof)!=row[1] or proof['state_sha']!=digest(s):raise ValueError('LEDGER_PROJECTION_TAMPERED')


def code_fingerprints():
    # Include the shared lot conversion used by both proposal and fill checks.
    return {n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest()
            for n in ('order_engine.py','intraday_inference.py','dynamic_service.py','intraday.py','dynamic_inputs.py','intraday_data.py')}


def reviewed_code(db, meta):
    code = meta['code']
    for revision, review in sorted(get(db, 'execution_upgrades').items()):
        if (review['from_code'] != code
                or review['monitor_config_sha'] != digest(meta['monitor_config'])
                or review['risk_config_sha'] != digest(meta['config'])):
            raise ValueError('EXECUTION_UPGRADE_CHAIN_INVALID')
        code = review['to_code']
    return code


def approve_upgrade(root, expected_code, validation_sha, reason, recover_failed_open=False):
    """Explicit, audited maintenance only. Never rewrite meta, state or fills.

    Caller must have reviewed the exact old/new code and completed verification.
    The ordinary poll path cannot authorize an upgrade by itself.
    """
    if not reason.strip() or not re.fullmatch(r'[a-f0-9]{64}', validation_sha):
        raise ValueError('EXECUTION_UPGRADE_REVIEW_REQUIRED')
    root = Path(root)
    with run_lock(root/'logs/dynamic'):
        at = pd.Timestamp(now())
        cal=days(root);market_session=session(at,cal)
        if market_session != 'CLOSED' and not recover_failed_open:
            raise ValueError('EXECUTION_UPGRADE_REQUIRES_CLOSED_SESSION')
        with db_open(root) as db:
            db.execute('BEGIN IMMEDIATE')
            meta = get(db, 'meta')['account'];state = load_state(db)
            verify_projection(db, state)
            if meta['monitor_config'] != config(root):
                raise ValueError('EXECUTION_UPGRADE_CONFIG_CHANGED')
            if state['day'] != state['closed_day'] or any(o['status'] in ACTIVE for o in state['orders'].values()):
                raise ValueError('EXECUTION_UPGRADE_REQUIRES_SETTLED_ACCOUNT')
            if market_session!='CLOSED':
                prior=cal[cal<pd.Timestamp(str(at.date()))]
                last=state.get('last_cycle_at')
                # Explicit operator recovery only: today's engine has never
                # advanced beyond yesterday's settlement. No live order can be
                # interrupted and no completed trading cycle can be rewritten.
                if (market_session!='CONTINUOUS' or not len(prior) or state['closed_day']!=str(prior[-1].date())
                        or (last and pd.Timestamp(last).tz_convert('Asia/Shanghai').date()>=at.date())
                        or any(pd.Timestamp(f['at']).tz_convert('Asia/Shanghai').date()>=at.date() for f in state['executions'])):
                    raise ValueError('EXECUTION_RECOVERY_REQUIRES_NO_CURRENT_SESSION_ACTIVITY')
            previous = reviewed_code(db, meta);current = code_fingerprints()
            if previous != expected_code:
                raise ValueError('EXECUTION_UPGRADE_BASE_MISMATCH')
            if previous == current:
                return {'status':'ALREADY_REVIEWED'}
            revision = f"{len(get(db, 'execution_upgrades')) + 1:012d}"
            review = dict(at=at.isoformat(), from_code=previous, to_code=current,
                          monitor_config_sha=digest(meta['monitor_config']),
                          risk_config_sha=digest(meta['config']), state_sha=digest(state),
                          validation_sha=validation_sha, reason=reason,
                          maintenance_mode='FAILED_OPEN_RECOVERY' if market_session!='CLOSED' else 'CLOSED_SESSION')
            put(db, 'execution_upgrades', revision, review)
            return {'status':'UPGRADE_REVIEW_RECORDED','revision':revision,'review_sha':digest(review)}


def initialize(root,db,at):
    cfg=config(root);meta=get(db,'meta').get('account')
    code=code_fingerprints()
    if meta is None:
        with sqlite3.connect('file:'+str(root/'data/adaptive/account.sqlite3')+'?mode=ro',uri=True) as old:
            old.execute('BEGIN');base=get(old,'meta')['account'];previous=load_state(old)
        if previous['day']!=previous['closed_day'] or previous['valuation_status'] not in ('ANCHOR_SNAPSHOT','VERIFIED_CLOSE'):raise ValueError('MIGRATION_REQUIRES_SETTLED_ANCHOR')
        s=seed(previous,at)
        meta=dict(created_at=at.isoformat(),mode='PAPER_ONLY',config=base['config'],adaptive_config=base['adaptive_config'],monitor_config=cfg,code=code,universe=base['universe'],anchor=previous['closed_day'],initial_equity=s['equity'],prior_account_sha=digest(previous),prior_account='adaptive',basis_note='迁移时按已核验账面估值建立本阶段成本基准，不冒充真实买入成本；历史收益保留在原账本，不相加')
        put(db,'migration','anchor',dict(meta=base,state=previous));put(db,'meta','account',meta);persist(db,s)
    if reviewed_code(db,meta)!=code or meta['monitor_config']!=cfg:raise ValueError('EXECUTION_VERSION_CHANGED_REVIEW_REQUIRED')
    s=load_state(db);verify_projection(db,s)
    return meta,s


def source(root,at,cal):
    from .dynamic_inputs import load
    day=pd.Timestamp(str(at.date()));prior=cal[cal<day][-1]
    return load(root,at,str(prior.date()))


def day_counters(s,day):
    fills=[f for f in s['executions'] if str(pd.Timestamp(f['at']).tz_convert('Asia/Shanghai').date())==day]
    return dict(fees=sum(f['fee'] for f in fills),turnover=sum(f['shares']*f['price'] for f in fills))


def reconcile_counters(db,s,at):
    """Correct only a verified current projection, with append-only evidence."""
    recorded=get(db,'fills')
    if {f['id']:f for f in s['executions']}!=recorded:
        raise ValueError('DAILY_COUNTER_FILL_EVIDENCE_MISMATCH')
    expected=day_counters(s,s['day'])
    if any(abs(s[k]-v)>1e-8 for k,v in expected.items()):
        before=digest(s);old={k:s[k] for k in expected};s.update(expected)
        correction=dict(at=at.isoformat(),day=s['day'],reason='RECONCILE_DAILY_COUNTERS_FROM_CONFIRMED_PAPER_FILLS',
                        old=old,new=expected,before=before,after=digest(s),fills_sha=digest(recorded))
        put(db,'counter_corrections',digest(correction),correction);persist(db,s)
    return s


def cycle(root):
    root=Path(root)
    if not enabled(root):return {'status':'DISABLED'}
    with run_lock(root/'logs/dynamic'):
        at=pd.Timestamp(now());cal=days(root);mode=session(at,cal)
        with db_open(root) as db:meta,s=initialize(root,db,at)
        if mode!='CONTINUOUS':
            with db_open(root) as db:
                db.execute('BEGIN IMMEDIATE');s=load_state(db);verify_projection(db,s)
                if any(o['status'] in ACTIVE for o in s['orders'].values()):
                    cancel_all(s,at,'OUTSIDE_SUPPORTED_CONTINUOUS_SESSION');persist(db,s)
            return publish(root,meta,s,{'status':'MARKET_CLOSED' if mode=='CLOSED' else 'OBSERVE_ONLY'})
        start=time.monotonic();source_errors=[]
        try:quotes,second=collect(list(meta['universe']),diagnostics=source_errors)
        except (OSError,ValueError,TypeError) as exc:
            quotes,second={},{};source_errors.append(dict(source='collection',error=type(exc).__name__))
        received=pd.Timestamp(now());request_duration=time.monotonic()-start
        # The decision clock is AFTER the requests complete, never before an observation.
        at=received;mode=session(at,cal);refpath=root/'data/intraday/reference'/(str(at.date())+'.json')
        try:
            ref=json.loads(refpath.read_text()) if refpath.exists() else {}
            if not isinstance(ref,dict):raise ValueError('REFERENCE_INVALID')
            digest(ref)
        except (OSError,ValueError):
            ref={};source_errors.append(dict(source='reference',error='REFERENCE_INVALID'))
        def sanitized(items,label):
            result={}
            for k,q in (items.items() if isinstance(items,dict) else []):
                try:
                    if k not in meta['universe'] or not isinstance(q,dict):raise ValueError()
                    t=pd.Timestamp(q['asof'])
                    if pd.isna(t) or t.tzinfo is None:raise ValueError()
                    digest(q)  # rejects non-finite JSON before immutable recording
                    if any(not isinstance(q.get(f),(int,float)) or not math.isfinite(q[f]) for f in ('price','previous_close')):raise ValueError()
                    result[k]=q
                except (ValueError,TypeError,KeyError):source_errors.append(dict(source=label,symbol=k,error='QUOTE_INVALID'))
            return result
        quotes=sanitized(quotes,'primary');second=sanitized(second,'secondary');checks={}
        for k in meta['universe']:
            try:checks[k]=quality(quotes.get(k),second.get(k),ref,k,at,cal,meta['anchor'],meta['monitor_config'])
            except (ValueError,TypeError,KeyError,AttributeError):checks[k]=['REFERENCE_INVALID']
        for k,q in quotes.items():
            try:q['volume_shares']=observed_bar(q,at)['volume']
            except (KeyError,ValueError,TypeError):checks.setdefault(k,[]).append('PARTIAL_BAR_UNVERIFIED')
        cycle_id=str(int(at.timestamp()//30))
        with db_open(root) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM records WHERE kind='cycles' AND key=?",(cycle_id,)).fetchone():return {'status':'ALREADY_PROCESSED'}
            s=load_state(db);verify_projection(db,s);before=digest(s)
            history=[json.loads(x[0]) for x in db.execute("SELECT body FROM records WHERE kind='cycles' ORDER BY CAST(key AS INTEGER) DESC LIMIT 16").fetchall()][::-1]
            history.append(dict(at=at.isoformat(),quotes=quotes,checks=checks))
            audit=None;model=None;r=None
            try:
                r=source(root,at,cal)
                if r['meta']['config']!=meta['config']:raise ValueError('RISK_OR_FEE_CONFIG_CHANGED_REVIEW_REQUIRED')
                saved=db.execute("SELECT body,sha256 FROM records WHERE kind='model' ORDER BY CAST(key AS INTEGER) DESC LIMIT 1").fetchone()
                prior=json.loads(saved[0]) if saved else None
                if prior and digest(prior)!=saved[1]:raise ValueError('MODEL_CACHE_TAMPERED')
                if prior and prior['original_sha']==digest(r['predictions']) and 0<=(at-pd.Timestamp(prior['at'])).total_seconds()<meta['monitor_config']['model_refresh_seconds']:
                    plan=prior['plan'];model=prior['audit']
                else:
                    marked=copy.deepcopy(s)
                    for k,q in quotes.items():
                        if not checks.get(k):marked['marks'][k]=q['price']
                    marked['equity']=marked['cash']+sum(p['shares']*marked['marks'][k] for k,p in marked['positions'].items())
                    plan,model=dynamic_plan(root,r,marked,quotes,checks,cal,at)
                    put(db,'model',cycle_id,dict(at=at.isoformat(),original_sha=digest(r['predictions']),plan=plan,audit=model))
                events=snapshot(root,at,meta['adaptive_config']);plan,audit=adjust(plan,s,quotes,history,events,meta['config'],meta['adaptive_config'],at)
                for k in audit['buy_blocks']:plan['edges'][k]=None
                for row in plan['rows']:
                    k=row['symbol'];row['target_weight']=plan['weights'].get(k,0.)
                    row['reasons']=row.get('reasons',[])+audit.get('stocks',{}).get(k,{}).get('reasons',[])
                    row['quote_time']=quotes[k]['asof']
                put(db,'events',digest(events),events)
                s,out=step(s,plan,quotes,checks,meta['config'],meta['monitor_config'],at,{r['symbol']:r['sector'] for r in plan['rows']},continuous=mode=='CONTINUOUS')
                out['decision_rows']=plan['rows'];out['model']=model;out['adaptive']=audit
            except (ValueError,KeyError,TypeError,IndexError,AttributeError,OSError) as exc:
                reason=str(exc) if isinstance(exc,ValueError) else 'DYNAMIC_MODEL_INPUT_INVALID'
                from .order_engine import event
                for order in s['orders'].values():
                    if order['status'] in ACTIVE and order['side']=='BUY':event(s,order,'CANCELED',at,'DECISION_INPUT_UNAVAILABLE')
                from .order_engine import quote_guards,value
                checks=quote_guards(s,quotes,checks,at,meta['monitor_config']);value(s,quotes,checks,at)
                if 'CONFIG_CHANGED' in str(exc):
                    out=dict(status='WAIT_CONFIG_REVIEW',reason=reason,checks=checks)
                else:
                    from .order_engine import risk_only_plan
                    environment=r.get('environment') if isinstance(r,dict) else None
                    fallback=risk_only_plan(s,quotes,meta['config'],environment)
                    predictions=r.get('predictions') if isinstance(r,dict) else None
                    rows=(predictions.get('forecasts') or []) if isinstance(predictions,dict) else []
                    sectors={x['symbol']:x.get('sector') for x in rows if isinstance(x,dict) and x.get('symbol')}
                    # step must inspect this same quote once; guards were already evaluated above.
                    for k in quotes:
                        if not checks.get(k):s['quote_seen'].pop(k,None)
                    s,risk=step(s,fallback,quotes,checks,meta['config'],meta['monitor_config'],at,sectors,continuous=mode=='CONTINUOUS')
                    out=dict(**risk,reason=reason,input_error=dict(type=type(exc).__name__,detail=str(exc)),inference_status='UNAVAILABLE_RISK_REDUCTIONS_ONLY')
            put(db,'references',digest(ref),ref)
            out['source_errors']=source_errors
            record=dict(reference_sha=digest(ref),secondary_quotes=second,at=at.isoformat(),quotes=quotes,checks=out.get('checks',checks),source_request_seconds=request_duration,quote_age_seconds={k:(at-pd.Timestamp(q['asof'])).total_seconds() for k,q in quotes.items()},before=before,after=digest(s),result=out)
            put(db,'cycles',cycle_id,record);persist(db,s);db.commit()
        return publish(root,meta,s,out)


def close_day(root,day):
    root=Path(root)
    if not enabled(root):return {'status':'DISABLED'}
    with run_lock(root/'logs/dynamic'):
        at=pd.Timestamp(now());cal=days(root)
        if pd.Timestamp(day) not in cal or day>str(at.date()) or (day==str(at.date()) and (at.hour,at.minute)<(15,5)):raise ValueError('CLOSE_NOT_AVAILABLE')
        with db_open(root) as db:
            db.execute('BEGIN IMMEDIATE');meta,s=initialize(root,db,at)
            if day<=s['closed_day']:
                reconcile_counters(db,s,at);db.commit()
                return publish(root,meta,s,{'status':'ALREADY_SETTLED'})
            if str(cal[cal<pd.Timestamp(day)][-1].date())!=s['closed_day']:raise ValueError('MISSING_PREVIOUS_SETTLEMENT')
            cancel_all(s,at,'END_OF_SESSION')
            # No successful intraday cycle is required to advance daily counters.
            # Cumulative fees and per-order minimum commissions are untouched.
            s.update(day_counters(s,day))
            held=[k for k,p in s['positions'].items() if p['shares']];obs=evidence(root,day,held)
            if set(obs['bars'])!=set(held) or set(obs['states'])!=set(held) or any(v['corporate_action_status']!='none' for v in obs['states'].values()):raise ValueError('CLOSE_OR_CORPORATE_ACTION_UNVERIFIED')
            for k,b in obs['bars'].items():s['marks'][k]=b['close']
            equity=s['cash']+sum(p['shares']*s['marks'][k] for k,p in s['positions'].items());s['peak']=max(s['peak'],equity);s['max_drawdown']=max(s['max_drawdown'],1-equity/s['peak'])
            nav=dict(date=day,equity=equity,cash=s['cash'],daily_pnl=equity-s['previous_close_equity'],daily_return=equity/s['previous_close_equity']-1,cumulative_return=equity/meta['initial_equity']-1,realized_pnl=s['realized_pnl'],unrealized_pnl=sum(p['shares']*s['marks'][k]-p['basis'] for k,p in s['positions'].items()),fees=s['fees'],total_fees=s['total_fees'],max_drawdown=s['max_drawdown'],mode='PAPER_ONLY')
            if abs(nav['realized_pnl']+nav['unrealized_pnl']-(equity-meta['initial_equity']))>.02:raise ValueError('PNL_RECONCILIATION_FAILED')
            put(db,'close_evidence',day,obs);put(db,'nav',day,nav);s.update(equity=equity,previous_close_equity=equity,closed_day=day,day=day,valuation_at=day+'T15:00:00+08:00',valuation_status='VERIFIED_CLOSE',unrealized_pnl=nav['unrealized_pnl']);persist(db,s);db.commit()
        return publish(root,meta,s,{'status':'SETTLED'})


def publish(root,meta,s,result):
    folder=root/'reports/dynamic/latest';folder.mkdir(parents=True,exist_ok=True)
    with db_open(root) as db:
        nav=list(get(db,'nav').values());execution_code=reviewed_code(db,meta)
        from .reporting.dynamic_status import snapshot as decision_snapshot
        checked_at=now().isoformat()
        diagnostic=decision_snapshot(db,meta['universe'],checked_at,result['status'])
    result={**result,'decision_rows':diagnostic['rows'],'last_decision_at':diagnostic['last_decision_at']}
    r=dict(checked_at=checked_at,mode='PAPER_ONLY',submitted_real_orders=0,meta=meta,account=s,nav=nav,execution_code=execution_code,decision_diagnostic={k:v for k,v in diagnostic.items() if k!='rows'},**result)
    r['unrealized_pnl_estimate']=sum(p['shares']*s['marks'][k]-p['basis'] for k,p in s['positions'].items())
    r['cumulative_return']=s['equity']/meta['initial_equity']-1;r['capital_utilization']=1-s['cash']/s['equity']
    r['limitations']=['仅模拟委托与估值，真实账户由用户手动交易，成交价/数量可能不同','盘中未完成日线输入尚未独立验证，原模型及正式准入标准不变','公开行情30秒轮询，无逐笔权限或低延迟服务承诺；资料缺失暂停','既有持仓成本按迁移估值建立阶段基准，不能当作券商历史成本','自动重报价通过超时撤单、冷却及新风险检查产生新委托，不追补断线期间成交']
    write_json(folder/'report.json',r);write_json(root/'data/dynamic/alerts.json',dict(updated_at=r['checked_at'],mode='PAPER_ONLY',alerts=s['alerts']))
    for name,rows in [('FILLS',s['executions']),('ORDERS',list(s['orders'].values())),('NAV',nav)]:
        pd.DataFrame(rows).to_csv(folder/(name+'.csv'),index=False,encoding='utf-8-sig')
    e=lambda x:html.escape(str(x));rows=''
    from .reporting.plain_chinese import translate
    last_events={item['order_id']:item for item in s['order_events']}
    for o in list(s['orders'].values())[-30:][::-1]:
        rows+='<tr>'+''.join('<td>'+e(x)+'</td>' for x in [o['created_at'],o['name'],o['side'],o['quantity'],o['filled'],o['limit_price'],o['status'],translate(last_events.get(o['id'],{}).get('reason','尚无状态记录')),'；'.join(o.get('rationale',[]))])+'</tr>'
    if not rows:rows='<tr><td colspan="9">尚无模拟委托；等待当时有效的行情、预测、资讯与风险检查，不预先假定成交。</td></tr>'
    positions=''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in [meta['universe'].get(k,k),p['shares'],p['sellable'],round(p.get('basis',0),2),s['marks'].get(k),round(p['shares']*s['marks'][k]-p.get('basis',0),2)])+'</tr>' for k,p in s['positions'].items() if p['shares'])
    page='<html lang="zh"><meta charset="utf-8"><meta http-equiv="refresh" content="30"><title>动态模拟交易与收益</title><style>body{font:15px/1.5 system-ui;margin:20px;color:#183047}table{border-collapse:collapse}th,td{padding:5px 9px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top;white-space:nowrap}.scroll{overflow:auto}h2{margin:16px 0 6px}</style><h1>动态模拟账户 · 不操作真实资金</h1><p>检查 '+e(r['checked_at'])+'；状态 '+e(r['status'])+'；估值 '+e(s['valuation_at'])+' / '+e(s['valuation_status'])+'</p><h2>买卖操作与委托状态</h2><p>ACCEPTED是待撮合，PARTIALLY_FILLED为部分模拟成交，FILLED为全部模拟成交；CANCELED/REJECTED没有新增成交。</p><div class="scroll"><table><tr><th>时间</th><th>股票</th><th>方向</th><th>委托股数</th><th>模拟成交股数</th><th>限价</th><th>状态</th><th>状态原因</th><th>依据</th></tr>'+rows+'</table></div>'
    page+='<h2>收益与持仓</h2><p>净值 '+f"{s['equity']:.2f}"+'；现金 '+f"{s['cash']:.2f}"+'；本阶段已实现 '+f"{s['realized_pnl']:.2f}"+'；未实现估值 '+f"{r['unrealized_pnl_estimate']:.2f}"+'；累计 '+f"{r['cumulative_return']:.2%}"+'；累计费用 '+f"{s['total_fees']:.2f}"+'；最大回撤 '+f"{s['max_drawdown']:.2%}"+'。</p><p>'+e(meta['basis_note'])+'</p><div class="scroll"><table><tr><th>股票</th><th>持有</th><th>可卖</th><th>阶段成本</th><th>参考估值价</th><th>阶段浮盈亏</th></tr>'+positions+'</table></div>'
    from .reporting.dynamic_status import render as render_decision_status
    page+=render_decision_status(diagnostic,meta['universe'],s['positions'])
    page+='<p>'+e(result.get('reason',''))+'</p><ul>'+''.join('<li>'+e(x)+'</li>' for x in r['limitations'])+'</ul><p><a href="FILLS.csv">模拟成交</a> · <a href="ORDERS.csv">委托</a> · <a href="NAV.csv">每日收益</a> · <a href="report.json">完整决策与时间证据</a></p></html>'
    atomic_text(folder/'index.html',page)
    health={k:r[k] for k in ('status','checked_at','mode','submitted_real_orders')};health['reason']=r.get('reason');write_json(root/'logs/dynamic_health.json',health)
    return health


def primary(root):
    p=Path(root)/'reports/dynamic/latest/report.json'
    if not p.exists():return '<section><h2>动态模拟账户等待初始化</h2></section>'
    r=json.loads(p.read_text());s=r['account'];e=html.escape
    orders='<div class="scroll"><table><tr><th>股票</th><th>方向</th><th>委托/模拟成交股数</th><th>限价</th><th>状态</th><th>时间</th></tr>'+''.join('<tr>'+''.join('<td>'+e(str(x))+'</td>' for x in [o['name'],o['side'],str(o['quantity'])+'/'+str(o['filled']),o['limit_price'],o['status'],o['created_at']])+'</tr>' for o in list(s['orders'].values())[-10:][::-1])+'</table></div>'
    if not s['orders']:orders='<p>尚无模拟委托，等待有效盘中数据；不会预设明天成交价格。</p>'
    return '<section><h2>当前主账户：真实行情驱动的研究模拟</h2><p>状态 '+e(r['status'])+'；估值 '+e(str(s['valuation_at']))+'；现金 '+f"{s['cash']:.2f}"+'元；权益 '+f"{s['equity']:.2f}"+'元。仅模拟，不等于真实账户成交。</p>'+orders+'<p><a href="详细报告/dynamic/latest/index.html">打开当前买卖委托、模拟成交及收益</a></p></section>'


def reconcile(root,path):
    supplied=json.loads(Path(path).read_text());at=pd.Timestamp(supplied['asof'])
    if at.tzinfo is None or at>pd.Timestamp(now()) or supplied.get('source')!='USER_MANUAL':raise ValueError('MANUAL_SOURCE_AND_VALID_TIMESTAMP_REQUIRED')
    cash=float(supplied['cash'])
    if not __import__('math').isfinite(cash) or cash<0:raise ValueError('INVALID_CASH')
    positions=supplied['positions']
    if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in positions.values()):raise ValueError('INVALID_SHARES')
    with db_open(root) as db:s=load_state(db)
    differences={k:dict(paper=s['positions'].get(k,{}).get('shares',0),manual=positions.get(k,0),difference=positions.get(k,0)-s['positions'].get(k,{}).get('shares',0)) for k in set(positions)|set(s['positions'])}
    report=dict(asof=at.isoformat(),source='USER_MANUAL_NOT_BROKER_VERIFIED',cash_difference=cash-s['cash'],positions=differences,paper_valuation_at=s['valuation_at'],note='仅核对差异；不修改模拟现金/持仓，不推断真实成交或真实盈亏')
    write_json(Path(root)/'reports/dynamic/latest/reconciliation.json',report);return report


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['poll','close','status','reconcile']);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--date');p.add_argument('--snapshot',type=Path);a=p.parse_args()
    try:
        if a.command=='reconcile':result=reconcile(a.root,a.snapshot)
        elif a.command=='status':result=json.loads((a.root/'logs/dynamic_health.json').read_text())
        else:result=close_day(a.root,a.date or str(now().date())) if a.command=='close' else cycle(a.root)
        print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as exc:
        if isinstance(exc,RuntimeError) and '另一次更新正在运行' in str(exc):return 0
        result=dict(status='FAILED',checked_at=now().isoformat(),error=type(exc).__name__+':'+str(exc),submitted_real_orders=0)
        write_json(a.root/'logs/dynamic_health.json',result);print(json.dumps(result,ensure_ascii=False));return 2

if __name__=='__main__':sys.exit(main())
