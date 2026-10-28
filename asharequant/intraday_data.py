"""Read-only market and corporate-action evidence for conditional paper fills."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,math
import pandas as pd
from .core import now,read_watchlist,write_json
from .connections import tencent_quotes,sina_quotes,suspensions
from .history_sources import Tushare,API_FIELDS

def days(root):
    return pd.DatetimeIndex(pd.to_datetime(pd.read_csv(Path(root)/'data/calendar.csv').iloc[:,0])).sort_values()

def refresh_reference(root,force=False):
    root=Path(root);at=now();day=str(at.date());cal=days(root)
    if pd.Timestamp(day) not in cal or (not force and not (9<=at.hour<16)):return {'status':'OUTSIDE_REFERENCE_WINDOW'}
    folder=root/'data/intraday/reference';path=folder/(day+'.json');symbols=read_watchlist(root).symbol.tolist()
    result=json.loads(path.read_text()) if path.exists() else dict(date=day,symbols={},errors=[])
    client=Tushare(root)
    if not result.get('complete'):
        limits={x['ts_code'][:6]:x for x in client.query('stk_limit',trade_date=day.replace('-',''),_fields=API_FIELDS['stk_limit'])}
        basic={x['ts_code'][:6]:x for x in client.query('stock_basic',list_status='L',_fields='ts_code,name,market,list_date')}
        def one(s):
            rows=client.query('dividend',ts_code=s+('.SH' if s.startswith('6') else '.SZ'),_fields=API_FIELDS['dividend'])
            if s not in limits or s not in basic:raise ValueError('LIMIT_OR_LISTING_MISSING')
            return dict(source='Tushare',fetched_at=now().isoformat(),limits=limits[s],basic=basic[s],dividends=rows)
        result['errors']=[]
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs={s:pool.submit(one,s) for s in symbols if s not in result['symbols']}
            for s,f in jobs.items():
                try:result['symbols'][s]=f.result()
                except Exception as exc:result['errors'].append(s+':'+type(exc).__name__)
        result['complete']=set(result['symbols'])==set(symbols)
    # Intraday suspension evidence is refreshed separately from once-daily actions.
    result['suspensions']=suspensions(day);result['refreshed_at']=now().isoformat()
    write_json(path,result);return dict(status='REFERENCE_READY' if result['complete'] else 'PARTIAL_REFERENCE',symbols=len(result['symbols']),errors=result['errors'])

def collect(symbols,diagnostics=None):
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(fn,symbols) for fn in (tencent_quotes,sina_quotes)];out=[]
        for name,f in zip(('Tencent','Sina'),jobs):
            try:out.append(f.result())
            except Exception as exc:
                out.append({})
                if diagnostics is not None:diagnostics.append(dict(source=name,error=type(exc).__name__,recovery='NEXT_SCHEDULED_CYCLE'))
    return out

def quality(q,second,reference,symbol,at,cal,anchor,cfg):
    reasons=[];day=str(at.date());ref=reference.get('symbols',{}).get(symbol)
    if not q or not second:return ['QUOTE_SOURCE_UNAVAILABLE']
    for x in (q,second):
        try:
            age=(at-pd.Timestamp(x['asof'])).total_seconds()
            if not 0<=age<=cfg['quote_max_age_seconds'] or str(pd.Timestamp(x['asof']).date())!=day:reasons.append('QUOTE_STALE_OR_FUTURE')
            if not x['price'] or x['price']<=0:reasons.append('PRICE_INVALID')
        except (ValueError,KeyError,TypeError):reasons.append('QUOTE_INVALID')
    if any(not isinstance(x.get(k),(int,float)) or not math.isfinite(x[k]) or x[k]<=0 for x in (q,second) for k in ('price','previous_close')):return reasons+['QUOTE_INVALID']
    if q.get('name')!=second.get('name') or abs(q['price']-second['price'])>.011 or abs(q['previous_close']-second['previous_close'])>.011:reasons.append('VENDOR_CONFLICT')
    if not ref or reference.get('date')!=day:return reasons+['CURRENT_REFERENCE_MISSING']
    try:
        fetched=pd.Timestamp(ref['fetched_at'])
        if fetched>at or str(fetched.date())!=day:reasons.append('REFERENCE_STALE')
        listing=pd.Timestamp(ref['basic']['list_date']);seasoned=len(cal[(cal>=listing)&(cal<=pd.Timestamp(day))])>5
        if not seasoned or ref['basic']['market']!='主板' or any(x in q['name'].upper() for x in ('ST','退')):reasons.append('SECURITY_NOT_SUPPORTED')
        lo=float(ref['limits']['down_limit']);hi=float(ref['limits']['up_limit'])
        if not lo<q['price']<hi or abs(q['limit_down']-lo)>.011 or abs(q['limit_up']-hi)>.011:reasons.append('LIMIT_LOCK_OR_CONFLICT')
        for row in ref['dividends']:
            if any(row.get(k) and anchor<=str(pd.Timestamp(row[k]).date())<=day for k in ('record_date','ex_date','pay_date','div_listdate')):
                reasons.append('CORPORATE_ACTION_RECONCILIATION_REQUIRED');break
        susp=reference.get('suspensions',{})
        age=(at-pd.Timestamp(susp.get('fetched_at'))).total_seconds()
        if not susp.get('complete') or susp.get('date')!=day or not 0<=age<=360:reasons.append('SUSPENSION_EVIDENCE_STALE')
        if any(r.get('SECURITY_CODE')==symbol for r in susp.get('items',[])):reasons.append('SUSPENDED_OR_EVENT')
        if not all(q.get(k) and q[k]>0 for k in ('bid','ask','bid_size_lots','ask_size_lots')) or q['bid']>q['ask']:reasons.append('BOOK_INVALID')
    except (ValueError,KeyError,TypeError):reasons.append('REFERENCE_INVALID')
    return sorted(set(reasons))
