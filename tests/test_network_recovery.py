"""Download retries preserve validation and never relabel stale data as fresh."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import pandas as pd
import requests
from asharequant.network_retry import retry_read,request_read
from asharequant import public_history as history
from asharequant.history_sources import _save


class NetworkRecoveryTests(unittest.TestCase):
    def test_timeout_retry_then_success_preserves_attempt_evidence(self):
        events=[];read=Mock(side_effect=[requests.exceptions.ReadTimeout(),{'real':'data'}])
        with patch('asharequant.network_retry.time.sleep'):
            self.assertEqual(retry_read(read,events=events),{'real':'data'})
        self.assertEqual(read.call_count,2);self.assertEqual(events,[{'attempt':1,'error':'ReadTimeout','retry':True}])

    def test_exhausted_retries_raise_and_do_not_invent_data(self):
        read=Mock(side_effect=subprocess.TimeoutExpired('synthetic download',50));events=[]
        with patch('asharequant.network_retry.time.sleep'),self.assertRaises(subprocess.TimeoutExpired):retry_read(read,events=events)
        self.assertEqual(read.call_count,2);self.assertFalse(events[-1]['retry'])

    def test_validation_certificate_and_authorization_failures_not_retried(self):
        for error in (ValueError('INVALID_OHLC'),requests.exceptions.SSLError('certificate'),RuntimeError('API_REJECTED:403')):
            read=Mock(side_effect=error)
            with self.subTest(error=type(error).__name__),self.assertRaises(type(error)):retry_read(read)
            self.assertEqual(read.call_count,1)

    def test_http_retry_only_read_methods_and_preserve_tls_timeout(self):
        transient=Mock(status_code=503);ok=Mock(status_code=200);original=Mock(side_effect=[transient,ok])
        with patch('asharequant.network_retry.time.sleep'):
            self.assertIs(request_read(original,None,'GET','https://example.test',verify=True,timeout=(8,20)),ok)
        transient.close.assert_called_once();self.assertEqual(original.call_args.kwargs,{'verify':True,'timeout':(8,20)})
        post=Mock(return_value=transient);self.assertIs(request_read(post,None,'POST','https://example.test'),transient);post.assert_called_once()

    def test_worker_transport_stderr_retry_but_not_data_errors(self):
        for message,count in [('ReadTimeout: download',2),('source identity mismatch',1)]:
            read=Mock(side_effect=RuntimeError(message))
            with patch('asharequant.network_retry.time.sleep'),self.assertRaises(RuntimeError):retry_read(read)
            self.assertEqual(read.call_count,count)

    def test_partial_history_cache_retries_failed_symbols_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);at=pd.Timestamp('2026-10-21T18:00:00+08:00')
            row=dict(code='sh.600031',date='2026-10-21',open='10',high='11',low='9',close='10',adjustflag='3',tradestatus='1',isST='0')
            with patch('asharequant.history_sources.now',return_value=at):
                ref=_save(root,'baostock_daily',{'symbol':'600031'},[row],'BaoStock')
            old=dict(asof='2026-10-21',fetched_at=at.isoformat(),references=[ref],crosschecks={'600031':dict(status='MATCHED',stale_for_requested_asof=False)},errors=[dict(symbol='600036',error='TimeoutExpired')])
            pointer=root/'data/history/baostock/latest.json';pointer.parent.mkdir(parents=True);pointer.write_text(json.dumps(old))
            watch=pd.DataFrame([{'symbol':'600031'},{'symbol':'600036'}]);second={**row,'code':'sh.600036'}
            with patch.object(history,'now',return_value=at),patch.object(history,'cutoff',return_value=pd.Timestamp('2026-10-21')),patch.object(history,'read_watchlist',return_value=watch),patch.object(history,'fetch',return_value={'daily':[second],'errors':[]}) as fetch,patch.object(history,'crosscheck',return_value={'status':'MATCHED'}):
                result=history.refresh(root)
            self.assertEqual(fetch.call_count,1);self.assertEqual(fetch.call_args.args[1],'600036')
            self.assertFalse(result['errors']);self.assertEqual(result['symbols'],2)
            self.assertIn(ref,result['references']) # original timestamp/checksum retained

    def test_missing_fields_remain_explicit_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(history,'read_watchlist',return_value=pd.DataFrame([{'symbol':'600031'}])),patch.object(history,'fetch',return_value={'daily':None}):
                # Null data must produce a visible failure rather than an empty success.
                result=history.refresh(Path(d))
            self.assertTrue(result['errors']);self.assertEqual(result['symbols'],0)
