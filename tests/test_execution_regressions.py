"""Synthetic regressions for lot conversion, pinned history and reviewed upgrades."""
import copy
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from asharequant.core import commit_snapshot
from asharequant.intraday import target_shares, save_state, load_state
from asharequant.order_engine import risk_only_plan, step, seed
from asharequant.intraday_inference import model_snapshot, infer_frame
from asharequant.forecast import FEATURES, features_and_labels, fit_predict
from asharequant.dynamic_service import (DEFAULTS as SERVICE, db_open, persist,
    initialize, approve_upgrade, code_fingerprints)
from asharequant.decision import DEFAULTS
from asharequant.paper_account import put, get, digest


class LotRegressionTests(unittest.TestCase):
    def test_round_trip_noise_only_not_price_tolerance(self):
        self.assertEqual(target_shares(math.nextafter(800., 0), 1., 1.), 800)
        self.assertEqual(target_shares(799.99999, 1., 1.), 700)
        self.assertEqual(target_shares(799., 1., 1.), 700)
        self.assertEqual(target_shares(800., 1., 1.), 800)
        self.assertEqual(target_shares(0., 1., 1.), 0)

    def test_hold_has_no_phantom_sell_but_real_reduction_fills(self):
        at = pd.Timestamp('2026-10-21T10:00:00+08:00')
        # Deliberately find representational noise in entirely synthetic inputs.
        cash = 140000.
        price = next(i/100 for i in range(1000, 2000)
                     if (800*(i/100)/(cash+800*(i/100)))*(cash+800*(i/100))/(i/100) < 800)
        equity = cash + 800*price
        s = seed(dict(cash=cash,positions={'600031':dict(shares=800,sellable=800)},
             marks={'600031':price},equity=equity,previous_close_equity=equity,peak=equity,
             day='2026-10-21',closed_day='2026-10-20',turnover=0.,fees=0.,used_quotes={},
             conditions={},fills_count=0),at)
        q=dict(symbol='600031',name='Synthetic',source='TEST_ONLY',price=price,previous_close=price,
               bid=price,ask=price+.01,bid_size_lots=100000,ask_size_lots=100000,
               limit_down=price*.9,limit_up=price*1.1,asof=at.isoformat(),volume_shares=10000000)
        c={**DEFAULTS,'max_stock':.225,'max_sector':.375,'max_turnover':.45,'max_invested':.9}
        cfg={**SERVICE,'quote_max_age_seconds':45,'book_participation':.01,'maximum_drawdown':.15,
             'minimum_equity':120000,'move_alert_fraction':.05,'limit_alert_fraction':.01}
        p=risk_only_plan(s,{'600031':q},c,'risk_on')
        original=digest(s)
        held,_=step(s,p,{'600031':q},{},c,cfg,at,{})
        self.assertFalse(held['orders']);self.assertEqual(digest(s),original)
        reduced={**p,'weights':{'600031':0.}}
        t=at+pd.Timedelta(seconds=30);q.update(asof=t.isoformat(),volume_shares=11000000)
        pending,_=step(held,reduced,{'600031':q},{},c,cfg,t,{})
        self.assertFalse(pending['executions'])
        t+=pd.Timedelta(seconds=30);q.update(asof=t.isoformat(),volume_shares=12000000)
        filled,_=step(pending,reduced,{'600031':q},{},c,cfg,t,{})
        self.assertEqual(filled['positions']['600031']['shares'],0)
        self.assertEqual(sum(f['shares'] for f in filled['executions']),800)
        self.assertAlmostEqual(filled['equity']-equity,filled['realized_pnl']+filled['unrealized_pnl'])


class PinnedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.at=pd.Timestamp('2026-10-21T10:00:00+08:00');self.generated='2026-10-20T18:00:00+08:00'
        self.cal=pd.bdate_range('2025-01-01','2026-10-22');dates=self.cal[self.cal<=pd.Timestamp('2026-10-20')]
        prices=10+np.arange(len(dates))*.003+np.sin(np.arange(len(dates)))*.01
        self.frame=pd.DataFrame(dict(date=dates,open=prices,high=prices+.1,low=prices-.1,close=prices,volume=100000.,amount=2000000.,turnover=.01))
        self.meta=self.commit(self.frame,'2026-10-20T17:00:00+08:00')
    def commit(self,frame,fetched):
        return commit_snapshot(self.root,'600031',frame,frame,dict(start=str(frame.date.min().date()),end=str(frame.date.max().date()),fetched_at=fetched))
    def read(self,meta=None):
        return model_snapshot(self.root,'600031',(meta or self.meta)['version'],self.generated,self.at)
    def test_latest_refresh_keeps_original_inputs_and_predictions(self):
        frozen=self.read();training=features_and_labels(self.frame,self.cal[self.cal<=pd.Timestamp('2026-10-20')],5).dropna()
        _,params=fit_predict(training,training.iloc[[-1]],10.,FEATURES)
        model=dict(horizon=5,model_parameters=params,final_training_last_label_end='2026-10-20')
        raw=['0']*50;raw[5]='11';raw[33]='12';raw[34]='10';raw[6]='100';raw[37]='11'
        quote=dict(raw_fields=raw,price=11.)
        before=infer_frame(frozen['hfq'],frozen['raw'],quote,self.cal,FEATURES,model,self.at)
        changed=self.frame.copy();changed['close']*=1.005;changed['high']=changed['close']+.2
        latest=self.commit(changed,'2026-10-21T09:00:00+08:00')
        self.assertNotEqual(latest['version'],self.meta['version'])
        snap=self.read();after=infer_frame(snap['hfq'],snap['raw'],quote,self.cal,FEATURES,model,self.at)
        self.assertEqual(before,after);self.assertEqual(snap['meta']['version'],self.meta['version'])
        # Missing/newer latest pointer has no bearing on the frozen reference.
        (self.root/'data/normalized/600031/latest.json').unlink();self.assertEqual(self.read()['meta'],snap['meta'])
    def test_missing_version_never_falls_back_to_latest(self):
        self.commit(self.frame,'2026-10-21T09:00:00+08:00')
        (self.root/'data/normalized/600031/versions'/self.meta['version']/'metadata.json').unlink()
        with self.assertRaisesRegex(ValueError,'MODEL_HISTORY_UNAVAILABLE'):self.read()
    def test_tampered_csv_is_rejected(self):
        (self.root/'data/normalized/600031/versions'/self.meta['version']/'hfq.csv').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'CHECKSUM'):self.read()
    def test_future_and_naive_data_are_rejected(self):
        for fetched in ['2026-10-20T19:00:00+08:00','2026-10-22T09:00:00+08:00','2026-10-20T17:00:00']:
            with self.subTest(fetched=fetched):
                meta=self.commit(self.frame,fetched)
                with self.assertRaisesRegex(ValueError,'HISTORY_NOT_AVAILABLE'):self.read(meta)
    def test_reference_cannot_escape_archive(self):
        for version in ['../latest','0'*31,'A'*32]:
            with self.assertRaisesRegex(ValueError,'INVALID_MODEL_HISTORY_REFERENCE'):
                model_snapshot(self.root,'600031',version,self.generated,self.at)
    def test_wrong_archive_identity_is_rejected(self):
        p=self.root/'data/normalized/600031/versions'/self.meta['version']/'metadata.json'
        m=json.loads(p.read_text());m['symbol']='600875';p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'IDENTITY'):self.read()


class UpgradeReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.at=pd.Timestamp('2026-10-23T18:00:00+08:00');self.cfg={**SERVICE,'enabled':True}
        self.old={n:'0'*64 for n in ('order_engine.py','intraday_inference.py','dynamic_service.py')}
        self.meta=dict(code=self.old,monitor_config=self.cfg,config={'max_stock':.225})
        self.state=dict(day='2026-10-23',closed_day='2026-10-23',orders={},executions=[],order_events=[],cash=150000,equity=150000)
        with db_open(self.root) as db:
            put(db,'meta','account',self.meta);persist(db,self.state)
        for name,value in [('now',self.at),('config',self.cfg),('days',pd.DatetimeIndex(['2026-10-23']))]:
            p=patch('asharequant.dynamic_service.'+name,return_value=value);p.start();self.addCleanup(p.stop)
    def test_review_is_append_only_and_allows_only_exact_code(self):
        with db_open(self.root) as db:
            before=db.execute('SELECT * FROM records ORDER BY kind,key').fetchall()
            with self.assertRaisesRegex(ValueError,'VERSION_CHANGED'):initialize(self.root,db,self.at)
        result=approve_upgrade(self.root,self.old,'a'*64,'Reviewed synthetic regression results')
        self.assertEqual(result['status'],'UPGRADE_REVIEW_RECORDED')
        with db_open(self.root) as db:
            self.assertEqual(initialize(self.root,db,self.at),(self.meta,self.state))
            self.assertEqual(db.execute("SELECT * FROM records WHERE kind!='execution_upgrades' ORDER BY kind,key").fetchall(),before)
            self.assertEqual(load_state(db),self.state)
            with patch('asharequant.dynamic_service.code_fingerprints',return_value={'unknown':'b'*64}):
                with self.assertRaisesRegex(ValueError,'VERSION_CHANGED'):initialize(self.root,db,self.at)
    def test_wrong_base_and_unsettled_or_active_order_block_review(self):
        with self.assertRaisesRegex(ValueError,'BASE_MISMATCH'):approve_upgrade(self.root,{},'a'*64,'test')
        for update in [dict(closed_day='2026-10-22'),dict(orders={'o':{'status':'ACCEPTED'}})]:
            with self.subTest(update=update):
                with db_open(self.root) as db:persist(db,{**self.state,**update})
                with self.assertRaisesRegex(ValueError,'SETTLED'):approve_upgrade(self.root,self.old,'a'*64,'test')
    def test_changed_monitor_configuration_blocks_review(self):
        with patch('asharequant.dynamic_service.config',return_value={**self.cfg,'order_ttl_seconds':180}):
            with self.assertRaisesRegex(ValueError,'CONFIG_CHANGED'):approve_upgrade(self.root,self.old,'a'*64,'test')
    def test_market_hours_and_missing_validation_block_review(self):
        with patch('asharequant.dynamic_service.session',return_value='CONTINUOUS'):
            with self.assertRaisesRegex(ValueError,'CLOSED_SESSION'):approve_upgrade(self.root,self.old,'a'*64,'test')
        with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):approve_upgrade(self.root,self.old,'','test')
    def test_explicit_failed_open_recovery_requires_no_current_session_activity(self):
        at=pd.Timestamp('2026-10-26T09:40:00+08:00')
        with patch('asharequant.dynamic_service.now',return_value=at),patch('asharequant.dynamic_service.days',return_value=pd.DatetimeIndex(['2026-10-23','2026-10-26'])):
            for stamp in ('2026-10-26T09:31:00+08:00','2026-10-27T09:31:00+08:00'):
                with db_open(self.root) as db:persist(db,{**self.state,'last_cycle_at':stamp})
                with self.assertRaisesRegex(ValueError,'NO_CURRENT_SESSION_ACTIVITY'):approve_upgrade(self.root,self.old,'a'*64,'review',recover_failed_open=True)
            with db_open(self.root) as db:persist(db,{**self.state,'last_cycle_at':'2026-10-23T14:55:00+08:00'})
            result=approve_upgrade(self.root,self.old,'a'*64,'review',recover_failed_open=True)
            self.assertEqual(result['status'],'UPGRADE_REVIEW_RECORDED')
            with db_open(self.root) as db:self.assertEqual(next(iter(get(db,'execution_upgrades').values()))['maintenance_mode'],'FAILED_OPEN_RECOVERY')
