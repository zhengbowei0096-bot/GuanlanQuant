# 本次整理验收

本次未调整预测算法、风险阈值和交易规则。与旧 Git 快照相比的差异还包含此前已在本地运行的功能；本次整理的行为基准是整理前的实际运行项目。

| 检查 | 结果 |
|---|---|
| 整理前原有测试 | 374 通过 |
| 整理后与实际部署后 | 各 377 通过（新增导入兼容、初始化不覆盖、嵌套归档检查） |
| 模块导入 | 75 个模块可导入 |
| CLI | `python -m asharequant.cli --help` 成功 |
| 14 个移动模块 | AST 比较一致，仅相对导入层级变化 |
| 39 个未迁移核心文件 | 与运行基准逐字节一致 |
| 真实历史缓存复算 | 相同特征、10 条预测、拟合参数完全一致 |
| 模型/风险模型/模拟引擎指纹 | 前后完全一致 |
| 本地配置及调度配置 | 保持不变 |
| 文档链接与 Git 空白检查 | 通过 |

没有把研究模型重新注册为正式模型，没有重新结算账本，没有执行真实下单。本次没有完整联网重跑每日流水线或在开盘期间验证成交，也没有完成全新机器安装验收。现有测试包含时间序列泄漏、交易费用、模拟执行、调度与报告路径检查，但不代表穷尽所有错误。

## 维护与恢复

部署前对所有替换文件及缓存建立 `backups/organization-时间/before.tar.gz`，同目录 `manifest.json` 记录替换、新增和缓存删除清单。回滚时应先暂停本地服务，在备份恢复前检查归档路径；恢复 replaced 文件，移除本次 added 文件，再恢复服务和运行测试。不要覆盖随后发生变化的数据、配置和账本。缓存可由 Python 自动重建。

可生成的缓存与有价值的研究产物分开处理：本次只清理 Python 字节码及系统缓存；数据、日志、报告、研究记录、历史备份未删除。没有证据认定无用的旧脚本保留。

尚存技术债务：源文件指纹与物理目录耦合；部分模块仍较大；券商导入适配限定华福；根目录兼容入口暂时存在；跨平台安装及完整环境锁定需进一步验收。未指定项目许可证，需要权利人作出选择。


报告保留规则变更（2026-10-21 北京时间）：报告导出相关10项测试通过，包含跨午夜选取、备份内容、重复清理、跨日期隔离及不完整导出保护。未改动预测或模拟账本算法。旧桌面副本可按 backups/desktop_report_versions 内恢复清单移回原日期目录。

## 2026-10-21 行情驱动执行升级

本次新增测试覆盖后续报价撮合、部分成交累计佣金、无新增成交量不撮合、限价、T+1、断线/撤单、冷却、幂等、风险退出、PnL恒等式、SQLite重启和收盘一次结算、保存系数推理与未来数据截断。合成数据仅用于测试。

原30只股票90组已发布预测用原参数重放：最大数值差0；该检查不等于盘中效果通过。闭市公开行情连接检查30/30腾讯、30/30新浪返回，本次请求约1.35秒，返回上一交易日报价，不能据此交易；供应商实际更新频率及端到端交易时段延迟尚待首个盘中验证。无券商连接测试或真实下单测试。

本次完整回归：源码目录396项通过（4.231秒），桌面运行目录396项通过（3.842秒）。最终导航链接修复另执行4项导航测试通过。78个子模块导入、94个导航目标和导出报告相对链接检查通过。浏览器file协议被安全策略禁止，未完成浏览器截图验收。


## 无声 Mac 弹窗提醒
独立 `asharequant/mac_alerts.py` 每30秒读取动态模拟提醒与健康状态，不调用语言模型，不修改账本。仅服务异常及恢复触发无声对话框；模拟买入、卖出、成交、撤单/拒单不弹窗，仍保留报告与账本记录。委托与成交分别显示；同订单更新合并，超过5分钟注明历史。重复事件按ID抑制，连续两次研究推理异常才提醒；交易时段健康超过120秒未更新提醒一次，恢复再提醒一次。
对话框120秒后自动关闭；电脑须开机、用户登录且桌面可用，离线或休眠不能保证及时提醒。投递状态独立保存在 `logs/mac_alerts/`，失败重试；崩溃后可能重复提醒，不重复交易。系统接受弹窗不等于用户已经阅读。
启动：`python -m asharequant.mac_alerts --root .`。服务为 `com.asharequant.mac-alerts`，独立于行情、模型和18点每日分析；停用此服务仅停止本地弹窗。聊天轮询仅在弹窗人工确认后暂停，18点任务保留。
验证（2026-10-21）：7项通知逻辑测试通过，涵盖去重、部分成交数量、历史卖出、异常/恢复、持续异常、过期健康和无声调用；用户确认无声对话框可见。尚未用真实盘中买卖事件验收。回滚：停止本地提醒服务并恢复聊天轮询，交易算法及账本无须恢复。

2026-10-21 用户更新：关闭所有交易事件弹窗，仅保留异常及恢复提醒；聊天轮询保持暂停，18点分析不变。交易事件仍标记已处理，避免旧消息补发。


2026-10-23：单一主账户展示验证。报告中文阅读层10项、每日导出及收益读取15项、导航4项测试通过。覆盖只读读取已冻结主账本、哈希篡改拒绝、日期截断、旧券商记录不混入、无账本不创建、未结算不填零、旧空表引用本次归档、金额与百分比展示不改原值、原始文件不改写、链接目标及最终导出哈希。验证仅针对报告和数据读取，不代表重新验证预测模型或盘中成交。
回滚：恢复变更前报告模块和文档副本；旧归档只恢复展示 HTML，不回滚或重写账户账本、预测及成交。


2026-10-23 workspace organization: 5 isolated maintenance tests passed (read-only input preservation, link validity, safe cache removal and restore, repeatability, refusal of unclassified/edited files, and path traversal rejection). Runtime import and path checks are recorded separately in the local organization verification record; this is not a new prediction or trading qualification.

2026-10-23 runtime workspace checks: 54 related tests passed; all 81 Python modules imported; all 283 category links and source-guide targets resolved; six installed service configurations retained valid paths. The command entry and two report-launcher shell scripts passed checks. Core model/execution files and local trading configuration contents were unchanged. Finder hides the compatibility root entries; ten categorized folders remain visible. These checks do not revalidate live market inputs or strategy quality.

## 2026-10-23 Source publication (源码同步验收)

- 保留远程已有的 GuanlanQuant 项目展示名与仓库链接，运行包继续为 `asharequant`。
- 完整自动化测试：425 项通过。81 个 Python 模块导入成功，3 个命令帮助入口通过。发布源码与桌面运行项目的 81 个模块逐字节一致，预测、风控和执行算法未因发布修改。
- 344 个本地文档链接解析通过；Markdown 文件逐项说明可在 GitHub 直接点入源码，HTML 说明供本地浏览器使用。
- 干净源码副本初始化生成 13 个本地配置/观察池文件，重复初始化不覆盖；动态服务默认关闭，配置文件名已统一为 `dynamic_config.json`。可生成十类工作区、116 个有效链接，未创建账户数据库或报告。
- 测试中的账户格式样例全部使用虚构数值。检查发布清单及待发布提交历史中的密钥、本机路径、账户标识、已知私人值和本地运行产物；安全检查不代表能识别任意未知秘密。
- 本次没有联网重跑行情/每日研究，没有改写账户账本，没有新做盘中成交或全新环境依赖安装验收。

恢复：使用发布前源码备份或 Git 中的上一版本恢复文档、模板和工具；工作区分类使用 `organize_workspace.py --rollback`。不得把代码回滚当成账户回滚，不覆盖冻结成交和收益。新生成配置名修正只影响新安装，已有私人配置内容不变。

## 2026-10-23 Public category navigation (公开分类验收)

- 完整自动化测试：429 项通过，其中 9 项工作区测试覆盖公开导航过滤、干净克隆初始化、恢复重建、编辑保护和分类完整性。
- 174 个公开文件（含十个分类 README）；596 个 Markdown/HTML 相对链接通过，没有失效目标。公开分类内容由审核清单生成，与本机私人文件增减无关。
- 81 个程序模块可导入，3 个命令帮助入口通过；所有程序模块与桌面运行版逐字节一致，没有移动源码、改变模型、策略、风控、账本或服务时间。
- 干净源码副本初始化生成 13 个本地配置/观察池文件，重复初始化不覆盖；动态服务默认关闭。十类目录、116 个有效本地链接可以生成、回滚再重建，174 个公开文件均未被改变，也未创建账户或报告。
- 十类目录共 60 项本地生成物排除检查通过；只有公开 README 可提交，私人清单、启动器、链接、账户与报告仍被排除。源码和待发布内容的敏感模式检查无命中；这不构成对任意未知秘密的识别保证。
- 本次验证不包含全新机器安装依赖、联网每日运行、盘中成交或真实券商接入。本节记录本地验收，远程发布须另行核对提交编号。

恢复：通过 Git 恢复维护工具、分类定义与说明；本机分类使用组织脚本生成的备份进行回滚。保留后续发生的私人数据变化，不恢复或改写账户账本。

## 2026-10-23 Homepage visibility (首页入口验收)

- 本次仅调整根目录显示与说明：README、requirements.txt、AGENTS.md 与十个分类并列可见；README 增加安装、架构、文件说明、安全与验证快捷入口。
- 15 项相关测试通过：工作区 11 项及目录/初始化兼容性 4 项；覆盖旧隐藏标记清除、重复刷新、回滚和未审核文件阻断。
- 616 个 Markdown/HTML 本地链接目标检查通过，安装页内锚点存在；81 个程序模块与桌面版本字节一致。未重跑交易、模型或实盘验收，历史完整测试结果不替代本次验证。
- 恢复：使用本次整理备份回滚 Finder 显示；说明和整理工具可通过 Git 恢复。无需调整配置参数、任务或账户。

## 2026-10-23 Root utilities cleanup (根目录工具验收)

- 18 项相关测试通过：工作区、初始化/导入兼容及运行归档；新增验证覆盖工具入口转发与新位置环境文件入档，私人账户不入源码快照。
- 四个重复启动入口删除；四个工具和三份环境清单的迁移前后内容哈希一致，保留原验证逻辑与依赖版本。CLI run/check 的帮助入口可用；工具模块可定位并通过语法检查。
- 80 个未涉及的程序模块内容完全一致；唯一程序改动为 work_archive.py 增补环境文件的归档匹配路径，未改模型、风险、预测、交易或任务配置。
- 170 个公开文件、622 个本地文档链接检查通过。未运行会读取账户、联网或改写研究证据的历史验收脚本；本次不是盘中、策略或全新环境安装验收。
- 回滚：恢复本次 Git 前版本或本机迁移备份，再用匹配版本的工作区分类刷新；保留期间新增账户记录，不把工作区显示回滚当成文件迁移回滚。

## Execution regression verification — 2026-10-23

本次修复验证：完整自动化测试445项通过，其中新增12项覆盖浮点整手边界、保持持仓无误触发、真实减仓仍可后续成交、锁定历史版本、刷新最新指针后的推理一致性、缺失/篡改/未来/无时区快照拒绝，以及执行版本追加审核与拒绝未经审核升级。原测试文件未改写。

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p 'test_execution_regressions.py' -v
```

原训练、特征、预测、概率校准、策略和风险参数没有修改。另在本地对保存的实际行情做只读回放并核对原参数公式；私人行情明细、账本、配置和回放结果不发布。未进行真实券商成交验收，也未证明下一交易时段会通过全部行情或公司行为校验；此类数据门槛保持原样。

## Daily model research and progress report — 2026-10-23

460 automated tests passed, including 15 new checks for same-session deduplication, new mature outcomes, future-confirmation rejection, primary-issuance counting, data-error recovery, frozen-experiment preservation, interrupted candidate preparation, checkpoint tampering, report empty states and localized Beijing timestamps on macOS. Original candidate search, feature/prediction formulas, independent acceptance gates and risk settings are unchanged. Tests of the scheduler use isolated fixtures; they do not establish a candidate's predictive advantage or formal eligibility.

Run `python -m unittest discover -s tests -q` to repeat regression checks. Run `python -m asharequant.cli iteration --root .` to evaluate locally available real evidence under the same exclusive update lock. It writes a new research snapshot and progress page, never replaces historical reports or account records. Completed daily checkpoints are checksum-verified; do not edit them to force a second search. Repeated same-day runs reuse results and may resume candidate preparation.

For rollback, restore the previous CLI/report sources and navigation from the deployment backup under the update lock; retain new study checkpoints and immutable lifecycle evidence. If an experiment has been frozen, preserve its parameters, version and pending-validation state. No automatic rollback of forecasts, fills or account ledgers is performed.

A local run on confirmed market evidence completed the original candidate comparison. A second check on the same session reused the checksum-identical study. No candidate qualified for a formal upgrade. Account records and the current account projection were unchanged; existing frozen research records were preserved. This was a research/report verification, not a rerun of the entire daily pipeline or live trading validation.

## Per-slot trial and independent validation — 2026-10-23

477 regression tests passed, including 17 new tests for per-slot candidate selection below 2%, recent-window deterioration, early research trial without formal admission, horizon-specific/repeated-trial budgets, prospective maturity and no early final scoring, missing records, immutable evidence, fake registries, changed implementations, backdated/future evidence, original causal fitting, same-day restart and the actual collector. Old scheduler tests now explicitly cover `legacy_run`; their legacy thresholds remain unchanged.

An isolated copy of existing closing-market evidence completed 90 slot studies and found 21 eligible research trials, with zero independently accepted upgrades. Repeating the same data date reused the study and experiments. This is a real-input software run, not prospective proof of predictive improvement, a full daily-pipeline rerun or broker execution. Eight core algorithm/function bodies and all trading-risk configuration values were separately compared against the prior version. See [MODEL_UPGRADES.md](MODEL_UPGRADES.md) for the new protocol and rollback requirements.

## Separate model activity panels — 2026-10-23

486 regression tests passed, including nine new checks for verified final-fit counts, eligible versus actually adopted trials, different daily/intraday source dates, missing or tampered evidence, future labels/data dates, unknown historical recipes, read-only ledger access and daily export with an entry-only homepage. Browser checks confirmed that all three panels switch independently. The dedicated report was rendered from preserved records without training or activating a model.

85 Python modules imported; 652 local documentation links resolved. A fresh source copy initialized 13 non-sensitive configuration templates, with 120 valid navigation links. These checks concern software/report behavior, not independent predictive acceptance. The original estimator, recipe-selection protocol, risk settings and sealed predictions were not changed.

To roll back this presentation, restore the backed-up reporting files, layout and documentation under the daily/update locks, then regenerate navigation and the latest presentation. Retain any newly generated report archive; do not restore or overwrite prediction/account databases for a presentation rollback.

## Dynamic decision diagnosis (动态判断空表修复，2026-10-23)

Scope: report generation and Chinese explanations only. Tests cover no records, preserved closed-session failure, complete decision evidence, first recovery after failure, failure recurrence without stale rows, partial/duplicate coverage, missing models, future timestamps, malformed/tampered evidence, read-only diagnosis and publication without account/record changes. This delivery passed 499 regression tests, imported 86 source modules, checked 659 documentation links with none broken, and verified 121 generated links in a fresh organized copy. Recorded intraday failures are read without replaying or backfilling trades. The original forecasting, decision, execution and risk functions remain unchanged; only the `publish` body of the fingerprint-bound service is updated and requires the existing audited deployment procedure.

Software verification does not establish next-session recovery. After deployment, require actual opening cycles and report any missing coverage, model results, quote quality or chronology. A closed-session service result cannot satisfy this check. Maintain the immutable failure history, account projection and risk configuration through deployment; append only the required execution version review.

## Runtime recovery validation (运行故障修复，2026-10-28)

The full suite passed 520 tests. After the final training-panel empty-state adjustment, its 11 tests passed again. New regressions cover independent sealed inputs without a legacy plan/NAV, null parameters and quote timestamps, immutable input hashes, missing-past-model refusal, failure-to-recovery diagnostics, no-fill timeout handling, daily counter reset with no successful intraday cycle, append-only counter correction, bounded transport retries, TLS/data validation failures and partial-cache recovery. Default closed-session upgrade review remains required; the explicit failed-opening exception is tested to reject any current-session processing.

Eleven original algorithm/execution source files were byte-identical to the prior deployment, including forecasting, calibration, allocation, risk, candidate selection and order matching. The bodies of `infer_frame`, `model_snapshot` and `observed_bar` were also identical. Local risk/configuration hashes are separately verified during deployment; private configuration values and ledger evidence are not published.

A read-only live probe at 09:41 Beijing time received 30 quotes from each public feed, in approximately 1.68 seconds, with observed primary quote ages around 2–6 seconds. The existing corporate-action checks blocked complete inference for two instruments. No threshold was relaxed, and this is not a claim of full live-inference recovery or broker execution. A separate preparation probe verified all 30 saved stock models and 90 calibrators without retraining or reading a legacy plan. Full online daily processing, sustained provider availability and real brokerage execution are not certified by these tests.

Restore backed-up files only under the maintenance locks and append a reviewed execution version; do not rewrite previous audit hashes, fills or NAV. Daily-counter corrections preserve their own before/after hashes and reasons. Live quotes must independently pass the unchanged quality gates after service restart.

Post-deployment verification on 2026-10-28: three consecutive observed morning cycles wrote checksum-valid diagnostics without the former null-plan crash. Main-ledger NAV/P&L identities and daily counters reconciled; no new simulated fill occurred in the observed interval, so new-fill ordering was not applicable. Full research inference remained blocked by unchanged dual-feed consistency and corporate-action checks. The desktop live page displayed these reasons; the refreshed daily export had no broken local links and retained the original daily failure status.
