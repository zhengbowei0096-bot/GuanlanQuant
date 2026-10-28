"""Exchange-session gated, restartable daily pipeline; no broker transport."""
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import pandas as pd
from .core import now, load_config, write_json, run_lock
from .data import calendar


def _run(root, at=None, execute=None, verify=False):
    root=Path(root);at=at or now()
    from .core import TZ
    if at.tzinfo is None: raise ValueError('调度时刻必须包含时区')
    at=at.astimezone(TZ);cfg=load_config(root)
    if not verify and (at.hour,at.minute)<max((18,0),(cfg['schedule_hour'],cfg['schedule_minute'])):
        return dict(status='BEFORE_CLOSE_BUFFER',submitted_orders=0)
    cal,meta=calendar(root,cfg,pd.Timestamp(at.date()),offline=False)
    if verify:
        from .core import cutoff
        eligible=cal[cal <= cutoff(at)]
        if len(eligible)==0: raise ValueError('没有可验收的完整交易日')
        session=eligible[-1].date()
    else: session=at.date()
    if pd.Timestamp(session) not in cal:
        return dict(status='NON_TRADING_DAY',submitted_orders=0)
    (root/'data').mkdir(exist_ok=True);key=str(session)
    table='daily_acceptance' if verify else 'daily_pipeline'
    with run_lock(root/'logs/daily'):
        with sqlite3.connect(root/'data/market.sqlite3') as db:
            db.execute(f'CREATE TABLE IF NOT EXISTS {table} (session TEXT PRIMARY KEY,status TEXT,attempts INTEGER,payload TEXT)')
            old=db.execute(f'SELECT status,attempts,payload FROM {table} WHERE session=?',(key,)).fetchone()
            if not verify and old and old[0]=='SUCCESS': return dict(status='ALREADY_COMPLETED',session=key,submitted_orders=0)
            attempts=(old[1] if old else 0)+1
            db.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?,?)',(key,'RUNNING',attempts,'{}'));db.commit()
            folder=root/('reports/daily_acceptance' if verify else 'reports/daily')/key/str(attempts);folder.mkdir(parents=True,exist_ok=False)
            steps=[]
            stable_inputs=['config.json','forecast_config.json','decision_config.json','watchlist.csv','data/decision_account.json','asharequant/iteration.py','asharequant/lifecycle.py']
            before={name:hashlib.sha256((root/name).read_bytes()).hexdigest() if (root/name).exists() else None for name in stable_inputs}
            def call(command):
                if execute is not None: return execute(command)
                result=subprocess.run([sys.executable,'-m','asharequant.cli',command,'--root',str(root)],cwd=root,capture_output=True,text=True,timeout=14400)
                (folder/(command+'.stdout.txt')).write_text(result.stdout)
                (folder/(command+'.stderr.txt')).write_text(result.stderr)
                return result.returncode
            status='FAILED';error=None
            from .dynamic_service import enabled as dynamic_enabled, close_day as dynamic_close
            dynamic=dynamic_enabled(root)
            account_step='dynamic-inputs' if dynamic else 'paper-account'
            try:
                # Existing run handles data, features, research, monitoring,
                # forecasts and decisions. Subsequent stages settle OOS outcomes.
                for command in ['history-refresh','run',account_step,'lifecycle','strict-validate','portfolio-validate','execution-replay','model-monitor','prediction-quality','strict-audit','connection-health']:
                    code=call(command);steps.append(dict(command=command,exit_code=code))
                    if code: break
                    if command=='run' and execute is None:
                        payload=json.loads((root/'reports/forecasts/latest/forecast.json').read_text())
                        if payload.get('asof')!=key or payload.get('errors'):
                            raise ValueError('当日预测缺失、不完整或日期不一致')
                else: status='SUCCESS'
            except Exception as exc: error=str(exc)
            # Settlement is independent of research success. Its own data and
            # frozen-plan checks remain mandatory; never turn a failed run green.
            if not any(x['command']==account_step for x in steps):
                try:
                    code=call(account_step)
                    steps.append(dict(command=account_step,exit_code=code,independent_recovery=True))
                    if code:status='FAILED'
                except Exception as exc:
                    status='FAILED'
                    steps.append(dict(command=account_step,exit_code=1,independent_recovery=True,error=str(exc)))
                    error=(error+'; ' if error else '')+account_step+':'+str(exc)
            if execute is None:
                if dynamic:
                    try:
                        result_dynamic=dynamic_close(root,key)
                        steps.append(dict(command='dynamic-close',exit_code=0,status=result_dynamic['status']))
                    except Exception as exc:
                        status='FAILED';error=(error+'; ' if error else '')+'DYNAMIC_SETTLEMENT_FAILED:'+str(exc)
                        steps.append(dict(command='dynamic-close',exit_code=1,error=str(exc)))
            after={name:hashlib.sha256((root/name).read_bytes()).hexdigest() if (root/name).exists() else None for name in stable_inputs}
            if before!=after:
                status='FAILED';error='CONFIG_OR_ACCOUNT_CHANGED_DURING_RUN'
            hashes={}
            for relative in ['config.json','forecast_config.json','decision_config.json','watchlist.csv','data/decision_account.json','data/connections/fees/latest.json','data/connections/market/latest.json','data/model_registry.json','data/production_registry.json','reports/lifecycle/latest.json','reports/prediction_quality/latest/report.json','reports/forecasts/latest/forecast.json','reports/decisions/latest/decision.json']:
                source=root/relative
                if source.exists():
                    target=folder/'inputs_and_results'/relative;target.parent.mkdir(parents=True,exist_ok=True)
                    content=source.read_bytes();target.write_bytes(content);target.chmod(0o600);hashes[relative]=hashlib.sha256(content).hexdigest()
            result=dict(mode='ACCEPTANCE' if verify else 'SCHEDULED',status=status,session=key,attempt=attempts,issued_at=at.isoformat(),completed_at=now().isoformat(),steps=steps,error=error,sha256=hashes,calendar=meta,submitted_orders=0,
                        log_directory=str(folder),note='SUCCESS表示流程完成，不表示模型/策略通过正式准入；源行情版本保存在forecast.data_versions')
            write_json(folder/'manifest.json',result)
            db.execute(f'UPDATE {table} SET status=?,payload=? WHERE session=?',(status,json.dumps(result,ensure_ascii=False),key))
            return result


def run(root, at=None, execute=None, verify=False):
    # Delivery is attempted even when data processing fails. It never grants trading authority.
    try:
        result=_run(root,at,execute,verify=True) if verify else _run(root,at,execute)
    except Exception as exc:
        if execute is None:
            try:
                from .daily_bundle import export
                from .core import TZ
                stamp=at or now()
                export(Path(root),str(stamp.astimezone(TZ).date()),dict(status='FAILED',error=str(exc)))
            except Exception:
                import logging
                logging.exception('每日失败报告归档也未成功')
        raise
    if execute is None and result['status'] not in ('BEFORE_CLOSE_BUFFER','NON_TRADING_DAY'):
        from .daily_bundle import export
        from .core import TZ
        session=result.get('session') or str((at or now()).astimezone(TZ).date())
        try:
            with run_lock(Path(root)/'logs/report_delivery'),run_lock(Path(root)):
                pointer=Path(root)/('reports/acceptance_delivery' if verify else 'reports/delivery')/session/'latest.json'
                previous=json.loads(pointer.read_text()) if pointer.exists() else {}
                if result['status']=='ALREADY_COMPLETED' and previous.get('pipeline_status')=='SUCCESS' and Path(previous['overview']).is_file():
                    result['delivery']=previous
                else:
                    delivered=export(Path(root),session,result);delivered['pipeline_status']=result['status']
                    write_json(pointer,delivered);result['delivery']=delivered
        except Exception as exc:
            result=dict(**{k:v for k,v in result.items() if k!='status'},status='FAILED',delivery_error=str(exc))
    return result
