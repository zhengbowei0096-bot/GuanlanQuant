"""Synthetic regression cases for missing legacy plans, nulls and daily costs."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from asharequant import dynamic_inputs as inputs, dynamic_service as service
from asharequant.paper_account import get,put,digest
from asharequant.intraday import load_state
import test_dynamic_execution as execution_fixtures


class RuntimeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=execution_fixtures.ExecutionTests();self.fixture.setUp();f=self.fixture
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.at=f.at;self.s=copy.deepcopy(f.s)
        self.meta=dict(config=f.c,adaptive_config={},monitor_config=f.cfg,code=service.code_fingerprints(),
                       universe={'600031':'TEST'},anchor='2026-10-20',initial_equity=150000.,basis_note='synthetic fixture')
        (self.root/'data').mkdir();(self.root/'data/calendar.csv').write_text('date\n2026-10-20\n2026-10-21\n2026-10-22\n')
        (self.root/'dynamic_config.json').write_text(json.dumps(f.cfg));(self.root/'intraday_config.json').write_text(json.dumps(f.cfg))
        with service.db_open(self.root) as db:put(db,'meta','account',self.meta);service.persist(db,self.s)

    def cycle(self,source=None,transport_error=None,good=False):
        f=self.fixture;q={**f.q,'volume_shares':10000000}
        plan=copy.deepcopy(f.plan);plan['rows'][0]['target_weight']=.15
        with ExitStack() as stack:
            for name,value in [('now',self.at),('source',source),('observed_bar',{'volume':10000000}),('snapshot',{})]:
                stack.enter_context(patch.object(service,name,return_value=value))
            stack.enter_context(patch.object(service,'collect',side_effect=transport_error,return_value=({'600031':q},{'600031':q})))
            if not transport_error:stack.enter_context(patch.object(service,'quality',return_value=[]))
            stack.enter_context(patch.object(service,'dynamic_plan',return_value=(plan,dict(at=self.at.isoformat(),stocks={'600031':{}})),side_effect=None if good else ValueError('DYNAMIC_MODEL_INPUT_MISSING')))
            stack.enter_context(patch.object(service,'adjust',side_effect=lambda p,*a:(p,{'buy_blocks':{}})))
            return service.cycle(self.root)

    def source(self):return dict(meta={'config':self.fixture.c},predictions={'asof':'2026-10-20'},environment='risk_off')

    def test_null_source_and_null_legacy_plan_persist_failure_then_recover(self):
        r=self.source();r.update(plan=None,predictions=None)
        self.cycle(r)
        report=json.loads((self.root/'reports/dynamic/latest/report.json').read_text())
        self.assertEqual(report['decision_diagnostic']['state'],'BLOCKED')
        self.assertFalse(report['account']['executions']);self.assertFalse(report['account']['orders'])
        self.at+=pd.Timedelta(seconds=30);self.fixture.q['asof']=self.at.isoformat()
        self.cycle(self.source(),good=True)
        report=json.loads((self.root/'reports/dynamic/latest/report.json').read_text())
        self.assertEqual(report['decision_diagnostic']['state'],'RECOVERED')
        self.assertTrue(report['decision_diagnostic']['last_failure_at'])
        self.assertEqual(report['decision_diagnostic']['decision_stocks'],1)
        self.assertFalse(report['account']['executions']) # accepted is never a fill

    def test_transport_timeout_records_real_failure_without_fill(self):
        self.cycle(self.source(),transport_error=TimeoutError('synthetic timeout'))
        with service.db_open(self.root) as db:
            c=next(iter(get(db,'cycles').values()));s=load_state(db)
        self.assertEqual(c['result']['source_errors'][0]['error'],'TimeoutError')
        self.assertEqual(c['checks']['600031'],['QUOTE_SOURCE_UNAVAILABLE'])
        self.assertFalse(s['executions']);self.assertFalse(s['orders'])
        self.assertGreaterEqual(c['source_request_seconds'],0)

    def test_null_quote_timestamp_and_invalid_reference_do_not_crash(self):
        p=self.root/'data/intraday/reference/2026-10-21.json';p.parent.mkdir(parents=True);p.write_text('null')
        self.fixture.q['asof']=None
        self.cycle(self.source())
        with service.db_open(self.root) as db:c=next(iter(get(db,'cycles').values()))
        self.assertFalse(c['quotes']);self.assertFalse(c['quote_age_seconds'])
        self.assertIn('QUOTE_INVALID',{e['error'] for e in c['result']['source_errors']})
        self.assertIn('REFERENCE_INVALID',{e['error'] for e in c['result']['source_errors']})

    def test_no_intraday_cycle_close_resets_only_daily_counters(self):
        with service.db_open(self.root) as db:
            s=load_state(db);s.update(fees=5.,turnover=1000.,total_fees=12.,total_turnover=2000.)
            service.persist(db,s)
        with patch.object(service,'now',return_value=pd.Timestamp('2026-10-21T18:00:00+08:00')),patch.object(service,'evidence',return_value={'bars':{},'states':{}}):
            service.close_day(self.root,'2026-10-21')
            with service.db_open(self.root) as db:before=get(db,'nav')
            service.close_day(self.root,'2026-10-21')
        with service.db_open(self.root) as db:
            s=load_state(db);self.assertEqual(get(db,'nav'),before)
        self.assertEqual(s['fees'],0);self.assertEqual(s['turnover'],0)
        self.assertEqual(s['total_fees'],12);self.assertEqual(s['total_turnover'],2000)
        self.assertEqual(before['2026-10-21']['fees'],0)

    def test_old_counter_correction_append_only_idempotent(self):
        with service.db_open(self.root) as db:
            s=load_state(db);s['fees']=5.;s['turnover']=1000.;service.persist(db,s)
            old={tuple(row[:2]):tuple(row[2:]) for row in db.execute('SELECT * FROM records')}
            service.reconcile_counters(db,s,self.at);service.reconcile_counters(db,s,self.at)
            self.assertEqual(len(get(db,'counter_corrections')),1)
            for (kind,key),(body,checksum) in old.items():
                self.assertEqual(db.execute('SELECT body,sha256 FROM records WHERE kind=? AND key=?',(kind,key)).fetchone(),(body,checksum))
            self.assertEqual(s['cash'],self.s['cash']);self.assertEqual(s['positions'],self.s['positions'])


class IndependentInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'data').mkdir();(self.root/'data/calendar.csv').write_text('date\n2026-10-20\n2026-10-21\n2026-10-22\n')
        self.at=pd.Timestamp('2026-10-21T10:00:00+08:00')
        self.spec=dict(universe=['600031'],candidate={'features':['ret1']})
        self.payload=dict(asof='2026-10-20',generated_at='2026-10-20T18:00:00+08:00',data_versions={'600031':'v'},forecasts=[dict(symbol='600031',close=10.,forecasts={str(h):dict(horizon=h,predicted_return=.01,final_training_last_label_end='2026-10-20',model_parameters=dict(coefficients=[1.],means=[0.],scales=[1.],intercept=0.)) for h in (1,5,20)})])
        with sqlite3.connect(self.root/'data/research_paper.sqlite3') as db:
            db.execute('CREATE TABLE records(kind TEXT,key TEXT,body TEXT,sha256 TEXT,PRIMARY KEY(kind,key))');put(db,'predictions','2026-10-20',self.payload)

    def prepare(self,day='2026-10-20'):
        with patch.object(inputs,'now',return_value=self.at),patch.object(inputs,'recipe',return_value=(self.spec,{},dict(config={},risk_multiplier=1.5))),patch('asharequant.connections.market_environment',return_value={'state':'neutral','asof':day}),patch('asharequant.intraday_inference.model_snapshot',return_value={}):
            return inputs.prepare(self.root,day)

    def test_legacy_plan_and_legacy_nav_not_needed(self):
        r=self.prepare();self.assertEqual(r['status'],'PREPARED')
        loaded=inputs.load(self.root,self.at,'2026-10-20')
        self.assertEqual(loaded['predictions'],self.payload);self.assertNotIn('plan',loaded)
        self.assertFalse(loaded['legacy_plan_required']);self.assertEqual(self.prepare()['status'],'ALREADY_PREPARED')

    def test_null_missing_nonfinite_and_future_parameters_rejected(self):
        for change in ('null','slot','nan','future','columns'):
            p=copy.deepcopy(self.payload);f=p['forecasts'][0]['forecasts']['1']
            if change=='null':p=None
            if change=='slot':p['forecasts'][0]['forecasts'].pop('20')
            if change=='nan':f['model_parameters']['coefficients']=[float('nan')]
            if change=='future':f['final_training_last_label_end']='2026-10-21'
            if change=='columns':f['model_features']=None
            with self.subTest(change=change),self.assertRaises(ValueError):inputs.validate(p,self.spec,self.at,'2026-10-20')

    def test_tampered_future_and_wrong_day_input_rejected(self):
        self.prepare();p=self.root/'data/dynamic/model_inputs/latest.json';pointer=json.loads(p.read_text())
        version=p.parent/'versions'/(pointer['sha256']+'.json')
        with self.assertRaises(ValueError):inputs.load(self.root,self.at,'2026-10-21')
        with self.assertRaises(ValueError):inputs.load(self.root,self.at-pd.Timedelta(hours=1),'2026-10-20')
        data=json.loads(version.read_text());data['environment']='risk_on';version.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'TAMPERED'):inputs.load(self.root,self.at,'2026-10-20')

    def test_new_session_publishes_separate_version_without_rewriting_old(self):
        self.prepare();old=list((self.root/'data/dynamic/model_inputs/versions').glob('*.json'))[0];before=old.read_bytes()
        self.at=pd.Timestamp('2026-10-21T18:00:00+08:00');new=copy.deepcopy(self.payload);new.update(asof='2026-10-21',generated_at=self.at.isoformat())
        with patch('asharequant.research_paper.predict_day',return_value=new) as train:
            self.assertEqual(self.prepare('2026-10-21')['prediction_origin'],'DAILY_ORIGINAL_RESEARCH_TRAINING');train.assert_called_once()
        self.assertEqual(old.read_bytes(),before)
        self.assertEqual(len(list(old.parent.glob('*.json'))),2)

    def test_missing_past_model_never_refitted(self):
        with sqlite3.connect(self.root/'data/research_paper.sqlite3') as db:db.execute('DELETE FROM records')
        with patch('asharequant.research_paper.predict_day') as train,self.assertRaisesRegex(ValueError,'NO_RETROSPECTIVE'):
            self.prepare()
        train.assert_not_called()
