"""Bounded retries for read-only data downloads, never order submissions."""
import logging
import subprocess
import time
import requests


def transient(exc):
    if isinstance(exc,requests.exceptions.SSLError):return False
    if isinstance(exc,(requests.exceptions.Timeout,requests.exceptions.ConnectionError,subprocess.TimeoutExpired,TimeoutError,ConnectionError)):
        return True
    # Child workers expose transport failures via stderr, not live exceptions.
    message=str(exc)
    return isinstance(exc,RuntimeError) and not any(s in message for s in ('SSLError','CERTIFICATE_VERIFY_FAILED')) and any(
        s in message for s in ('ReadTimeout','ConnectTimeout','ConnectionResetError','RemoteDisconnected','Connection aborted','ConnectionError','TimeoutExpired'))


def retry_read(operation,attempts=2,events=None):
    for attempt in range(attempts):
        try:return operation()
        except Exception as exc:
            retry=attempt+1<attempts and transient(exc)
            if events is not None:events.append(dict(attempt=attempt+1,error=type(exc).__name__,retry=retry))
            if not retry:raise
            logging.warning('数据请求暂时中断，进行第 %d 次有限重试（%s）',attempt+1,type(exc).__name__)
            time.sleep(attempt+1)


def request_read(original,session,method,url,**kwargs):
    if method.upper() not in ('GET','HEAD'):return original(session,method,url,**kwargs)
    def one():
        response=original(session,method,url,**kwargs)
        if response.status_code in (429,500,502,503,504):
            response.close()
            raise requests.exceptions.ConnectionError('TEMPORARY_HTTP_STATUS:'+str(response.status_code))
        return response
    return retry_read(one)
