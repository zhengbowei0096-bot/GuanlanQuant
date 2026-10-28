"""Bounded real-provider retrieval and provenance-checked execution evidence.

A downloaded delisting list is not a complete historical PIT universe. Unknown
corporate actions are not silently mapped to 'none'. No token is logged/saved.
Verified official references: Tushare doc_id 25/183/214/27/28/103 (2026-10-19).
"""
from pathlib import Path
import hashlib,json,os,time,math
import pandas as pd
import requests
from .core import now,cutoff,load_config,read_watchlist,write_json
from .connections import digest,suspensions


API_FIELDS={
    'daily':'ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount',
    'stk_limit':'ts_code,trade_date,pre_close,up_limit,down_limit',
    'suspend_d':'ts_code,trade_date,suspend_timing,suspend_type',
    'adj_factor':'ts_code,trade_date,adj_factor',
    'dividend':'ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,imp_ann_date,base_date,base_share',
    'namechange':'ts_code,name,start_date,end_date,ann_date,change_reason',
}


def _save(root,name,request,data,provider):
    value=dict(dataset=name,provider=provider,request=request,fetched_at=now().isoformat(),data=data)
    key=digest(value);path=Path(root)/'data/history/raw'/(name+'-'+key+'.json');write_json(path,value)
    return dict(dataset=name,rows=len(data) if isinstance(data,list) else None,path=str(path.relative_to(root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),provider=provider,request=request,fetched_at=value['fetched_at'])


def verified(root,reference):
    path=(Path(root)/reference['path']).resolve()
    if not path.is_relative_to((Path(root)/'data/history/raw').resolve()):raise ValueError('HISTORY_PATH_ESCAPE')
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=reference['sha256']:raise ValueError('HISTORY_SOURCE_HASH_MISMATCH')
    value=json.loads(content)
    if value.get('dataset')!=reference.get('dataset'):raise ValueError('HISTORY_DATASET_MISMATCH')
    if value['provider']!=reference['provider'] or value['request']!=reference['request']:raise ValueError('HISTORY_SOURCE_IDENTITY_MISMATCH')
    if pd.Timestamp(value['fetched_at'])>pd.Timestamp(now()):raise ValueError('FUTURE_HISTORY_FETCH')
    return value['data']


def credential(root=None):
    value=os.environ.get('TUSHARE_TOKEN')
    if value:return value.strip()
    if root is not None:
        path=Path(root)/'data/credentials/tushare.token'
        if path.exists():
            if path.stat().st_mode & 0o077:raise RuntimeError('CREDENTIAL_FILE_MUST_BE_PRIVATE')
            return path.read_text().strip() or None
    return None


class Tushare:
    def __init__(self,root=None):
        self.token=credential(root)
        if not self.token:raise RuntimeError('TUSHARE_TOKEN_NOT_CONFIGURED')
    def query(self,name,**params):
        fields=params.pop('_fields','');items=[];offset=0;limit=1000
        for _ in range(100):
            response=requests.post('https://api.tushare.pro',json=dict(api_name=name,token=self.token,params={**params,'offset':offset,'limit':limit},fields=fields),timeout=(5,20))
            response.raise_for_status();raw=response.json()
            if raw.get('code')!=0:
                # Do not expose a provider exception containing request credentials.
                raise RuntimeError('TUSHARE_API_REJECTED:'+name+':'+str(raw.get('code')))
            data=raw.get('data')
            if not isinstance(data,dict) or not isinstance(data.get('items'),list) or not isinstance(data.get('fields'),list):raise ValueError('TUSHARE_SCHEMA_CHANGED:'+name)
            rows=[dict(zip(data['fields'],r)) for r in data['items']]
            if items and rows and rows[0] in items:raise ValueError('TUSHARE_PAGINATION_NOT_ADVANCING:'+name)
            items+=rows
            if len(rows)<limit:return items
            offset+=limit;time.sleep(1.3)
        raise ValueError('TUSHARE_PAGINATION_TRUNCATED:'+name)


def query_with_retry(client,api,params):
    # Retry only transient transport failures, never schema/permission errors.
    for attempt in range(3):
        try:return client.query(api,**params)
        except (requests.exceptions.Timeout,requests.exceptions.ConnectionError):
            if attempt==2:raise
            time.sleep(2*(attempt+1))


def _public(root,cfg):
    from .data import network_job
    results=[];errors=[]
    for name,kind,url in [('sse_delisted','history_sse_delisted','https://www.sse.com.cn/assortment/stock/list/delisting/'),('szse_delisted','history_sz_delisted','https://www.szse.cn/market/stock/suspend/index.html')]:
        try:
            from .network_retry import retry_read
            frame=retry_read(lambda:network_job(root,{**cfg,'worker_timeout_seconds':35},kind=kind))
            for col in ('公司代码','证券代码'):
                if col in frame:frame[col]=frame[col].astype(str).str.zfill(6)
            rows=json.loads(frame.to_json(orient='records',date_format='iso',force_ascii=False))
            if not rows:raise ValueError('EMPTY_OFFICIAL_LIST_NOT_CERTIFIED')
            results.append(_save(root,name,dict(url=url),rows,'SSE' if name.startswith('sse') else 'SZSE'))
        except Exception as exc:errors.append(dict(provider=name,error=str(exc)[-300:]))
    return results,errors


def refresh(root,days=1900,public=True,force=False):
    root=Path(root);end=cutoff();start=end-pd.Timedelta(days=days);cfg=load_config(root)
    pointer=root/'data/lifecycle/current.json'
    if pointer.exists():
        exp=json.loads(pointer.read_text())['experiment'];frozen=root/'data/lifecycle/experiments'/exp/'spec.json'
        if frozen.exists():start=min(start,pd.Timestamp(json.loads(frozen.read_text())['start_session'])-pd.Timedelta(days=30))
    existing=root/'data/history/latest.json'
    if existing.exists() and not force:
        old=json.loads(existing.read_text())
        if not old.get('errors') and old.get('asof')==str(end.date()) and old.get('token_available')==bool(credential(root)) and old.get('range_start')<=str(start.date()) and 0<=(pd.Timestamp(now())-pd.Timestamp(old['fetched_at'])).total_seconds()<3600:
            # Validate cached references; a corrupted cache never becomes successful.
            try:
                for ref in old.get('references',[]):verified(root,ref)
                return {**old,'cached':True}
            except (ValueError,OSError):pass
    refs=[];errors=[]
    if public:
        p,e=_public(root,cfg);refs+=p;errors+=e
        # A dated real suspension list is useful partial evidence, not full status.
        try:refs.append(_save(root,'suspensions',dict(date=str(end.date())),suspensions(str(end.date())),'Eastmoney'))
        except Exception as exc:errors.append(dict(provider='Eastmoney suspensions',error=str(exc)[-300:]))
    normalized=[];universe=[];token=bool(credential(root))
    if token:
        client=Tushare(root);date0=start.strftime('%Y%m%d');date1=end.strftime('%Y%m%d')
        for status in ('L','D','P'):
            try:
                params=dict(list_status=status,_fields='ts_code,symbol,name,market,list_date,delist_date,list_status')
                rows=client.query('stock_basic',**params);refs.append(_save(root,'stock_basic',params,rows,'Tushare'));universe+=rows
            except Exception as exc:errors.append(dict(provider='Tushare stock_basic '+status,error=str(exc)))
        for item in read_watchlist(root).itertuples():
            code=item.symbol+('.SH' if item.symbol.startswith('6') else '.SZ');datasets={};bindings={}
            for api in ('daily','stk_limit','suspend_d','adj_factor','dividend','namechange'):
                params=dict(ts_code=code,_fields=API_FIELDS[api])
                if api not in ('dividend','namechange'):params.update(start_date=date0,end_date=date1)
                try:
                    rows=query_with_retry(client,api,params);reference=_save(root,api,params,rows,'Tushare');refs.append(reference);datasets[api]=rows;bindings[api]=reference
                except Exception as exc:errors.append(dict(provider='Tushare '+api,symbol=item.symbol,error=str(exc)))
                time.sleep(1.3)
            if len(datasets)==6:
                try:normalized+=normalize_tushare(item.symbol,datasets,bindings)
                except (ValueError,KeyError,TypeError) as exc:errors.append(dict(provider='Tushare normalization',symbol=item.symbol,error=str(exc)))
    else:errors.append(dict(provider='Tushare',error='TOKEN_OR_DATA_PERMISSION_REQUIRED; no credential was invented'))
    binding_sets={}
    for record in normalized:
        key=digest(record['bindings']);binding_sets[key]=record['bindings'];record['bindings']=key
    result=dict(binding_sets=binding_sets,schema=1,asof=str(end.date()),range_start=str(start.date()),fetched_at=now().isoformat(),token_available=token,
        references=refs,official_delisting_rows=sum(ref.get('rows') or 0 for ref in refs if ref['provider'] in ('SSE','SZSE')),listing_records=len(universe),execution_records=normalized,errors=errors,
        historical_universe_status='CURRENT_LISTING_EPISODES_ONLY_NOT_PIT_SELECTION_HISTORY',
        blockers=['HISTORICAL_SELECTION_MEMBERSHIP_NOT_CERTIFIED']+([] if normalized else ['COMPLETE_EXECUTION_DATA_UNAVAILABLE']))
    write_json(root/'data/history/manifests'/(digest(result)+'.json'),result)
    write_json(existing,result);write_json(root/'reports/history_sources/latest.json',result)
    # Keep compatibility with the legacy replay, but never invent absent state.
    if normalized:write_json(root/'data/execution_history.json',dict(records=[r for r in normalized if r['corporate_action_status'] in ('none','event')],source='provenance-bound Tushare adapter'))
    return result


def normalize_tushare(symbol,data,bindings):
    for api in ('daily','stk_limit','adj_factor'):
        dates=[r['trade_date'] for r in data[api]]
        if len(set(dates))!=len(dates):raise ValueError('DUPLICATE_PROVIDER_DATES:'+api)
    daily={r['trade_date']:r for r in data['daily']};limits={r['trade_date']:r for r in data['stk_limit']}
    factors={r['trade_date']:r.get('adj_factor') for r in data['adj_factor']}
    susp={r['trade_date'] for r in data['suspend_d'] if r.get('suspend_type')=='S'}
    events={r.get('ex_date') for r in data['dividend'] if r.get('div_proc')=='实施' and r.get('ex_date')}
    event_days={};complete_ex={};seen_events=set()
    for dividend in data['dividend']:
        if dividend.get('div_proc')!='实施' or not dividend.get('ex_date'):continue
        cash=float(dividend.get('cash_div_tax') or 0.);ratio=float(dividend.get('stk_div') or 0.)
        if cash==0 and ratio==0:continue
        record=dividend.get('record_date');ex=dividend['ex_date'];pay=dividend.get('pay_date');listing=dividend.get('div_listdate')
        complete=bool(record and dividend.get('ann_date') and dividend['ann_date']<=record<ex and math.isfinite(cash) and math.isfinite(ratio) and cash>=0 and ratio>=0 and (cash==0 or pay and pay>=ex) and (ratio==0 or listing and listing>=ex))
        if not complete:continue
        event=dict(record_date=record,ex_date=ex,pay_date=pay,listing_date=listing,cash_per_share_gross=cash,bonus_ratio=ratio,tax_reserve_rate=.20)
        event['event_id']=digest(dict(symbol=symbol,event=event))
        if event['event_id'] in seen_events:continue
        seen_events.add(event['event_id']);complete_ex.setdefault(ex,[]).append(event)
        for date in (record,ex,pay,listing):
            if date:event_days.setdefault(date,[]).append(event)
    last_close=None
    result=[];last_factor=None
    for date in sorted(set(daily)|set(limits)|susp):
        factor=factors.get(date);action='unknown'
        if factor is not None and (not math.isfinite(float(factor)) or float(factor)<=0):raise ValueError('INVALID_ADJUSTMENT_FACTOR')
        if factor is not None and last_factor is not None and abs(float(factor)/float(last_factor)-1)<1e-10 and date not in events:action='none'
        # Rights issues, separate dividend payment/share delivery, taxes and
        # intraday halts require richer event data; never invent an event ledger.
        if date in complete_ex and factor is not None and last_factor is not None:
            gross=sum(e['cash_per_share_gross'] for e in complete_ex[date]);bonus=sum(e['bonus_ratio'] for e in complete_ex[date])
            if last_close and last_close>gross:
                expected=last_close*(1+bonus)/(last_close-gross)
                if abs(float(factor)/float(last_factor)-expected)<=.002:action='event'
        if date in event_days and action=='none':action='event'
        if factor is not None:last_factor=factor
        if date in daily:last_close=daily[date].get('close')
        limit=limits.get(date,{})
        names=[r for r in data.get('namechange',[]) if r.get('start_date') and r['start_date']<=date<=(r.get('end_date') or '99999999') and r.get('ann_date') and r['ann_date']<=date]
        name=max(names,key=lambda r:r['start_date'])['name'] if names else None
        ordinary=bool(name and not any(x in name.upper() for x in ('ST','退')))
        previous=limit.get('pre_close')
        if not isinstance(previous,(int,float)) or previous<=0 or not all(isinstance(limit.get(k),(int,float)) for k in ('up_limit','down_limit')):ordinary=False
        elif abs(limit['up_limit']-round(previous*1.1,2))>.011 or abs(limit['down_limit']-round(previous*.9,2))>.011:ordinary=False
        status='suspended' if date in susp else 'trading' if date in daily else 'unknown'
        result.append(dict(ordinary_session=ordinary,security_name=name,symbol=symbol,date=pd.Timestamp(date).strftime('%Y-%m-%d'),status=status,
            limit_up=limit.get('up_limit'),limit_down=limit.get('down_limit'),corporate_action_status=action,action={'events':event_days.get(date,[]),'source':'Tushare dividend; conservative 20% tax reserve'},
            source='Tushare daily+stk_limit+suspend_d+adj_factor+dividend',reference_ohlc={k:daily[date].get(k) for k in ('open','close','high','low')} if date in daily else None,bindings=bindings))
    return result


def execution_states(root,symbols,sessions):
    """Formal replay accepts only records bound to verified raw provider responses."""
    path=Path(root)/'data/history/latest.json'
    if not path.exists():return {},{},['PROVENANCE_BOUND_HISTORY_MISSING']
    manifest=json.loads(path.read_text());states={};errors=[];proof=digest(manifest)
    archived=Path(root)/'data/history/manifests'/(proof+'.json')
    if not archived.exists() or digest(json.loads(archived.read_text()))!=proof:return {},{},['HISTORY_MANIFEST_NOT_ARCHIVED']
    records={(r['symbol'],r['date']):r for r in manifest.get('execution_records',[])}
    checked={};normalized_cache={}
    for symbol in symbols:
        for day in sessions:
            date=str(day.date());r=records.get((symbol,date))
            if r is None:errors.append('MISSING_EXECUTION_STATE:'+symbol+':'+date);continue
            try:
                raw={}
                bindings=manifest.get('binding_sets',{}).get(r['bindings']) if isinstance(r['bindings'],str) else r['bindings']
                if not isinstance(bindings,dict) or set(bindings)!= {'daily','stk_limit','suspend_d','adj_factor','dividend','namechange'}:raise ValueError('EXECUTION_PROVENANCE_INCOMPLETE')
                binding_key=digest(bindings)
                for api,reference in bindings.items():
                    if reference.get('dataset')!=api or reference['provider']!='Tushare' or reference['request'].get('ts_code')!=symbol+('.SH' if symbol.startswith('6') else '.SZ'):raise ValueError('PROVIDER_SECURITY_OR_DATASET_MISMATCH')
                    sha=reference['sha256']
                    if sha not in checked:checked[sha]=verified(root,reference)
                    raw[api]=checked[sha]
                if binding_key not in normalized_cache:normalized_cache[binding_key]={x['date']:x for x in normalize_tushare(symbol,raw,r['bindings'])}
                expected=normalized_cache[binding_key].get(date)
                if expected is None or digest(expected)!=digest(r):raise ValueError('NORMALIZED_HISTORY_TAMPERED')
                if r['status'] not in ('trading','suspended') or r['corporate_action_status'] not in ('none','event') or r.get('ordinary_session') is not True:raise ValueError('CORPORATE_ACTION_OR_STATUS_UNRESOLVED')
                if r['status']=='trading' and not (isinstance(r.get('limit_down'),(int,float)) and isinstance(r.get('limit_up'),(int,float)) and 0<r['limit_down']<r['limit_up']):raise ValueError('DAILY_LIMITS_UNAVAILABLE')
                if r['status']=='trading' and (not r.get('reference_ohlc') or any(not isinstance(r['reference_ohlc'].get(k),(int,float)) or not math.isfinite(r['reference_ohlc'][k]) or r['reference_ohlc'][k]<=0 for k in ('open','close','high','low'))):raise ValueError('PROVIDER_OHLC_MISSING')
                states[symbol,date]=r
            except (ValueError,KeyError,OSError,TypeError) as exc:errors.append(str(exc)+':'+symbol+':'+date)
    return states,dict(manifest_sha256=proof,manifest_path=str(archived.relative_to(root)),checked_rows=len(states),required_rows=len(symbols)*len(sessions)),list(dict.fromkeys(errors))[:40]
