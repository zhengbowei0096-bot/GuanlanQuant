"""Public source snapshots. Historical restatements are NOT point-in-time vintages.
No production model promotion. All field names and nulls retained verbatim.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sqlite3, subprocess, sys, tempfile, logging, time, re, html
import pandas as pd

SOURCES = {
 'valuations':'stock_value_em', 'financial_main':'stock_financial_analysis_indicator_em',
 'industry_list':'index_realtime_sw','industry_members':'index_component_sw',
 'industry_history':'stock_industry_clf_hist_sw','industry_bars':'index_hist_sw',
 'macro_cpi':'macro_china_cpi','macro_pmi':'macro_china_pmi','macro_gdp':'macro_china_gdp',
 'macro_money':'macro_china_money_supply','macro_lpr':'macro_china_lpr'}
DATE_FIELDS={'valuations':'数据日期','financial_main':'REPORT_DATE','financial_balance':'REPORT_DATE',
 'financial_income':'REPORT_DATE','financial_cashflow':'REPORT_DATE','industry_bars':'日期',
 'industry_history':'start_date','macro_cpi':'月份','macro_pmi':'月份','macro_gdp':'季度',
 'macro_money':'月份','macro_lpr':'TRADE_DATE'}

def stamp(): return datetime.now(timezone.utc).isoformat()
def canonical(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def period(x):
 s=str(x)
 m=re.search(r'(\d{4})年\s*(\d{1,2})月',s)
 if m:return str(pd.Period(f'{m[1]}-{int(m[2]):02d}',freq='M').end_time.date())
 m=re.search(r'(\d{4})年?第?\s*(?:1-)?([1-4])季度',s)
 if m:return str(pd.Period(f'{m[1]}Q{m[2]}',freq='Q').end_time.date())
 return str(pd.Timestamp(s).date())

def normalise(df,dataset,start,end):
 if df.empty:raise ValueError('接口返回空表')
 df=df.drop_duplicates().copy()
 datecol=DATE_FIELDS.get(dataset)
 if datecol:
  if datecol not in df:raise ValueError('缺少日期列 '+datecol)
  dates=df[datecol].map(period)
  df=df.loc[(dates>=start)&(dates<=end)].copy();df['_observation_date']=dates.loc[df.index]
 if df.empty:raise ValueError('请求区间没有真实记录')
 if dataset in ('industry_bars','valuations') and df['_observation_date'].duplicated().any():raise ValueError('日期重复且记录冲突')
 if dataset=='industry_bars':
  for c in ['开盘','最高','最低','收盘']:
   df[c]=pd.to_numeric(df[c],errors='raise')
   if df[c].isna().any() or (df[c]<=0).any():raise ValueError('无效行业指数价格')
  if ((df['最高']<df[['开盘','收盘','最低']].max(axis=1))|(df['最低']>df[['开盘','收盘','最高']].min(axis=1))).any():raise ValueError('OHLC关系错误')
 if dataset=='valuations':
  for c in ['总市值','流通市值','总股本','流通股本']:
   if (pd.to_numeric(df[c],errors='raise').dropna()<=0).any():raise ValueError('非正市值/股本')
 # Round-trip converts numpy scalars and NaN to JSON-native values/null.
 rows=json.loads(df.to_json(orient='records',date_format='iso',force_ascii=False,double_precision=15))
 rows.sort(key=canonical)
 return rows

def connect(root):
 db=sqlite3.connect(root/'data/market.sqlite3',timeout=30)
 db.executescript('''CREATE TABLE IF NOT EXISTS factor_snapshots(
 dataset TEXT,entity TEXT,content_hash TEXT,first_seen_at TEXT,raw_path TEXT,rows_json TEXT,
 PRIMARY KEY(dataset,entity,content_hash));
 CREATE TABLE IF NOT EXISTS factor_fetches(
 dataset TEXT,entity TEXT,fetched_at TEXT,content_hash TEXT,metadata_json TEXT,
 PRIMARY KEY(dataset,entity,fetched_at));
 CREATE TABLE IF NOT EXISTS factor_current(
 dataset TEXT,entity TEXT,content_hash TEXT,fetched_at TEXT,rows_count INTEGER,
 PRIMARY KEY(dataset,entity));''')
 return db

def persist(root,dataset,entity,raw,rows,meta):
 digest=hashlib.sha256(canonical(rows).encode()).hexdigest()
 folder=root/'data/factors'/dataset/entity/digest;folder.mkdir(parents=True,exist_ok=True)
 path=folder/'raw.csv'
 if not path.exists():
  with tempfile.NamedTemporaryFile(mode='w',dir=folder,suffix='.csv',delete=False) as handle:
   raw.to_csv(handle,index=False);temp_path=Path(handle.name)
  temp_path.replace(path)
 with connect(root) as db:
  old=db.execute('SELECT rows_json FROM factor_snapshots JOIN factor_current USING(dataset,entity,content_hash) WHERE dataset=? AND entity=?',(dataset,entity)).fetchone()
  if old and dataset in DATE_FIELDS:
   previous={x['_observation_date'] for x in json.loads(old[0]) if meta['start']<=x['_observation_date']<=meta['end']}
   if not previous.issubset({x['_observation_date'] for x in rows}):raise ValueError('响应遗漏已存日期，保留旧快照')
  db.execute('INSERT OR IGNORE INTO factor_snapshots VALUES(?,?,?,?,?,?)',(dataset,entity,digest,meta['fetched_at'],str(path),canonical(rows)))
  db.execute('INSERT INTO factor_fetches VALUES(?,?,?,?,?)',(dataset,entity,meta['fetched_at'],digest,canonical(meta)))
  db.execute('INSERT OR REPLACE INTO factor_current VALUES(?,?,?,?,?)',(dataset,entity,digest,meta['fetched_at'],len(rows)))
 return digest

def asof_records(root,dataset,entity,asof):
 """Strict locally observed vintage, never backfill first-download history."""
 point=pd.Timestamp(asof)
 if point.tzinfo is None:raise ValueError('asof必须包含时区')
 value=point.tz_convert('UTC').isoformat()
 with connect(root) as db:
  row=db.execute('SELECT s.rows_json FROM factor_fetches f JOIN factor_snapshots s USING(dataset,entity,content_hash) WHERE f.dataset=? AND f.entity=? AND f.fetched_at<=? ORDER BY f.fetched_at DESC LIMIT 1',(dataset,entity,value)).fetchone()
 if not row:return []
 result=[]
 for item in json.loads(row[0]):
  if item.get('_observation_date', '1900-01-01') > str(point.tz_convert('Asia/Shanghai').date()):continue
  release=[item.get(k) for k in ('NOTICE_DATE','UPDATE_DATE','update_time') if item.get(k)]
  if any(pd.Timestamp(x).date()>point.tz_convert('Asia/Shanghai').date() for x in release):continue
  result.append(item)
 return result

def worker(job,output,root):
 import akshare as ak,requests,certifi,importlib
 original=requests.sessions.Session.request
 with tempfile.TemporaryDirectory() as tmp:
  bundle=Path(tmp)/'ca.pem';bundle.write_bytes(Path(certifi.where()).read_bytes()+b'\n'+(root/'certs/sw-intermediate.pem').read_bytes())
  def bounded(self,method,url,**kwargs):
   kwargs['timeout']=(8,20)
   kwargs['verify']=str(bundle) if 'swsresearch.com' in url else True
   from .network_retry import request_read
   return request_read(original,self,method,url,**kwargs)
  requests.sessions.Session.request=bounded
  ds=job['dataset'];params=job['params']
  if ds in ('financial_balance','financial_income','financial_cashflow'):
   mod=importlib.import_module(ak.stock_balance_sheet_by_report_em.__module__)
   code=params['symbol'];typ=mod._stock_balance_sheet_by_report_ctype_em(symbol=code)
   part={'financial_balance':'zcfzb','financial_income':'lrb','financial_cashflow':'xjllb'}[ds]
   base='https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/'
   args={'companyType':typ,'reportDateType':'0','code':code}
   res=requests.get(base+part+'DateAjaxNew',params=args);res.raise_for_status()
   dates=[str(x['REPORT_DATE'])[:10] for x in res.json()['data'] if job['start']<=str(x['REPORT_DATE'])[:10]<=job['end']]
   frames=[]
   for i in range(0,len(dates),5):
    batch=dates[i:i+5];res=requests.get(base+part+'AjaxNew',params={**args,'reportType':'1','dates':','.join(batch)});res.raise_for_status()
    frame=pd.DataFrame(res.json()['data'])
    if not set(batch).issubset(set(frame['REPORT_DATE'].str[:10])):raise ValueError('财务报表返回不完整')
    frames.append(frame)
   df=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
  else:df=getattr(ak,SOURCES[ds])(**params)
  df.to_csv(output,index=False)

def fetch(root,dataset,entity,params,start,end,full=False):
 with connect(root) as db:
  cached=db.execute('SELECT c.fetched_at,f.metadata_json FROM factor_current c JOIN factor_fetches f USING(dataset,entity,fetched_at,content_hash) WHERE dataset=? AND entity=?',(dataset,entity)).fetchone()
 if cached and json.loads(cached[1])['end']==end and not full and (datetime.now(timezone.utc)-datetime.fromisoformat(cached[0])).total_seconds()<86400:
  with connect(root) as db:
   return json.loads(db.execute('SELECT rows_json FROM factor_snapshots JOIN factor_current USING(dataset,entity,content_hash) WHERE dataset=? AND entity=?',(dataset,entity)).fetchone()[0])
 job=dict(dataset=dataset,params=params,start=start,end=end)
 for attempt in range(2):
  try:
   with tempfile.TemporaryDirectory(prefix='aq-factor-') as tmp:
    inp=Path(tmp)/'job.json';out=Path(tmp)/'out.csv';inp.write_text(json.dumps(job))
    proc=subprocess.run([sys.executable,'-m','asharequant.factors','worker',str(inp),str(out),str(root)],cwd=root,capture_output=True,text=True,timeout=180)
    if proc.returncode:raise RuntimeError(proc.stderr[-1200:])
    raw=pd.read_csv(out,dtype={c:str for c in ['symbol','industry_code','证券代码','代码','指数代码','SECURITY_CODE','SECUCODE']})
   if dataset.startswith('financial_'):
    if 'SECURITY_CODE' not in raw or set(raw.SECURITY_CODE.astype(str).str.zfill(6))!={entity}:raise ValueError('财务接口股票代码不匹配')
   if dataset=='industry_bars' and set(raw['代码'].astype(str).str.zfill(6))!={entity}:raise ValueError('行业指数代码不匹配')
   rows=normalise(raw,dataset,start,end)
   meta={**job,'fetched_at':stamp(),'source':SOURCES.get(dataset,'eastmoney_statement_'+dataset),'pit_verified':False,
    'release_policy':'保留公告与更新日期；没有发布日期则为空；严格历史使用须先被本地观察到',
    'industry_volume_amount_units':'provider_unspecified' if dataset=='industry_bars' else None}
   persist(root,dataset,entity,raw,rows,meta)
   logging.info('扩展数据 %s %s：%d 条',dataset,entity,len(rows));return rows
  except Exception:
   if attempt:raise
   time.sleep(1)

def audit(root,start,end):
 calendar=pd.read_csv(root/'data/calendar.csv').trade_date
 expected=set(calendar[(calendar>=start)&(calendar<=end)])
 results=[]
 with connect(root) as db:
  snapshots=db.execute('SELECT dataset,entity,rows_json FROM factor_snapshots JOIN factor_current USING(dataset,entity,content_hash)').fetchall()
  for ds,entity,encoded in snapshots:
   rows=json.loads(encoded);dates={x['_observation_date'] for x in rows if '_observation_date' in x}
   item={'dataset':ds,'entity':entity,'rows':len(rows),'first_date':min(dates) if dates else None,'last_date':max(dates) if dates else None}
   if ds=='industry_bars':
    item.update(missing_sessions=sorted(expected-dates),unexpected_sessions=sorted(dates-expected),volume_unit='provider_unspecified',amount_unit='provider_unspecified')
   if ds=='valuations':
    expected_stock={x[0] for x in db.execute('SELECT date FROM daily_bars WHERE symbol=? AND date>=? AND date<=?',(entity,start,end))}
    item['missing_stock_sessions']=sorted(expected_stock-dates)
    item['extra_dates_vs_stock_bars']=sorted(dates-expected_stock)
    prices=dict(db.execute('SELECT date,close FROM daily_bars WHERE symbol=? AND date>=? AND date<=?',(entity,start,end)))
    item['close_mismatches_over_002']=[x['_observation_date'] for x in rows if x['_observation_date'] in prices and x.get('当日收盘价') is not None and abs(float(x['当日收盘价'])-prices[x['_observation_date']])>0.020001]
   if ds.startswith('financial_'):
    item['missing_notice_date']=sum(not x.get('NOTICE_DATE') for x in rows)
    item['missing_update_date']=sum(not x.get('UPDATE_DATE') for x in rows)
    item['known_revisions']=sum(bool(x.get('UPDATE_DATE') and x.get('NOTICE_DATE') and x['UPDATE_DATE']>x['NOTICE_DATE']) for x in rows)
   if ds.startswith('macro_'):
    item['publication_date_available']=False
    item['rate_date_available']=ds=='macro_lpr'
   results.append(item)
 return results

def update(root,dataset='all',full=False):
 from .core import cutoff
 root=Path(root);end=str(cutoff().date());start=str((pd.Timestamp(end)-pd.DateOffset(years=5)).date())
 watch=pd.read_csv(root/'watchlist.csv',dtype={'symbol':str});symbols=watch.loc[watch.enabled==1,'symbol'].tolist()
 errors=[]
 def get(ds,entity,params,begin=start):
  try:return fetch(root,ds,entity,params,begin,end,full)
  except Exception as e:
   msg=f'{ds}/{entity}: {e}';errors.append(msg);logging.exception(msg);return []
 if dataset in ('all','industry'):
  indices=get('industry_list','sw_level1',{'symbol':'一级行业'},'1900-01-01')
  get('industry_history','sw_classification',{},'1900-01-01')
  mapping=[]
  for index in indices:
   code=str(index['指数代码']).zfill(6)
   members=get('industry_members',code,{'symbol':code},'1900-01-01')
   selected=[x for x in members if str(x['证券代码']).zfill(6) in symbols]
   if selected:
    get('industry_bars',code,{'symbol':code,'period':'day'})
    mapping.extend({'symbol':str(x['证券代码']).zfill(6),'index':code,'name':index['指数名称'],'membership':x} for x in selected)
  (root/'reports/industry_mapping.json').write_text(json.dumps({'observed_at':stamp(),'historical_backfill_allowed':False,'mapping':mapping},ensure_ascii=False,indent=2))
  missing=set(symbols)-{x['symbol'] for x in mapping}
  if missing:errors.append('行业映射缺失：'+','.join(sorted(missing)))
 if dataset in ('all','valuations'):
  for s in symbols:get('valuations',s,{'symbol':s})
 if dataset in ('all','financial'):
  for s in symbols:
   get('financial_main',s,{'symbol':s+('.SH' if s.startswith('6') else '.SZ'),'indicator':'按报告期'})
   for kind in ['balance','income','cashflow']:get('financial_'+kind,s,{'symbol':('SH' if s.startswith('6') else 'SZ')+s})
 if dataset in ('all','macro'):
  for name in ['cpi','pmi','gdp','money','lpr']:get('macro_'+name,'china',{})
 with connect(root) as db:
  counts=[dict(zip(['dataset','entities','rows','oldest_fetch'],x)) for x in db.execute('SELECT dataset,COUNT(*),SUM(rows_count),MIN(fetched_at) FROM factor_current GROUP BY dataset')]
  integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
 quality=audit(root,start,end)
 gaps=sum(len(x.get('missing_sessions',[]))+len(x.get('missing_stock_sessions',[])) for x in quality)
 result=dict(quality=quality,missing_daily_records=gaps,quality_status='incomplete' if gaps else 'see_field_limitations',success=not errors,run_at=stamp(),requested=dataset,start=start,end=end,counts=counts,errors=errors,database_integrity=integrity,production_model_uses_new_factors=False)
 (root/'reports/factors.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 rows=''.join('<tr>'+''.join('<td>'+html.escape(str(x[k]))+'</td>' for k in ['dataset','entities','rows','oldest_fetch'])+'</tr>' for x in counts)
 page='''<!doctype html><meta charset="utf-8"><title>扩展数据接入</title><style>body{font:16px system-ui;margin:40px;line-height:1.8;color:#17263d}td,th{padding:10px;border-bottom:1px solid #ddd}table{border-collapse:collapse}pre{white-space:pre-wrap}</style><h1>行业、估值、财务和宏观数据</h1>'''
 page+=f'<p>历史范围：{start} 至 {end}；获取时间：{result["run_at"]}。数据库完整性：{integrity}。缺失日频记录：{gaps}（不插值填补）。</p><table><tr><th>数据集</th><th>标的/序列数</th><th>记录数</th><th>最早获取时间</th></tr>'+rows+'</table>'
 page+='''<h2>使用边界</h2><p>这些数据已经接入本地数据层，尚未加入正式预测模型。原模型不变。财务报告期、公告日期、更新日期分开保存；缺失字段保留空值。宏观月度/季度数据缺少可靠发布日期，不能按统计月份提前用于历史预测。历史估值和财务数据可能经过事后修订。严格时间点查询只允许使用当时已获取的快照。</p><p>行业采用申万一级行业。当前成分股不能直接作为历史成分股；另存分类变更原始历史。行业成交量额单位接口未说明，保留原始值，不转换为人民币金额。财务报表为原始累计口径，不自动当作单季度值。历史估值允许真实负市盈率。</p><p>每日任务会检查更新；24小时缓存避免重复下载。多数来源只支持全表获取，数据库按内容哈希幂等保存并保留版本，不宣称网络请求仅下载新增行。</p><p>来源：<a href="https://akshare.akfamily.xyz/data/stock/stock.html">AKShare股票接口文档</a>、<a href="https://akshare.akfamily.xyz/data/index/index.html">指数接口文档</a>、<a href="https://akshare.akfamily.xyz/data/macro/macro.html">宏观接口文档</a>。数据由东方财富、申万研究公开接口提供。</p>'''
 page+='<h2>数据质量明细</h2><pre>'+html.escape(json.dumps(quality,ensure_ascii=False,indent=2))+'</pre>'
 page+='<h2>本次错误</h2><pre>'+html.escape('\n'.join(errors) or '无')+'</pre>'
 (root/'reports/factors.html').write_text(page)
 return result

if __name__=='__main__':
 if sys.argv[1]=='worker':worker(json.loads(Path(sys.argv[2]).read_text()),Path(sys.argv[3]),Path(sys.argv[4]))
