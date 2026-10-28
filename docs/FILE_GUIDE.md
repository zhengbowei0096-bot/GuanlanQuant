# AshareQuant File Guide (文件逐项说明)

Desktop workspace: numbered English categories; runtime paths are retained for services and integrity checks. (桌面按编号英文分类，服务路径与完整性检查保持原位。)

## Project home (项目首页)

These files remain directly visible beside the ten categories. (以下文件与十个分类并列展示，无需展开文件夹。)

- [README.md](../README.md) — What the project does and how to run it. (项目用途与运行方法。)
- [requirements.txt](../requirements.txt) — Dependency versions for installation/reproduction. (安装与复现用依赖版本。)
- [AGENTS.md](../AGENTS.md) — Required rules for future code, documentation and navigation changes. (后续代码、说明和导航同步规则。)

## 00_Start_Here (使用入口)

Start with the guide, daily overview and live account. (先看指南、每日总览和实时账户。)

[Open category (打开分类)](../00_Start_Here%20%28%E4%BD%BF%E7%94%A8%E5%85%A5%E5%8F%A3%29/README.md)

## 01_Reports (报告与收益)

Read the main account, predictions and validation. Archived snapshots keep their original dates. (查看主账户、预测、验证及按日期保存的历史报告。)

[Open category (打开分类)](../01_Reports%20%28%E6%8A%A5%E5%91%8A%E4%B8%8E%E6%94%B6%E7%9B%8A%29/README.md)

## 02_Source (程序源码)

Read modules in execution order; links keep runtime paths and source fingerprints intact. (按数据到运行顺序查看源码，原路径与指纹保留。)

[Open category (打开分类)](../02_Source%20%28%E7%A8%8B%E5%BA%8F%E6%BA%90%E7%A0%81%29/README.md)

### 01_Data (数据获取)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/data.py](../asharequant/data.py) | Data module: data.py (日历、历史行情增量更新、批量更新及报价获取。) |
| [asharequant/worker.py](../asharequant/worker.py) | Data module: worker.py (独立网络工作进程，供主程序限制请求耗时、隔离网络故障。) |
| [asharequant/connections.py](../asharequant/connections.py) | Data module: connections.py (腾讯/新浪等行情交叉检查、停牌信息、账户快照和费用资料导入；不发送真实订单。) |
| [asharequant/history_sources.py](../asharequant/history_sources.py) | Data module: source-bound historical evidence and bounded official-list retries. (来源、时间与校验保留；失败缓存不阻止重试。) |
| [asharequant/public_history.py](../asharequant/public_history.py) | Data module: BaoStock supplemental history with bounded transport retries and verified partial-cache recovery. (仅补充数据；空值显式失败，失败股票重新下载，不把旧快照标成新行情。) |
| [asharequant/factors.py](../asharequant/factors.py) | Data module: public factor snapshots with bounded read-request retries. (保留TLS验证、采集时间和原数据质量检查。) |
| [asharequant/indices.py](../asharequant/indices.py) | Data module: indices.py (指数数据更新、市场环境特征及指数特征研究比较。) |
| [asharequant/compare.py](../asharequant/compare.py) | Data module: compare.py (比较保留的东方财富基准与标准化腾讯数据，检查差异。) |
| [asharequant/data_sources/database.py](../asharequant/data_sources/database.py) | Data module: data_sources/database.py (把校验后的行情快照同步到 SQLite 数据库，避免重复导入。) |
| [asharequant/data_sources/broker_records.py](../asharequant/data_sources/broker_records.py) | Data module: data_sources/broker_records.py (读取本地券商 CSV 导出记录；导入文件不等于实时连接券商。) |
| [asharequant/intraday_data.py](../asharequant/intraday_data.py) | Data module: timestamped dual-source quotes and explicit transport failures. (行情失败记录来源，下一轮重试，时效与交易资料门槛不变。) |
| [asharequant/intraday_events.py](../asharequant/intraday_events.py) | Data module: intraday_events.py (新闻及公告采集、去重、发布时间/首次观察时间记录和规则分类；不等于阅读全部公告全文。) |
| [asharequant/network_retry.py](../asharequant/network_retry.py) | Bounded retries for read-only data requests. (仅临时网络故障有限重试，不重试订单、不忽略证书或数据错误。) |

### 02_Prediction (预测与评分)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/intraday_inference.py](../asharequant/intraday_inference.py) | Research inference: original saved coefficients and feature formulas; current-account risk budget without old plans. (不训练盘中模型、不改风险参数，使用当时可用模型与行情。) |
| [asharequant/forecast.py](../asharequant/forecast.py) | Prediction module: forecast.py (核心收益预测：构建技术特征与未来收益标签、拟合 Ridge、产生预测及基础研究配置。) |
| [asharequant/seven_metrics.py](../asharequant/seven_metrics.py) | Prediction module: seven_metrics.py (汇总七项研究指标，结合九因素计算综合评分并导出结果；评分本身不授予交易资格。) |
| [asharequant/probability_calibration.py](../asharequant/probability_calibration.py) | Prediction module: probability_calibration.py (按时间顺序校准上涨概率，使用独立日期块，检查概率估计是否具有验证依据。) |
| [asharequant/model_candidates.py](../asharequant/model_candidates.py) | Prediction module: model_candidates.py (固定规格的 AR、Lasso、LightGBM、XGBoost 候选模型及已选择模型读取。) |
| [asharequant/risk_models.py](../asharequant/risk_models.py) | Prediction module: risk_models.py (GARCH 波动率与 HMM 市场状态研究、风险比较和协方差调整；通过检查才可应用相应结果。) |
| [asharequant/models/__init__.py](../asharequant/models/__init__.py) | Prediction module: models/__init__.py (统一暴露既有特征、拟合和推理函数；这里没有另一套预测算法。) |

### 03_Decision_and_Risk (决策与风控)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/decision.py](../asharequant/decision.py) | Decision and Risk module: decision.py (组合优化及候选交易计划核心：四种配置方法、费用、现金、单股/行业上限、T+1、股数和交易状态约束。) |
| [asharequant/research_policy.py](../asharequant/research_policy.py) | Decision and Risk module: research_policy.py (研究模拟的仓位分配：市场环境影响总仓位，个股结合预测与风险分配；不赋予正式资格。) |
| [asharequant/adaptive_policy.py](../asharequant/adaptive_policy.py) | Decision and Risk module: adaptive_policy.py (模型输出后的盘中调整：走势、相对表现、波动和事件修正研究判断，保留原始预测、评分和排名。) |
| [asharequant/risk/risk_control.py](../asharequant/risk/risk_control.py) | Decision and Risk module: risk/risk_control.py (独立风险减仓模拟计划，只处理风险卖出方向，不因模型未通过而完全失去风控计划。) |
| [asharequant/strategies/next_session_plan.py](../asharequant/strategies/next_session_plan.py) | Decision and Risk module: strategies/next_session_plan.py (下一交易日意向及其条件说明，把收盘后计划与当下能否成交分开。) |
| [asharequant/strategy_experiment.py](../asharequant/strategy_experiment.py) | Decision and Risk module: strategy_experiment.py (比较不同风险预算和执行阈值的研究方案，冻结对照输入并记录收益、成本及风险；不训练模型。) |

### 04_Execution_and_Ledger (执行与记账)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/paper_account.py](../asharequant/paper_account.py) | Execution and Ledger module: paper_account.py (旧策略历史模拟账户（默认隐藏）：冻结计划、模拟执行、持续账本与收益报告；不操作真实资金。) |
| [asharequant/research_paper.py](../asharequant/research_paper.py) | Execution and Ledger module: research_paper.py (研究模型预测与独立模拟账户：冻结研究计划、跟踪预测到期并生成报告，不替换正式模型。) |
| [asharequant/research_execution.py](../asharequant/research_execution.py) | Execution and Ledger module: research_execution.py (研究模拟执行引擎，按既定风险优先顺序处理减仓，并考虑执行约束。) |
| [asharequant/active_research.py](../asharequant/active_research.py) | Execution and Ledger module: active_research.py (保留的日线研究模拟方案及历史账本，连接研究计划、执行及发布报告。) |
| [asharequant/order_engine.py](../asharequant/order_engine.py) | Execution and Ledger module: order_engine.py (动态模拟委托、稳定整手换算、后续报价撮合、T+1、费用及盈亏；无真实券商通道。) |
| [asharequant/active_execution.py](../asharequant/active_execution.py) | Execution and Ledger module: active_execution.py (日常研究模拟执行及小额买单净优势检查，考虑实际单笔费用是否划算。) |
| [asharequant/intraday.py](../asharequant/intraday.py) | Execution and Ledger module: intraday.py (盘中对照执行；提供仅修正浮点误差的统一整手股数换算，保留交易与风险条件。) |
| [asharequant/adaptive_intraday.py](../asharequant/adaptive_intraday.py) | Execution and Ledger module: adaptive_intraday.py (原动态模拟账户与迁移来源，冻结证据保留；当前主账户由 dynamic_service 管理。) |
| [asharequant/execution_replay.py](../asharequant/execution_replay.py) | Execution and Ledger module: execution_replay.py (按历史交易日重放候选订单，检查费用、涨跌停与交易状态；不能确认成交时不虚构成交。) |

### 05_Validation (验证与迭代)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/backtesting/research.py](../asharequant/backtesting/research.py) | Validation module: backtesting/research.py (固定规则的探索性指标、策略模拟和历史研究，与实际执行层分开。) |
| [asharequant/portfolio_validation.py](../asharequant/portfolio_validation.py) | Validation module: portfolio_validation.py (滚动样本外比较投资组合方法；使用收益标签的代理评估，不能直接证明实际可成交。) |
| [asharequant/strict_validation.py](../asharequant/strict_validation.py) | Validation module: strict_validation.py (时间划分、滚动验证、时点对齐、风险收益指标和正式资格检查的基础工具。) |
| [asharequant/validation_engine.py](../asharequant/validation_engine.py) | Validation module: validation_engine.py (固定规格训练/验证/测试和推理接口；已被查看的历史数据不冒充未触碰测试集。) |
| [asharequant/model_research.py](../asharequant/model_research.py) | Validation module: model_research.py (新旧候选模型的配对历史比较、显著性检验及前瞻影子预测记录。) |
| [asharequant/iteration.py](../asharequant/iteration.py) | Fingerprint-bound candidate search and legacy cadence retained for audit; current CLI scheduling is in daily_iteration.py. (保留原候选算法与旧调度供指纹审计，当前日常调度见 daily_iteration.py。) |
| [asharequant/lifecycle.py](../asharequant/lifecycle.py) | Validation module: lifecycle.py (Champion–Challenger 生命周期：实验冻结、预测到期、独立验收、晋升、资格撤销及正式模型准入。) |
| [asharequant/model_monitor.py](../asharequant/model_monitor.py) | Validation module: model_monitor.py (持续记录预测误差、评估模型状态，必要时限制不再满足要求的模型。) |
| [asharequant/evaluation/prediction_quality.py](../asharequant/evaluation/prediction_quality.py) | Validation module: evaluation/prediction_quality.py (不可随意改写的预测与实际结果记录，计算到期误差及统计质量；本身不是交易开关。) |
| [asharequant/evaluation/factor_research.py](../asharequant/evaluation/factor_research.py) | Validation module: evaluation/factor_research.py (按信息发布时间对齐因子并进行研究比较；诊断回测不直接晋升正式模型。) |
| [asharequant/evaluation/validation_readiness.py](../asharequant/evaluation/validation_readiness.py) | Validation module: evaluation/validation_readiness.py (解释模型还缺哪些验证条件，不降低门槛、不承诺何时必定通过。) |
| [asharequant/evaluation/connection_health.py](../asharequant/evaluation/connection_health.py) | Validation module: evaluation/connection_health.py (汇总数据连接及无人值守流程准备状态，保存检查证据。) |
| [asharequant/daily_iteration.py](../asharequant/daily_iteration.py) | Daily entry for per-slot trials; retains the legacy frozen scheduler. (分组试用的每日入口，保留旧版冻结调度兼容实现。) |
| [asharequant/slot_upgrade.py](../asharequant/slot_upgrade.py) | Per-stock/horizon research trial and immutable prospective acceptance; no trading admission. (分股票与期限研究试用、封存验证，不授予交易资格。) |

### 06_Reporting (报告展示)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/reporting/plain_chinese.py](../asharequant/reporting/plain_chinese.py) | Reporting module: plain_chinese.py (报告中文阅读层，解释委托撤销、数据快照及模型校验状态；不改变原始数值与记录。) |
| [asharequant/reporting/report.py](../asharequant/reporting/report.py) | Reporting module: reporting/report.py (生成主要分析网页、图表和指标展示。) |
| [asharequant/reporting/daily_bundle.py](../asharequant/reporting/daily_bundle.py) | Daily report delivery, verified account returns and dedicated model-activity link; preserves earlier exports in backups. (每日交付与已结算收益，首页仅链接模型专栏，旧报告保留备份。) |
| [asharequant/reporting/holding_summary.py](../asharequant/reporting/holding_summary.py) | Reporting module: reporting/holding_summary.py (从已冻结的研究计划提取现有持仓操作摘要，展示建议股数和依据。) |
| [asharequant/reporting/probability_display.py](../asharequant/reporting/probability_display.py) | Reporting module: reporting/probability_display.py (展示研究上涨概率和未通过原因，避免把研究估计写成已验证概率。) |
| [asharequant/reporting/report_navigation.py](../asharequant/reporting/report_navigation.py) | Reporting module: reporting/report_navigation.py (管理完整总览与动态模拟入口，每30秒同步桌面实时展示及附件，隐藏旧策略；不修改模型或账本。) |
| [asharequant/reporting/dynamic_status.py](../asharequant/reporting/dynamic_status.py) | Reporting module: checksum-verified decision, failure and recovery evidence with transport causes. (空表给出具体原因；休市和重启不当作恢复。) |
| [asharequant/reporting/iteration_status.py](../asharequant/reporting/iteration_status.py) | Current model-activity presentation entry and legacy study status. (当前模型活动专栏入口与旧研究状态兼容展示。) |
| [asharequant/reporting/model_activity.py](../asharequant/reporting/model_activity.py) | Reporting module: verified legacy and independent model snapshots; separate training, trial and acceptance. (按日期去重训练记录，展示当前独立模型来源，不宣称盘中已通过。) |

### 07_Operations (自动运行)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/dynamic_service.py](../asharequant/dynamic_service.py) | Operations module: quote-driven paper execution, durable null/timeout diagnostics and append-only daily counter reconciliation. (独立模型输入、空值与超时留证、按成交日核对费用；历史记录不重写。) |
| [asharequant/cli.py](../asharequant/cli.py) | CLI entry: run, daily, dynamic-inputs and explicit legacy tools. (独立准备盘中模型输入，旧账本命令保留兼容但不作为主账户前提。) |
| [asharequant/mac_alerts.py](../asharequant/mac_alerts.py) | Operations module: mac_alerts.py (独立无声 Mac 弹窗：仅提醒服务异常及恢复，交易事件不弹窗；不调用模型、不修改账本。) |
| [asharequant/scheduler.py](../asharequant/scheduler.py) | Operations module: scheduler.py (本地定时服务唤醒后的检查器：按北京时间和交易日判断是否应运行，记录尝试及结果；不能自行唤醒关机电脑。) |
| [asharequant/daily.py](../asharequant/daily.py) | Operations module: daily research, independent model inputs and independent main-account settlement. (启用动态主账户时不运行旧盘前计划账本；失败仍单独尝试模型输入和结算。) |
| [asharequant/code_guard.py](../asharequant/code_guard.py) | Operations module: code_guard.py (代码实验隔离、测试检查、发布和回滚工具；每日任务不会自行发布未经验证代码。) |
| [asharequant/work_archive.py](../asharequant/work_archive.py) | Operations module: work_archive.py (按工作日期保存运行记录、源码快照和报告关联，供追溯和恢复。) |
| [asharequant/core.py](../asharequant/core.py) | Operations module: core.py (通用基础：北京时间、配置、股票名单、文件锁、数据校验、快照和安全文件写入。) |
| [asharequant/dynamic_inputs.py](../asharequant/dynamic_inputs.py) | Independent sealed model inputs using existing training and risk recipes. (独立封存每日模型，盘中不依赖旧计划，不回填历史预测。) |

### 08_Compatibility (兼容入口)

| File (文件) | Purpose (用途) |
|---|---|
| [asharequant/factor_research.py](../asharequant/factor_research.py) | Compatibility module: factor_research.py (旧导入兼容入口，实际逻辑位于 evaluation/factor_research.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/research.py](../asharequant/research.py) | Compatibility module: research.py (旧导入兼容入口，实际逻辑位于 backtesting/research.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/broker_records.py](../asharequant/broker_records.py) | Compatibility module: broker_records.py (旧导入兼容入口，实际逻辑位于 data_sources/broker_records.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/prediction_quality.py](../asharequant/prediction_quality.py) | Compatibility module: prediction_quality.py (旧导入兼容入口，实际逻辑位于 evaluation/prediction_quality.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/database.py](../asharequant/database.py) | Compatibility module: database.py (旧导入兼容入口，实际逻辑位于 data_sources/database.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/next_session_plan.py](../asharequant/next_session_plan.py) | Compatibility module: next_session_plan.py (旧导入兼容入口，实际逻辑位于 strategies/next_session_plan.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/risk_control.py](../asharequant/risk_control.py) | Compatibility module: risk_control.py (旧导入兼容入口，实际逻辑位于 risk/risk_control.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/__init__.py](../asharequant/__init__.py) | Compatibility module: __init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |
| [asharequant/holding_summary.py](../asharequant/holding_summary.py) | Compatibility module: holding_summary.py (旧导入兼容入口，实际逻辑位于 reporting/holding_summary.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/connection_health.py](../asharequant/connection_health.py) | Compatibility module: connection_health.py (旧导入兼容入口，实际逻辑位于 evaluation/connection_health.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/report_navigation.py](../asharequant/report_navigation.py) | Compatibility module: report_navigation.py (旧导入兼容入口，实际逻辑位于 reporting/report_navigation.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/report.py](../asharequant/report.py) | Compatibility module: report.py (旧导入兼容入口，实际逻辑位于 reporting/report.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/validation_readiness.py](../asharequant/validation_readiness.py) | Compatibility module: validation_readiness.py (旧导入兼容入口，实际逻辑位于 evaluation/validation_readiness.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/probability_display.py](../asharequant/probability_display.py) | Compatibility module: probability_display.py (旧导入兼容入口，实际逻辑位于 reporting/probability_display.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/daily_bundle.py](../asharequant/daily_bundle.py) | Compatibility module: daily_bundle.py (旧导入兼容入口，实际逻辑位于 reporting/daily_bundle.py；两者指向同一模块，保留以兼容旧调用。) |
| [asharequant/reporting/__init__.py](../asharequant/reporting/__init__.py) | Compatibility module: reporting/__init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |
| [asharequant/backtesting/__init__.py](../asharequant/backtesting/__init__.py) | Compatibility module: backtesting/__init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |
| [asharequant/strategies/__init__.py](../asharequant/strategies/__init__.py) | Compatibility module: strategies/__init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |
| [asharequant/evaluation/__init__.py](../asharequant/evaluation/__init__.py) | Compatibility module: evaluation/__init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |
| [asharequant/data_sources/__init__.py](../asharequant/data_sources/__init__.py) | Compatibility module: data_sources/__init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |
| [asharequant/risk/__init__.py](../asharequant/risk/__init__.py) | Compatibility module: risk/__init__.py (Python 包标识，标明该目录属于程序包；不负责独立预测或下单。) |

## 03_Configuration (配置)

Local settings and public examples; do not change risk limits by moving files. (本机配置与公开模板，整理不改变参数。)

[Open category (打开分类)](../03_Configuration%20%28%E9%85%8D%E7%BD%AE%29/README.md)

## 04_Data (数据与账本)

Private runtime data. Keep ledgers and frozen research records intact. (私人运行数据，保留账本和冻结研究证据。)

[Open category (打开分类)](../04_Data%20%28%E6%95%B0%E6%8D%AE%E4%B8%8E%E8%B4%A6%E6%9C%AC%29/README.md)

## 05_Operations (运行与诊断)

Service configuration, health checks and logs. Services keep their existing paths and schedules. (服务配置、健康状态和日志，运行路径与时间不变。)

[Open category (打开分类)](../05_Operations%20%28%E8%BF%90%E8%A1%8C%E4%B8%8E%E8%AF%8A%E6%96%AD%29/README.md)

## 06_Tests_and_Tools (测试与工具)

Tests live in tests/, maintenance commands in scripts/, data comparison and historical acceptance in tools/. Some tools read or write local records. (测试、维护、对比及历史验收分别归类，执行前核对说明。)

[Open category (打开分类)](../06_Tests_and_Tools%20%28%E6%B5%8B%E8%AF%95%E4%B8%8E%E5%B7%A5%E5%85%B7%29/README.md)

## 07_Documentation (说明文档)

Current manuals separated from historical implementation notes. (当前使用说明与历史开发记录分开。)

[Open category (打开分类)](../07_Documentation%20%28%E8%AF%B4%E6%98%8E%E6%96%87%E6%A1%A3%29/README.md)

## 08_Archives_and_Backups (历史与回滚)

Evidence and recoverable changes. Do not confuse backups with active code. (证据与可恢复变更，不作为当前运行代码。)

[Open category (打开分类)](../08_Archives_and_Backups%20%28%E5%8E%86%E5%8F%B2%E4%B8%8E%E5%9B%9E%E6%BB%9A%29/README.md)

## 09_Environment (环境与依赖)

requirements.txt is the basic installation list; config/environments/ keeps optional historical environment versions. (首页保留基础安装清单，历史环境版本集中保存。)

[Open category (打开分类)](../09_Environment%20%28%E7%8E%AF%E5%A2%83%E4%B8%8E%E4%BE%9D%E8%B5%96%29/README.md)

## Maintenance (维护)

Run `python scripts/organize_workspace.py --root .` to preview classification; add `--apply` to refresh it. Unknown root files or Python modules stop the refresh for review. Use `--rollback BACKUP` to restore the previous display and cleaned caches. Only generated navigation and confirmed caches are removed; data, ledgers, source algorithms and risk settings are retained. (先预览，未知文件须补充分类；可恢复原显示和缓存，不删除账本和算法。)
