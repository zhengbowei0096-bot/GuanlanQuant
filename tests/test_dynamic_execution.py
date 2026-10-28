"""Synthetic fixtures only. Never market signals or evidence of broker execution."""
import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from asharequant.decision import DEFAULTS
from asharequant.order_engine import seed,step,fee,LiveBrokerUnavailable
from asharequant.intraday import session,save_state
from asharequant.paper_account import put,get,digest
from asharequant.dynamic_service import cycle,db_open,close_day,DEFAULTS as SERVICE
from asharequant.intraday_inference import infer_frame
from asharequant.forecast import FEATURES,features_and_labels,fit_predict

class ExecutionTests(unittest.TestCase):
 def setUp(self):
  self.at=pd.Timestamp('2026-10-21T10:00:00+08:00')
  self.cfg=dict(SERVICE,enabled=True,quote_max_age_seconds=45,book_participation=.01,move_alert_fraction=.05,limit_alert_fraction=.01,notification_enabled=False,maximum_drawdown=.15,minimum_equity=120000)
  self.c={**DEFAULTS,'max_stock':.225,'max_sector':.375,'max_turnover':.45,'max_invested':.9,'fees_verified':True}
  self.s=seed(dict(cash=150000.,positions={},marks={},equity=150000.,previous_close_equity=150000.,peak=150000.,day='2026-10-20',closed_day='2026-10-20',turnover=0.,fees=0.,used_quotes={},conditions={},notification_queue=[],fills_count=0,valuation_at='2026-10-20',valuation_status='VERIFIED_CLOSE'),self.at-pd.Timedelta(hours=1))
  self.q=dict(symbol='600031',name='TEST',source='SYNTHETIC_TEST',price=10.,previous_close=10.,bid=9.99,ask=10.01,bid_size_lots=100000,ask_size_lots=100000,limit_up=11.,limit_down=9.,asof=self.at.isoformat())
  self.plan=dict(environment='risk_off',weights={'600031':.15},edges={'600031':dict(reference_price=10.,predicted_return=.08,uncertainty=.005)},risk_priorities={'600031':1},rows=[dict(symbol='600031',name='TEST',sector='机械')])
 def run_step(self,s=None,seconds=0,q=None,plan=None,checks=None,continuous=True):
  at=self.at+pd.Timedelta(seconds=seconds);q={**(q or self.q),'asof':at.isoformat(),'volume_shares':10000000+seconds*10000}
  return step(s or self.s,plan or self.plan,{'600031':q},checks or {'600031':[]},self.c,self.cfg,at,{'600031':'机械'},continuous)
 def test_accept_then_later_fill_and_idempotence(self):
  s,r=self.run_step();self.assertEqual(len(s['executions']),0);self.assertEqual(next(iter(s['orders'].values()))['status'],'ACCEPTED')
  s,r=self.run_step(s,30);self.assertEqual(len(s['executions']),1);self.assertEqual(s['positions']['600031']['sellable'],0)
  again,_=self.run_step(s,30);self.assertEqual(again,s)
  self.assertAlmostEqual(s['equity']-150000,s['realized_pnl']+s['unrealized_pnl'])
 def test_partial_and_commission_once_per_order(self):
  s,_=self.run_step();q={**self.q,'ask_size_lots':500}
  s,_=self.run_step(s,30,q);o=next(iter(s['orders'].values()));self.assertEqual(o['status'],'PARTIALLY_FILLED');self.assertEqual(o['filled'],500)
  s,_=self.run_step(s,60,q);o=next(iter(s['orders'].values()));self.assertEqual(o['filled'],1000)
  self.assertAlmostEqual(o['fees'],fee(o['notional'],'BUY',self.c,'600031'))
 def test_limit_price_prevents_fill(self):
  s,_=self.run_step();s,_=self.run_step(s,30,{**self.q,'ask':10.03});self.assertFalse(s['executions'])
 def test_cancel_stale_disconnect_and_restart_no_backfill(self):
  s,_=self.run_step();s,r=self.run_step(s,30,checks={'600031':['QUOTE_SOURCE_UNAVAILABLE']});self.assertFalse(s['executions']);self.assertEqual(next(iter(s['orders'].values()))['status'],'CANCELED')
  restored=json.loads(json.dumps(s));restored,_=self.run_step(restored,60);self.assertFalse(restored['executions'])
 def test_timeout_and_lunch_cancel(self):
  s,_=self.run_step();s,_=self.run_step(s,121);self.assertEqual(next(iter(s['orders'].values()))['status'],'CANCELED')
  s,_=self.run_step();s,_=self.run_step(s,30,continuous=False);self.assertFalse(s['executions']);self.assertEqual(next(iter(s['orders'].values()))['status'],'CANCELED')
 def test_invalid_jump_and_future_and_duplicate_quote(self):
  s,_=self.run_step();s,r=self.run_step(s,30,{**self.q,'price':10.8});self.assertIn('ABNORMAL_PRICE_JUMP',r['checks']['600031']);self.assertFalse(s['executions'])
  s,_=self.run_step();at=self.at+pd.Timedelta(seconds=30)
  for ts in [self.at,at+pd.Timedelta(seconds=60)]:
   result,r=step(s,self.plan,{'600031':{**self.q,'asof':ts.isoformat()}},{'600031':[]},self.c,self.cfg,at,{'600031':'机械'})
   self.assertFalse(result['executions'])
 def test_t_plus_one_no_sell_and_real_broker_disabled(self):
  s,_=self.run_step();s,_=self.run_step(s,30);s,_=self.run_step(s,400,plan={**self.plan,'weights':{'600031':0}})
  self.assertFalse(any(o['side']=='SELL' for o in s['orders'].values()))
  with self.assertRaises(RuntimeError):LiveBrokerUnavailable().submit('BUY')
 def test_realized_unrealized_roundtrip(self):
  s,_=self.run_step();s,_=self.run_step(s,30);s['positions']['600031']['sellable']=s['positions']['600031']['shares'] # synthetic next-session entitlement
  sell={**self.plan,'weights':{'600031':0}}
  s,_=self.run_step(s,400,plan=sell);s,_=self.run_step(s,430,plan=sell)
  self.assertEqual(s['positions']['600031']['shares'],0);self.assertAlmostEqual(s['unrealized_pnl'],0);self.assertAlmostEqual(s['equity']-150000,s['realized_pnl'])
 def test_negative_net_edge_no_buy(self):
  p=copy.deepcopy(self.plan);p['edges']['600031']['predicted_return']=.0001
  s,_=self.run_step(plan=p);self.assertFalse(s['orders'])
 def test_previous_session_unsettled(self):
  s=copy.deepcopy(self.s);s['closed_day']='2026-10-19';_,r=self.run_step(s);self.assertEqual(r['status'],'PREVIOUS_SESSION_UNSETTLED')
 def test_risk_exits_t1_and_costs(self):
  s=copy.deepcopy(self.s);s.update(cash=100000,equity=110000,segment_initial_equity=110000,previous_close_equity=110000,positions={'600031':dict(shares=1000,sellable=1000,basis=10000)},marks={'600031':10})
  s,_=self.run_step(s);self.assertEqual(next(iter(s['orders'].values()))['side'],'SELL');s,_=self.run_step(s,30);self.assertTrue(s['executions'])
 def test_no_observed_trading_no_paper_fill(self):
  s,_=self.run_step();at=self.at+pd.Timedelta(seconds=30)
  q={**self.q,'asof':at.isoformat(),'volume_shares':10000000}
  s,_=step(s,self.plan,{'600031':q},{'600031':[]},self.c,self.cfg,at,{'600031':'机械'})
  self.assertFalse(s['executions'])
 def test_risk_plan_cannot_buy_when_model_missing(self):
  from asharequant.order_engine import risk_only_plan
  s=copy.deepcopy(self.s);s.update(cash=130000,equity=150000,positions={'600031':dict(shares=2000,sellable=2000,basis=20000)},marks={'600031':10.})
  p=risk_only_plan(s,{'600031':self.q},self.c,'risk_off')
  self.assertLessEqual(p['weights']['600031'],20000/150000);self.assertFalse(p['edges'])
 def test_all_exchange_session_boundaries(self):
  cal=pd.DatetimeIndex(['2026-10-21'])
  for t,expect in [('09:29:59','OBSERVE_ONLY'),('09:30:00','CONTINUOUS'),('11:30:00','CLOSED'),('13:00:00','CONTINUOUS'),('14:57:00','OBSERVE_ONLY'),('15:05:00','CLOSED')]:
   self.assertEqual(session(pd.Timestamp('2026-10-21T'+t+'+08:00'),cal),expect)
 def test_sqlite_service_restart_and_settlement(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'data/adaptive').mkdir(parents=True);(root/'data/calendar.csv').write_text('date\n2026-10-20\n2026-10-21\n2026-10-22\n')
   (root/'dynamic_config.json').write_text(json.dumps({**SERVICE,'enabled':True}));(root/'intraday_config.json').write_text(json.dumps(self.cfg))
   base=dict(config=self.c,adaptive_config={},universe={'600031':'TEST'})
   with sqlite3.connect(root/'data/adaptive/account.sqlite3') as db:
    db.execute('create table records(kind TEXT,key TEXT,body TEXT,sha256 TEXT,primary key(kind,key))');db.execute('create table current_state(id INTEGER PRIMARY KEY,body TEXT)');put(db,'meta','account',base);save_state(db,self.s)
   r=dict(meta={'config':self.c},predictions={'asof':'2026-10-20','generated_at':'2026-10-20T18:00:00+08:00'},plan=self.plan)
   folder=root/'reports/active_research/latest';folder.mkdir(parents=True);(folder/'report.json').write_text(json.dumps(r))
   def run_at(t):
    q={**self.q,'asof':t.isoformat(),'volume_shares':10000000+(t-self.at).total_seconds()*10000}
    with patch('asharequant.dynamic_service.source',return_value=r),patch('asharequant.dynamic_service.now',return_value=t),patch('asharequant.dynamic_service.collect',return_value=({'600031':q},{'600031':q})),patch('asharequant.dynamic_service.observed_bar',return_value={'volume':q['volume_shares']}),patch('asharequant.dynamic_service.quality',return_value=[]),patch('asharequant.dynamic_service.dynamic_plan',return_value=(self.plan,{'at':t.isoformat()})),patch('asharequant.dynamic_service.snapshot',return_value={}),patch('asharequant.dynamic_service.adjust',side_effect=lambda plan,*args:(plan,{'buy_blocks':{}})):
     return cycle(root)
   self.assertEqual(run_at(self.at)['status'],'RUNNING_PAPER_ONLY');self.assertEqual(run_at(self.at)['status'],'ALREADY_PROCESSED');run_at(self.at+pd.Timedelta(seconds=30));run_at(self.at+pd.Timedelta(seconds=60))
   with db_open(root) as db:
    s=json.loads(db.execute('select body from current_state').fetchone()[0]);self.assertEqual(len(s['executions']),1);self.assertEqual(len(get(db,'model')),2)
   obs=dict(bars={'600031':{'close':10.1}},states={'600031':{'corporate_action_status':'none'}})
   with patch('asharequant.dynamic_service.now',return_value=pd.Timestamp('2026-10-21T18:00:00+08:00')),patch('asharequant.dynamic_service.evidence',return_value=obs):
    self.assertEqual(close_day(root,'2026-10-21')['status'],'SETTLED');self.assertEqual(close_day(root,'2026-10-21')['status'],'ALREADY_SETTLED')
   with db_open(root) as db:self.assertEqual(len(get(db,'nav')),1)

class ModelTests(unittest.TestCase):
 def test_frozen_inference_identical_math_future_history_ignored(self):
  cal=pd.bdate_range('2025-01-01','2026-10-30');at=pd.Timestamp('2026-10-21T10:00:00+08:00');past=cal[cal<pd.Timestamp(str(at.date()))];n=len(past)
  price=10+np.arange(n)*.003+np.sin(np.arange(n))*.01
  h=pd.DataFrame(dict(date=past,open=price,high=price+.1,low=price-.1,close=price,volume=np.full(n,10000.),amount=price*10000))
  frame=features_and_labels(h,past,5);train=frame.dropna();_,params=fit_predict(train,train.iloc[[-1]],10.,FEATURES)
  f=dict(horizon=5,model_parameters=params,final_training_last_label_end='2026-10-20')
  raw=['0']*50;raw[5]='11';raw[33]='12';raw[34]='10';raw[6]='100';raw[37]='11';q=dict(raw_fields=raw,price=11.)
  y,a=infer_frame(h,h,q,cal,FEATURES,f,at)
  x=np.array(list(a['features'].values()));expected=params['intercept']+((x-params['means'])/params['scales'])@np.array(params['coefficients']);self.assertAlmostEqual(y,expected)
  future=h.iloc[[-1]].copy();future['date']=pd.Timestamp('2026-10-22');future['close']=99999
  y2,_=infer_frame(pd.concat([h,future]),h,q,cal,FEATURES,f,at);self.assertEqual(y,y2)
  with self.assertRaises(ValueError):infer_frame(h,h,q,cal,FEATURES,{**f,'final_training_last_label_end':'2026-10-21'},at)
