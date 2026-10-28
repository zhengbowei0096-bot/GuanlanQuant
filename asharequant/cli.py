from pathlib import Path
import argparse
import json
import logging
import sys

from .core import (now, cutoff, load_config, read_watchlist, run_lock,
                   write_json, read_snapshot, quality, stock_config)
from .data import calendar, update_all, quotes
from .research import evaluate
from .report import build_report


def main(argv=None):
    parser = argparse.ArgumentParser(description='AshareQuant 本地行情与研究系统')
    parser.add_argument('command', choices=['dynamic-inputs','active-research','strategy-experiment','research-paper','risk-plan','paper-account','broker-refresh','public-history','connection-health','prediction-quality','iteration','code-guard','history-refresh','lifecycle', 'strict-validate', 'daily', 'daily-verify', 'strict-audit', 'run', 'report', 'check', 'status', 'database', 'forecast', 'indices', 'index-research', 'factors', 'factor-research', 'model-research', 'risk-research', 'model-monitor', 'decision', 'portfolio-validate', 'connect-refresh', 'connections', 'account-import', 'fees-import', 'fee-observation', 'probability-calibrate', 'execution-replay', 'history-import'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dataset', choices=['all','industry','valuations','financial','macro'], default='all')
    parser.add_argument('--method', choices=['equal_weight','risk_parity','mean_variance','constrained_score'], help='仅选择研究目标，不启用正式交易')
    parser.add_argument('--input', type=Path, help='账户/费用/历史状态JSON输入文件')
    parser.add_argument('--stage', choices=['all','linear','trees'], default='all')
    parser.add_argument('--full', action='store_true', help='强制刷新全部历史')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    (root / 'logs').mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s',
                        force=True, handlers=[logging.StreamHandler(),
                                  logging.FileHandler(root / 'logs' / 'app.log', encoding='utf-8')])
    try:
        if args.command == 'dynamic-inputs':
            from .dynamic_inputs import prepare
            with run_lock(root):result=prepare(root)
            print(json.dumps(result,ensure_ascii=False));return 0
        if args.command == 'active-research':
            from .active_research import run
            with run_lock(root): result=run(root)
            print(json.dumps({k:result.get(k) for k in ('status','asof','equity','cash','alerts')},ensure_ascii=False))
            return 2 if result['status']=='BLOCKED_DATA' else 0
        if args.command == 'strategy-experiment':
            from .strategy_experiment import run
            with run_lock(root): result=run(root)
            print(json.dumps({k:result.get(k) for k in ('status','asof','target_session','snapshot_count','alerts')},ensure_ascii=False))
            return 2 if result['status']=='BLOCKED_DATA' else 0
        if args.command == 'research-paper':
            from .research_paper import run
            with run_lock(root):
                result=run(root)
                from .holding_summary import update
                if result["status"]!="DISABLED":update(root,result)
            print(json.dumps({k:v for k,v in result.items() if k in ('status','equity','cash','alerts','submitted_orders')},ensure_ascii=False))
            return 2 if result['status']=='BLOCKED_DATA' else 0
        if args.command == 'risk-plan':
            from .risk_control import run
            with run_lock(root):result=run(root)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 2 if result['status']=='BLOCKED_DATA' else 0
        if args.command == 'paper-account':
            from .paper_account import run
            with run_lock(root):
                result=run(root)
                from .risk_control import run as risk_plan
                from .research_paper import enabled,run as research_paper
                if enabled(root):
                    research=research_paper(root)
                    from .holding_summary import update
                    update(root,research)
                    from .strategy_experiment import run as compare_strategies
                    if research["status"]=="ACTIVE_RESEARCH_PAPER":
                        compare_strategies(root)
                        from .active_research import run as active_research
                        active=active_research(root)
                        if active["status"]=="BLOCKED_DATA":
                            result["status"]="BLOCKED_DATA"
                            result["alerts"].extend(active["alerts"])
                    if research["status"]=="BLOCKED_DATA":
                        result["status"]="BLOCKED_DATA"
                        result["alerts"].extend(research["alerts"])
                risk_plan(root)
                from .intraday import enabled as intraday_enabled,close_day
                from .dynamic_service import enabled as dynamic_enabled
                if intraday_enabled(root) and not dynamic_enabled(root):
                    intraday_day=json.loads((root/"reports/active_research/latest/report.json").read_text())["asof"]
                    close_day(root,intraday_day)
                    from .adaptive_intraday import enabled as adaptive_enabled,close_day as adaptive_close
                    if adaptive_enabled(root):adaptive_close(root,intraday_day)
            print(json.dumps({k:result[k] for k in ('status','start_session','equity','cash','daily_return','cumulative_return','alerts','submitted_orders')},ensure_ascii=False,indent=2))
            return 2 if result['status']=='BLOCKED_DATA' else 0
        if args.command in ('daily','daily-verify'):
            from .daily import run
            result=run(root,verify=args.command=='daily-verify')
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 2 if result['status']=='FAILED' else 0
        if args.command in ('broker-refresh','public-history','connection-health'):
            with run_lock(root):
                if args.command=='broker-refresh':
                    from .broker_records import ingest
                    result=ingest(root)
                elif args.command=='public-history':
                    from .public_history import refresh
                    result=refresh(root,force=args.full)
                    result={k:v for k,v in result.items() if k not in ('references','crosschecks')}
                else:
                    from .connection_health import run
                    result=run(root)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0
        if args.command == 'prediction-quality':
            from .prediction_quality import run, import_reference
            with run_lock(root):
                if args.input is not None:import_reference(root,args.input)
                result=run(root)
            print(json.dumps({k:result[k] for k in ('asof','predictions','confirmed','pending','trading_effect')},ensure_ascii=False,indent=2))
            return 0
        if args.command == 'status':
            path = root / 'reports' / 'latest_run.json'
            print(path.read_text() if path.exists() else '尚无成功生成的报告')
            return 0
        if args.command=='code-guard':
            from .code_guard import dispatch
            if args.input is None:raise ValueError('code-guard需要JSON操作文件')
            print(json.dumps(dispatch(root,json.loads(args.input.read_text())),ensure_ascii=False,indent=2));return 0
        if args.command=='iteration':
            from .daily_iteration import run
            with run_lock(root):result=run(root)
            print(json.dumps({k:v for k,v in result.items() if k not in ('drift','studies','update_history')},ensure_ascii=False,indent=2))
            return 2 if result['errors'] else 0
        if args.command in ('history-refresh','lifecycle'):
            with run_lock(root):
                if args.command=='history-refresh':
                    from .history_sources import refresh
                    result=refresh(root,force=args.full)
                    from .public_history import refresh as public_refresh
                    supplement=public_refresh(root,force=args.full)
                    result={k:v for k,v in result.items() if k not in ('execution_records','references')}
                    result['supplemental_history']={k:supplement[k] for k in ('symbols','daily_rows','errors','formal_execution_eligible')}
                else:
                    from .lifecycle import run
                    result=run(root)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0
        if args.command == 'strict-validate':
            from .validation_engine import run
            result=run(root)
            print(json.dumps({'status':result['status'],'results':len(result['results']),'errors':result['errors'],'gate':result['formal_gate']},ensure_ascii=False,indent=2))
            return 0
        if args.command == 'strict-audit':
            from .strict_validation import audit
            print(json.dumps(audit(root),ensure_ascii=False,indent=2))
            return 0
        cfg = load_config(root)
        watchlist = read_watchlist(root)
        end = cutoff()
        with run_lock(root):
            if args.command in ('connect-refresh','connections','account-import','fees-import','fee-observation','probability-calibrate','execution-replay','history-import'):
                from . import connections as conn
                if args.command=='connect-refresh': result=conn.refresh_market(root)
                elif args.command=='connections': result=conn.readiness(root)
                elif args.command=='probability-calibrate':
                    from .probability_calibration import run
                    result=run(root)
                elif args.command=='execution-replay':
                    from .execution_replay import run
                    result=run(root)
                else:
                    if args.input is None: raise ValueError('该导入命令需要--input文件')
                    if args.command=='account-import': result=conn.import_account(root,args.input)
                    elif args.command=='fees-import': result=conn.import_fees(root,args.input)
                    elif args.command=='fee-observation': result=conn.import_fee_observation(root,args.input)
                    else:
                        from .execution_replay import import_history
                        result=import_history(root,args.input)
                if args.command=='execution-replay': result={k:v for k,v in result.items() if k!='results'}
                if args.command=='connect-refresh': result={k:v for k,v in result.items() if k not in ('quotes','raw_tencent')}
                print(json.dumps(result,ensure_ascii=False,indent=2))
                return 0
            if args.command == 'model-monitor':
                from .model_monitor import run
                result=run(root)
                from .lifecycle import monitor as monitor_production
                monitor_production(root)
                print(json.dumps({'asof':result['asof'],'active':len(result['active']),'blocked':len(result['blocked'])},ensure_ascii=False))
                return 0
            if args.command == 'decision':
                from .decision import generate
                payload, folder = generate(root, args.method)
                print(json.dumps({'report': str(folder / 'index.html'), 'rows': len(payload['decisions']), 'cash_after': payload['cash_after'], 'submitted_orders': 0, 'blockers': payload['blockers']}, ensure_ascii=False, indent=2))
                return 0
            if args.command == 'portfolio-validate':
                from .portfolio_validation import run
                result = run(root)
                print(json.dumps({'status': result['status'], 'summary': result['summary'], 'formal_method': result['formal_method']}, ensure_ascii=False, indent=2))
                return 0
            cal, cal_meta = calendar(root, cfg, end, offline=args.command not in ('run', 'indices'))
            if args.command == 'risk-research':
                from .risk_models import run
                result, folder = run(root)
                from .model_monitor import run as monitor_models
                monitor_models(root)
                print(json.dumps({'report':str(folder/'index.html'),'approved':result['approved_count'],'fit_failures':len(result['fit_failures'])},ensure_ascii=False))
                return 0
            if args.command == 'model-research':
                from .model_research import run
                result, folder = run(root,args.stage)
                from .model_monitor import run as monitor_models
                monitor_models(root)
                print(json.dumps({'report':str(folder/'index.html'),'summary':result['summary'],'errors':result['errors']},ensure_ascii=False,indent=2))
                return 2 if result['errors'] else 0
            if args.command == 'factor-research':
                from .factor_research import run
                result, folder = run(root)
                print(json.dumps({'report':str(folder/'index.html'),'summary':result['summary']}, ensure_ascii=False, indent=2))
                return 0
            if args.command == 'factors':
                from .factors import update
                result = update(root, args.dataset, args.full)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result['success'] else 2
            if args.command == 'indices':
                from .indices import update_indices
                result = update_indices(root, cfg, end, cal)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result['success'] else 2
            if args.command == 'index-research':
                from .indices import compare_indices
                result = compare_indices(root, cfg, end, cal)
                print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
                return 0
            if args.command == 'forecast':
                from .forecast import generate
                payload, folder = generate(root)
                print(json.dumps({'report': str(folder / 'index.html'), 'asof': payload['asof'], 'errors': payload['errors'], 'plan': payload['plan']}, ensure_ascii=False, indent=2))
                return 2 if payload['errors'] else 0
            if args.command == 'database':
                from .database import sync_database
                result = sync_database(root, cfg, watchlist, end, cal)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return int(any(r['unexplained_missing'] for r in result['symbols']))
            if args.command == 'check':
                rows = []
                for row in watchlist.itertuples():
                    try:
                        snapshot = read_snapshot(root, row.symbol)
                        if snapshot is None:
                            raise ValueError('没有已验证快照')
                        q = quality(snapshot['raw'], cal, stock_config(cfg, row.symbol), end)
                        rows.append({'symbol': row.symbol, **q})
                        print(row.symbol, json.dumps(q, ensure_ascii=False))
                    except Exception as exc:
                        rows.append({'symbol': row.symbol, 'error': str(exc)})
                        print(row.symbol, str(exc))
                write_json(root / 'reports' / 'quality.json', rows)
                return int(any('error' in r or not r['calendar_complete'] for r in rows))
            statuses = update_all(root, cfg, watchlist, end, cal, args.full) if args.command == 'run' else []
            if args.command == 'run' and not any(not s['ok'] for s in statuses):
                from .database import sync_database
                sync_database(root, cfg, watchlist, end, cal)
            quote_error = None
            try:
                quote_map = quotes(root, cfg, watchlist.symbol.tolist(), end, cal,
                                   offline=args.command != 'run')
            except Exception as exc:
                quote_map = {}
                quote_error = str(exc)
            candidates, pool, research, issues = evaluate(root, cfg, watchlist, cal, end, statuses, quote_map)
            if quote_error:
                issues.append({'symbol': '名称核验', 'error': quote_error})
            if args.command == 'run' and statuses and all(s['ok'] for s in statuses) and not quote_error:
                from .indices import update_indices
                index_status = update_indices(root, cfg, end, cal)
                issues.extend({'symbol': s['symbol'], 'error': s['error']} for s in index_status['statuses'] if not s['ok'])
                from .factors import update
                factor_status = update(root)
                issues.extend({'symbol': '扩展数据', 'error': e} for e in factor_status['errors'])
                if factor_status['success']:
                    from .factor_research import run as run_factor_research
                    run_factor_research(root)
                from .model_research import run as run_model_research
                model_result, _ = run_model_research(root)
                issues.extend(model_result['errors'])
                from .risk_models import run as run_risk_research
                risk_result, _ = run_risk_research(root)
                from .model_monitor import run as monitor_models
                monitor_models(root)
                try:
                    from .connections import refresh_market
                    refresh_market(root)
                except Exception as exc:
                    issues.append({'symbol':'七项指标交易状态','error':str(exc)})
                from .lifecycle import run as run_lifecycle
                run_lifecycle(root)
                from .daily_iteration import run as run_iteration
                iteration_result=run_iteration(root)
                issues.extend(iteration_result['errors'])
                from .forecast import generate
                forecast_payload, forecast_folder = generate(root)
                from .decision import generate as generate_decision
                try:
                    from .connections import refresh_market
                    from .probability_calibration import run as calibrate_probabilities
                    calibrate_probabilities(root)
                    generate_decision(root)
                except Exception as exc:
                    logging.exception('第八模块计划生成失败，保留原行情和预测流程')
                    issues.append({'symbol': '交易决策', 'error': str(exc)})
                logging.info('预测及模拟配置报告：%s', forecast_folder / 'index.html')
                issues.extend(forecast_payload['errors'])
            folder = build_report(root, cfg, watchlist, end, cal_meta, statuses,
                                  candidates, pool, research, issues, args.command)
            logging.info('报告已生成：%s', folder / 'index.html')
            if len(pool) < cfg['pool_min']:
                logging.warning('合格观察池不足%d只：当前%d只', cfg['pool_min'], len(pool))
            bad = [s for s in statuses if not s['ok']]
            state = 'partial' if bad or issues else 'success'
            write_json(root / 'logs' / 'last_attempt.json', {
                'at': now().isoformat(), 'state': state, 'updated': len(statuses) - len(bad),
                'failed': len(bad), 'issues': len(issues), 'report': str(folder),
            })
            return 2 if bad or issues else 0
    except Exception as exc:
        if str(exc) == '另一次更新正在运行，请稍后再试':
            logging.warning('%s', exc)
            return 75
        logging.exception('运行未完成')
        write_json(root / 'logs' / 'last_attempt.json', {
            'at': now().isoformat(), 'state': 'failed', 'error': str(exc),
        })
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
