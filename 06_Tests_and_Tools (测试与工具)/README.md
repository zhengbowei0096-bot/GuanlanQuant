# 06_Tests_and_Tools (测试与工具)

[Project home (项目首页)](../README.md) · [File guide (文件说明)](../docs/FILE_GUIDE.md)

Tests live in tests/, maintenance commands in scripts/, data comparison and historical acceptance in tools/. Some tools read or write local records. (测试、维护、对比及历史验收分别归类，执行前核对说明。)

Public source and documentation only. Local runtime records remain on your computer. (这里只发布源码与说明，本机运行记录不上传。)

## Files (文件)

| File (文件) | Purpose (用途) |
|---|---|
| [tests/test_daily_iteration.py](../tests/test_daily_iteration.py) | Daily research deduplication, actual-outcome timing, frozen validation, recovery and readable report regressions. (每日研究、时序、冻结验证、恢复与报告回归测试。) |
| [tests/test_active_research.py](../tests/test_active_research.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_adaptive.py](../tests/test_adaptive.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_connections.py](../tests/test_connections.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_connectivity.py](../tests/test_connectivity.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_corporate_ledger.py](../tests/test_corporate_ledger.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_daily_acceptance.py](../tests/test_daily_acceptance.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_daily_bundle.py](../tests/test_daily_bundle.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_database.py](../tests/test_database.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_decision.py](../tests/test_decision.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_dynamic_execution.py](../tests/test_dynamic_execution.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_dynamic_status.py](../tests/test_dynamic_status.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_factor_research.py](../tests/test_factor_research.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_factors.py](../tests/test_factors.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_forecast.py](../tests/test_forecast.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_history_retries.py](../tests/test_history_retries.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_history_sources.py](../tests/test_history_sources.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_holding_summary.py](../tests/test_holding_summary.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_indices.py](../tests/test_indices.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_intraday.py](../tests/test_intraday.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_iteration.py](../tests/test_iteration.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_iteration_null_candidate.py](../tests/test_iteration_null_candidate.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_layout.py](../tests/test_layout.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_lifecycle.py](../tests/test_lifecycle.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_mac_alerts.py](../tests/test_mac_alerts.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_model_activity.py](../tests/test_model_activity.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_model_candidates.py](../tests/test_model_candidates.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_model_monitor.py](../tests/test_model_monitor.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_network_recovery.py](../tests/test_network_recovery.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_next_session_plan.py](../tests/test_next_session_plan.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_paper_account.py](../tests/test_paper_account.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_plain_chinese.py](../tests/test_plain_chinese.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_prediction_quality.py](../tests/test_prediction_quality.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_real_fees.py](../tests/test_real_fees.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_report_navigation.py](../tests/test_report_navigation.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_research_paper.py](../tests/test_research_paper.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_research_policy.py](../tests/test_research_policy.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_risk_control.py](../tests/test_risk_control.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_risk_models.py](../tests/test_risk_models.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_runtime_recovery.py](../tests/test_runtime_recovery.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_seven_metrics.py](../tests/test_seven_metrics.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_slot_upgrade.py](../tests/test_slot_upgrade.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_strategy_experiment.py](../tests/test_strategy_experiment.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_strict_validation.py](../tests/test_strict_validation.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_system.py](../tests/test_system.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_work_archive.py](../tests/test_work_archive.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [tests/test_workspace_organization.py](../tests/test_workspace_organization.py) | Regression and integrity checks, run with unittest. (回归与完整性检查。) |
| [scripts/init_config.py](../scripts/init_config.py) | Configuration initialization and workspace organization. (配置初始化与工作区整理。) |
| [scripts/organize_workspace.py](../scripts/organize_workspace.py) | Configuration initialization and workspace organization. (配置初始化与工作区整理。) |
| [tools/decision_example.py](../tools/decision_example.py) | Data comparison, historical acceptance tools and decision examples; run modules from the project root. (数据对比、历史验收与示例，均从项目根目录运行。) |
| [tools/verify_stage1.py](../tools/verify_stage1.py) | Data comparison, historical acceptance tools and decision examples; run modules from the project root. (数据对比、历史验收与示例，均从项目根目录运行。) |

## Validation_Tools (对比与验收)

| File (文件) | Purpose (用途) |
|---|---|
| [tools/compare_sources.py](../tools/compare_sources.py) | Compare preserved historical source snapshots; needs local watchlist and data. Run from the project root with python -m tools.compare_sources. (历史来源对比，不是实时第二行情源。) |
| [tools/verify_factors.py](../tools/verify_factors.py) | Historical factor acceptance: cache idempotency, first-observed time and original feature count. Reads/writes local data and reports. (历史因子验收，有固定日期假设，运行前核对。) |
| [tools/verify_models.py](../tools/verify_models.py) | Historical model comparison acceptance: time splits, forecast replay and shadow records. Requires existing comparison results. (模型对比历史验收，需要已有本地报告。) |
| [tools/verify_risk_models.py](../tools/verify_risk_models.py) | Historical risk-model acceptance: training dates, shadow records and account consistency. Writes local evidence. (历史风险模型与账户一致性验收，不是盘中交易入口。) |

## Regression_Tests (回归测试)

| File (文件) | Purpose (用途) |
|---|---|
| [tests/test_execution_regressions.py](../tests/test_execution_regressions.py) | Synthetic tests for lot rounding, immutable model history, time guards and append-only execution upgrades. (股数取整、历史快照、时间校验与追加升级审核测试。) |
