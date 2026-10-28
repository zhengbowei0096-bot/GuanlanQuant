import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from bs4 import BeautifulSoup
from asharequant.paper_account import put,digest
from asharequant.reporting.model_activity import collect, document
from asharequant.daily_bundle import export


class ModelActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'data/research_paper.sqlite3'
        self.path.parent.mkdir()
        self.spec=dict(version='saved-v1',candidate=dict(alpha=100,features=['r5']))
        f=dict(model_parameters=dict(means=[1],scales=[1],coefficients=[.2],intercept=0),
               final_training_last_label_end='2024-01-02',predicted_return=.01,forecast_target_date='2024-01-03')
        self.payload=dict(asof='2024-01-02',generated_at='2024-01-02T18:30:00+08:00',model='saved-v1',
            config=dict(minimum_train=504,training_cap=1260),forecasts=[dict(symbol='600000',name='测试股票',forecasts={'1':f})])
        self.report=dict(version='slot-v2',asof='2024-01-02',research_trial_slots=['600000/1'],accepted_slots=[],
            slot_progress=[dict(slot='600000/1',name='测试股票',status='WAITING',confirmed=0,required=60)],
            research_progress=dict(status='ALREADY_RESEARCHED_SESSION',next_review_at='2024-01-03T18:00:00+08:00'))

    def save(self,payload=None,active=True):
        payload=payload or self.payload
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,key TEXT,body TEXT,sha256 TEXT,PRIMARY KEY(kind,key))')
            put(db,'spec','active',self.spec);put(db,'predictions',payload['asof'],payload)
        if active:
            p=self.root/'reports/active_research/latest/report.json';p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(dict(predictions=payload)))

    def test_count_final_fits_and_preserve_database(self):
        self.save();before=self.path.read_bytes();data=collect(self.root,'2024-01-02')
        self.assertEqual(len(data['days'][0]['rows']),1)
        self.assertEqual(data['active']['date'],'2024-01-02');self.assertEqual(self.path.read_bytes(),before)
        page=document(self.root,self.report,'2024-01-02')
        for text in ('已保存 1 组最终拟合','5日涨跌幅','拟合约束强度 100','原记录未保存最终训练样本数','配置的训练样本下限：504'):
            self.assertIn(text,page)
        self.assertNotIn('实际训练1260',page)

    def test_independent_snapshot_used_without_legacy_plan_or_double_count(self):
        self.save(active=False)
        p=self.root/'data/dynamic/model_inputs';(p/'versions').mkdir(parents=True)
        bundle=dict(available_at='2024-01-02T19:00:00+08:00',spec=self.spec,predictions=self.payload)
        checksum=digest(bundle);(p/'versions'/(checksum+'.json')).write_text(json.dumps(bundle))
        (p/'latest.json').write_text(json.dumps({'sha256':checksum}))
        result=collect(self.root,'2024-01-02')
        self.assertEqual(len(result['days']),1);self.assertEqual(len(result['active']['rows']),1)
        self.assertFalse(result['issues'])
        # A broken independent source cannot silently fall back to the old report.
        (p/'latest.json').write_text(json.dumps({'sha256':'bad'}))
        self.assertIsNone(collect(self.root,'2024-01-02')['active'])

    def test_independent_training_is_visible_without_old_ledger(self):
        p=self.root/'data/dynamic/model_inputs';(p/'versions').mkdir(parents=True)
        bundle=dict(available_at='2024-01-02T19:00:00+08:00',spec=self.spec,predictions=self.payload)
        checksum=digest(bundle);(p/'versions'/(checksum+'.json')).write_text(json.dumps(bundle));(p/'latest.json').write_text(json.dumps({'sha256':checksum}))
        data=collect(self.root,'2024-01-02')
        self.assertEqual(len(data['days']),1);self.assertIsNotNone(data['active']);self.assertFalse(self.path.exists());self.assertFalse(data['issues'])

    def test_eligible_is_not_adopted_and_three_panels(self):
        self.save();page=document(self.root,self.report,'2024-01-02')
        for text in ('可研究试用 1 组','预测实际采用试用方案 0 组','尚未采用这些试用方案','0 / 60','独立预测验证通过 0 组'):
            self.assertIn(text,page)
        soup=BeautifulSoup(page,'html.parser')
        self.assertEqual([s['id'] for s in soup.select('.model-panels>section')],['training','trial','acceptance'])
        self.assertEqual(len(soup.select('input[type=radio]')),3)
        self.assertFalse(any(not t.select('tbody tr') for t in soup.select('table')))

    def test_trial_use_and_active_source_different_date(self):
        self.save()
        p=copy.deepcopy(self.payload);p['asof']='2024-01-03';p['generated_at']='2024-01-03T18:30:00+08:00'
        f=p['forecasts'][0]['forecasts']['1'];f['forecast_target_date']='2024-01-04'
        f['prediction_upgrade']=dict(scope='RESEARCH_TRIAL_ONLY',experiment='test',slot='600000/1',recipe=self.spec['candidate'])
        self.save(p,active=False)
        page=document(self.root,self.report,'2024-01-03')
        for text in ('预测实际采用试用方案 1 组','来源文件采用试用方案 0 组','两个来源日期不同','数据日：2024-01-02'):
            self.assertIn(text,page)

    def test_missing_database_does_not_create_state(self):
        page=document(self.root,self.report,'2024-01-02')
        self.assertFalse(self.path.exists());self.assertIn('尚无封存训练记录',page)
        self.assertNotIn('已保存 1 组',page)

    def test_tampered_record_is_not_training_evidence(self):
        self.save()
        with sqlite3.connect(self.path) as db:db.execute("UPDATE records SET body='{}' WHERE kind='predictions'")
        result=collect(self.root,'2024-01-02')
        self.assertFalse(result['days']);self.assertIn('完整性核对失败',result['issues'][0])

    def test_future_label_and_missing_artifact_not_counted(self):
        p=copy.deepcopy(self.payload);f=p['forecasts'][0]['forecasts']['1']
        f['final_training_last_label_end']='2024-01-03';p['forecasts'][0]['forecasts']['5']={}
        self.save(p);day=collect(self.root,'2024-01-02')['days'][0]
        self.assertEqual(day['rows'],{});self.assertEqual(day['invalid'],2)

    def test_future_data_day_omitted_and_unverified_source_not_used(self):
        self.save();data=collect(self.root,'2024-01-01')
        self.assertFalse(data['days']);self.assertIsNone(data['active'])
        active=self.root/'reports/active_research/latest/report.json'
        p=copy.deepcopy(self.payload);p['forecasts'][0]['forecasts']['1']['predicted_return']=.8
        active.write_text(json.dumps(dict(predictions=p)))
        self.assertIsNone(collect(self.root,'2024-01-02')['active'])

    def test_unknown_recipe_does_not_use_current_parameters(self):
        p=copy.deepcopy(self.payload);p['model']='unknown-version';self.save(p)
        page=document(self.root,self.report,'2024-01-02')
        self.assertIn('原记录未保存可核对的参数方案',page)
        self.assertNotIn('拟合约束强度 100',page)

    def test_daily_export_has_only_entry_and_separate_report(self):
        self.save();r=self.root/'reports/iteration/latest.json';r.parent.mkdir(parents=True);r.write_text(json.dumps(self.report))
        before=self.path.read_bytes()
        with patch('asharequant.daily_bundle.read_watchlist',return_value=pd.DataFrame()),patch('asharequant.daily_bundle.read_snapshot',return_value=None):
            delivered=export(self.root,'2024-01-02',dict(status='SUCCESS'),self.root/'desktop')
        overview=Path(delivered['overview']);text=overview.read_text()
        self.assertIn('模型训练与验证',text)
        for absent in ('model-panels','每日训练：','已到期／所需起点','0 / 60'):
            self.assertNotIn(absent,text)
        link=BeautifulSoup(text,'html.parser').find('a',string='模型训练与验证')['href']
        dedicated=overview.parent/link
        self.assertTrue(dedicated.is_file());self.assertIn('已保存 1 组最终拟合',dedicated.read_text())
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse((self.root/'data/iteration/slot-v2.sqlite3').exists())


if __name__=='__main__':unittest.main()
