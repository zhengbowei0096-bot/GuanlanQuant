import unittest,tempfile,shutil,sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import pandas as pd
from asharequant.daily import run
from asharequant.scheduler import due
from asharequant.core import TZ
ROOT=Path(__file__).resolve().parents[1]
class AcceptanceTests(unittest.TestCase):
 def test_dynamic_daily_does_not_require_legacy_account_plan(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);shutil.copy(ROOT/'config.json',root/'config.json');(root/'dynamic_config.json').write_text('{"enabled":true}')
   for failure in (False,True):
    commands=[]
    def execute(command):
     commands.append(command);return 2 if failure and command=='run' else 0
    with patch('asharequant.daily.calendar',return_value=(pd.DatetimeIndex(['2026-10-20']),{})):
     result=run(root,datetime(2026,10,20,19,tzinfo=TZ),execute,verify=True)
    self.assertNotIn('paper-account',commands);self.assertEqual(commands.count('dynamic-inputs'),1)
    self.assertEqual(result['status'],'FAILED' if failure else 'SUCCESS')
 def test_acceptance_separate_from_scheduled_and_repeated(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);shutil.copy(ROOT/'config.json',root/'config.json')
   at=datetime(2026,10,20,7,tzinfo=TZ)
   with patch('asharequant.daily.calendar',return_value=(pd.DatetimeIndex(['2026-10-16','2026-10-19','2026-10-20']),{})):
    a=run(root,at,lambda _:0,verify=True);b=run(root,at,lambda _:0,verify=True)
    self.assertEqual(a['session'],'2026-10-19');self.assertEqual(a['issued_at'],at.isoformat());self.assertEqual(b['attempt'],2)
    self.assertEqual(run(root,at,lambda _:self.fail('early'))['status'],'BEFORE_CLOSE_BUFFER')
   with sqlite3.connect(root/'data/market.sqlite3') as db:
    self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='daily_pipeline'").fetchone()[0],0)
 def test_weekend_uses_completed_session(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);shutil.copy(ROOT/'config.json',root/'config.json')
   with patch('asharequant.daily.calendar',return_value=(pd.DatetimeIndex(['2026-10-16']),{})):
    r=run(root,datetime(2026,10,18,19,tzinfo=TZ),lambda _:0,verify=True)
    self.assertEqual(r['session'],'2026-10-16')
 def test_beijing_trigger_before_and_after_london_dst(self):
  cfg={'schedule_hour':18,'schedule_minute':0}
  for day,hour in [(20,10),(27,10)]:
   utc=datetime(2026,10,day,hour,tzinfo=ZoneInfo('UTC'))
   self.assertTrue(due(utc,{},cfg))
   self.assertFalse(due(utc.replace(hour=9,minute=59),{},cfg))
   self.assertFalse(due(utc,{'success_date':str(utc.date())},cfg))
