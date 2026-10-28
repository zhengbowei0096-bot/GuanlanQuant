"""Presentation-only Chinese views; never rewrites source JSON/CSV or ledgers."""
import ast,csv,html,io,json,re,math
from pathlib import Path
from urllib.parse import urlsplit,unquote,quote
from bs4 import BeautifulSoup
from ..core import atomic_text

WORDS = dict(x.split('=',1) for x in '''INVALID_QUOTE=报价或买卖盘字段缺失、非正数或无效
DYNAMIC_MODEL_INPUT_MISSING=独立模型输入尚未准备好，等待盘后生成或核验已保存的预测
DYNAMIC_MODEL_INPUT_INVALID=模型输入存在空值或字段结构异常，本轮研究判断暂停
DYNAMIC_MODEL_INPUT_TAMPERED=独立模型输入完整性校验失败，禁止使用
DYNAMIC_MODEL_SLOT_MISSING=个股的1、5、20日模型输入不完整
DYNAMIC_MARKET_ENVIRONMENT_UNAVAILABLE=缺少对应日期的大盘风险状态，等待数据补齐后重新核验
MISSING_SAVED_MODEL_NO_RETROSPECTIVE_TRAINING=缺少当时已保存的模型，不使用后来的数据补做旧预测
RECONCILE_DAILY_COUNTERS_FROM_CONFIRMED_PAPER_FILLS=按本日已确认模拟成交校正当日费用与成交金额，历史记录和累计费用不变
FAILED_OPEN_RECOVERY=开盘后尚无当日交易处理记录，已完成停服审核恢复
DAILY_COUNTER_FILL_EVIDENCE_MISMATCH=当日费用无法与不可变模拟成交核对，暂停更正
STALE_OR_FUTURE_QUOTE=报价过期或晚于判断时间
LOCKED_LIMIT_OR_INVALID_BOOK=涨跌停限制或买卖盘价格关系异常
DUPLICATE_OR_REORDERED_QUOTE=报价重复或到达顺序倒置
ABNORMAL_PRICE_JUMP=价格异常跳变，已暂停使用
CUMULATIVE_VOLUME_REGRESSION=当日累计成交量倒退，数据需要核对
QUOTE_PARSE_FAILED=行情字段无法解析
PRICE_INVALID=最新价格无效
CURRENT_REFERENCE_MISSING=缺少当日股票交易参考资料
SECURITY_NOT_SUPPORTED=股票暂不符合当前支持的交易范围
SUSPENDED_OR_EVENT=股票停牌或存在交易事件
REFERENCE_INVALID=股票交易参考资料无效
DECISION_TIME_INVALID=判断或模型记录时间不符合先后顺序
NO_RECORDED_DECISIONS=本轮未生成动态判断明细
DECISION_COVERAGE_INCOMPLETE=动态判断未覆盖完整观察池
MODEL_EVIDENCE_INCOMPLETE=缺少完整模型计算证据
DECISION_EVIDENCE_UNVERIFIED=动态判断记录无法读取或完整性校验未通过
WAITING=等待首次有效盘中记录
BLOCKED=动态判断受阻，尚未确认恢复
RECOVERED=最近盘中记录已确认恢复
AVAILABLE=最近盘中记录已有完整判断
EVIDENCE_UNVERIFIED=证据无法核验
OBSERVE_ONLY=当前只观察，未进入连续交易时段
QUOTE_SOURCE_UNAVAILABLE=行情来源暂不可用
QUOTE_STALE_OR_FUTURE=行情时间过期或晚于判断时间
QUOTE_INVALID=行情数值缺失或无效
REFERENCE_STALE=当日交易参考资料过期
SUSPENSION_EVIDENCE_STALE=停牌核查资料缺失或过期
BOOK_INVALID=买卖盘价格或数量无效
LIMIT_LOCK_OR_CONFLICT=触及涨跌停或涨跌停参考不一致
PARTIAL_BAR_UNVERIFIED=当日未收盘行情未通过校验
PREVIOUS_CLOSE_MODEL_NOT_AVAILABLE=上一交易日模型报告尚不可用或时间不合规
FROZEN_CALIBRATOR_REQUIRED=模型缺少可复用的已保存概率校准参数
INTRADAY_FEATURE_MISSING=盘中特征缺失，无法完成推理
PRIOR_SESSION_HISTORY_REQUIRED=缺少截至上一交易日的历史行情
MODEL_SNAPSHOT_STALE_OR_FUTURE=模型快照过期或晚于当前时点
FROZEN_PARAMETERS_INVALID=已保存模型参数未通过有效性检查
MODEL_LABEL_NOT_MATURE_BEFORE_SESSION=模型训练使用的标签在开盘前尚未到期
RESEARCH_TRIAL=研究试用，独立验证尚未完成
PREDICTIVE_PROCEDURE_VALIDATED_RESEARCH_EXECUTION=预测方案通过独立验证，交易仍为研究模拟
RESEARCH_TRIAL_ONLY=仅研究试用
PREDICTION_RECIPE_ONLY=仅预测方案验证通过
RESEARCH_ONLY=仅供研究，尚未正式验证
REFERENCE_ONLY=仅供参考
NO_VALIDATED_MODEL_RELEASE=尚无通过验证的正式模型
NO_VALIDATED_PORTFOLIO_RELEASE=尚无通过验证的正式组合策略
BUY=买入
ADD=加仓
SELL=卖出
REDUCE=减仓
HOLD=持有
WAIT=观望
NO_TRADE=本次不交易
PAPER_ONLY=仅模拟交易
RESEARCH_PAPER_ONLY=仅供研究模拟
ACTIVE_RESEARCH_PAPER=当前研究模拟
PAPER_FILL=模拟成交
ACCEPTED=模拟委托已接受，等待撮合
PARTIALLY_FILLED=部分模拟成交
FILLED=全部模拟成交
CANCELED=已撤单
REJECTED=已拒单
MARKET_CLOSED=非交易时段
RUNNING_PAPER_ONLY=模拟服务运行中
SETTLED=已结算
ALREADY_SETTLED=此前已完成结算
VERIFIED_CLOSE=已核验收盘估值
ANCHOR_SNAPSHOT=起始账户快照
OBSERVED_QUOTE_PAPER_ESTIMATE=基于已观察行情的模拟估值
SNAPSHOT_AVAILABLE=已有数据快照
FAILED=流程失败，请查看原因
SUCCESS=流程完成，不代表模型验证通过
RUNNING=处理中
MISSING=资料缺失
UNKNOWN=未知，待核实
WAIT_CONFIG_REVIEW=配置变化，等待核查
STALE_VALUATION=估值过期
PRESENTATION_UPDATED=仅更新报告展示
REPORT_REFRESH=刷新报告展示
INITIALIZED_WAITING_FIRST_CLOSE=已初始化，等待首次收盘结算
NO_SAME_DAY_ACCOUNT_NAV=缺少当日账户净值，不能计算实际收益
IMPLEMENTATION_CHANGED=研究实现发生变化，重新评估
WAITING_FOR_UNTOUCHED_TEST=等待未参与调参的独立测试
CONDITIONAL_RISK_PLAN=有条件的风险调整方案
PLAN_ONLY=仅供参考的计划
OBSERVED_TRADE_ONLY=仅按已观察行情评估成交
CALIBRATED_NOT_VALIDATED=已做概率校准，但尚未通过独立验证
EXECUTION_REPLAY_COMPLETE_EVIDENCE_INCOMPLETE=执行回放完成，但成交证据不完整
MIGRATION_MARK_NOT_BROKER_COST=成本按账户迁移时估值建立，并非券商实际成本
CONDITIONAL_PAPER_LIMIT_ORDER_WAIT_LATER_QUOTE=模拟限价委托等待后续有效报价撮合
LATER_OBSERVED_QUOTE=使用委托之后观察到的报价撮合
EXPIRED_REASSESS_WITH_NEW_DECISION=委托已过期，需根据新判断重新评估
HELD_QUOTE_UNVERIFIED=持仓行情未通过校验
SIGNAL_REVERSED_OR_TARGET_REACHED=最新目标已变化或已达到，无需继续原委托
EXPIRED_REASSESS_WITH_NEW_DECISION=委托已超时，等待重新判断
CONDITIONAL_PAPER_LIMIT_ORDER_WAIT_LATER_QUOTE=等待下一次有效报价撮合
LATER_OBSERVED_QUOTE=依据后续有效报价模拟成交
HISTORY_MODEL_VERSION_MISMATCH=历史数据版本与模型绑定版本不一致
MODEL_HISTORY_UNAVAILABLE=模型绑定的历史快照缺失或无法读取
MODEL_HISTORY_CHECKSUM_FAILED=模型历史快照完整性校验失败
MODEL_HISTORY_IDENTITY_MISMATCH=模型历史快照的股票或版本不匹配
MODEL_HISTORY_DATES_MISMATCH=模型历史快照的两种价格日期不一致
HISTORY_NOT_AVAILABLE_AT_MODEL_TIME=历史快照在模型生成时尚不可用或来源未核实
INVALID_MODEL_HISTORY_REFERENCE=模型绑定的历史版本路径无效
MODEL_QUOTE_NOT_VALID=股票行情未通过模型输入校验
UNAVAILABLE_RISK_REDUCTIONS_ONLY=研究推理不可用，仅检查独立风险减仓
execution_code=当前已审核执行代码版本
MODEL_QUOTE_NOT_VALID=模型所需行情未通过校验
CORPORATE_ACTION_RECONCILIATION_REQUIRED=除权除息等公司行动需要核对
VENDOR_CONFLICT=不同来源的行情不一致
UNAVAILABLE_RISK_REDUCTIONS_ONLY=研究推理不可用，仅运行独立风控减仓
UNCERTAINTY_HIGH=模型不确定性较高
DOWNSIDE_HIGH=下行风险较高
FORMAL_METHOD_NOT_VALIDATED=组合方法尚未通过正式验证
ACCOUNT_STALE_OR_UNVERIFIED=账户资料过期或未经核验
FORECAST_VALIDATION_FAILED=预测未通过验证
PROBABILITY_LOW=上涨概率未达到交易要求
PROBABILITY_NOT_INDEPENDENTLY_VALIDATED=上涨概率尚未独立验证
TARGET_NOT_VALIDATED=目标仓位尚未验证
RETURN_BELOW_COST=预期收益不足以覆盖成本
PRICE_NOT_CURRENT_LIVE=价格不是当前有效行情
TRADING_STATUS_UNVERIFIED=交易状态尚未核验
SESSION_UNVERIFIED=交易时段尚未核验
OUTSIDE_SUPPORTED_CONTINUOUS_SESSION=当前不在支持的连续交易时段
CURRENT_HOLDING_ABOVE_STOCK_CAP=当前持仓超过单只股票上限
INVALID_WEIGHT=仓位权重不符合要求
SSE_MAIN_A=沪市主板普通A股
SZSE_MAIN_A=深市主板普通A股
SOURCES=数据来源
MAE=平均绝对误差
RMSE=均方根误差
ECE=概率校准误差
QLIKE=波动预测损失指标
NAV=账户净值
CSV=明细表
JSON=原始数据记录
True=是
False=否
None=未提供
true=是
false=否
null=未提供
ridge=岭回归模型
garch=条件波动率模型
tencent=腾讯行情
sina=新浪行情'''.splitlines())
FIELDS=dict(x.split('=',1) for x in '''decision_diagnostic=动态判断异常与恢复
state=判断状态
service_status=服务状态
latest_attempt_at=最近盘中尝试时间
last_success_at=最近成功判断时间
last_failure_at=最近异常时间
last_failure_reason=最近异常原因
recovered_at=恢复确认时间
expected_stocks=观察池股票数
decision_stocks=本轮判断覆盖股票数
quote_problems=最近行情检查问题
reasons=具体原因
model_at=模型计算时间
last_decision_at=完整判断记录时间
id=记录编号
status=状态
asof=数据日期
date=日期
session=交易日
issued_at=生成时间
completed_at=完成时间
checked_at=检查时间
symbol=股票代码
name=股票名称
side=方向
shares=股数
price=模拟成交价
quantity=委托股数
filled=已成交股数
limit_price=限价
cash=现金
equity=账户权益
nav=账户净值
fee=费用
fees=当日费用
total_fees=累计费用
at=北京时间
reason=原因
rationale=决策依据
mode=运行模式
order_id=委托编号
source=来源
quote_time=报价时间
created_at=委托时间
cash_after=成交后现金
realized_pnl=已实现盈亏
unrealized_pnl=未实现盈亏
daily_pnl=当日盈亏
daily_return=当日收益率（小数）
cumulative_return=累计收益率（小数）
max_drawdown=最大回撤（小数）
errors=问题
error=问题说明
warnings=提示
steps=执行步骤
command=步骤名称
exit_code=退出状态码
submitted_orders=真实下单数
submitted_real_orders=真实下单数
attempt=尝试次数
sha256=完整性校验值
config=配置记录
forecasts=预测记录
horizon=预测期限（交易日）
expected_return=预期收益率
probability_up=上涨概率估计
validation=验证结果
metrics=评估指标
sample=样本
samples=样本数量
alpha=正则化参数
features=模型特征
mean_gain=平均改善幅度
eligible_for_future_test=是否进入后续测试
studies=候选研究
persistent_drift=是否持续出现分布变化
research_reason=研究原因
candidate=候选模型
note=说明
limitations=使用限制
data_versions=数据版本
portfolio=组合
weights=仓位权重
turnover=换手金额
initial_equity=初始权益
assumption=模拟撮合假设'''.splitlines())
TOKEN=re.compile(r'(?<![A-Za-z0-9_])('+ '|'.join(re.escape(k) for k in sorted(WORDS,key=len,reverse=True))+r')(?![A-Za-z0-9_])')
def translate(text):
 return TOKEN.sub(lambda m:WORDS[m[0]],str(text))

def tree(value):
 if isinstance(value,dict):
  return '<table><tbody>'+''.join('<tr><th>'+html.escape(FIELDS.get(str(k),str(k)))+'</th><td>'+tree(v)+'</td></tr>' for k,v in value.items())+'</tbody></table>' if value else '<p>暂无记录</p>'
 if isinstance(value,list):return '<details><summary>查看明细（'+str(len(value))+'项）</summary><ol>'+''.join('<li>'+tree(v)+'</li>' for v in value)+'</ol></details>' if value else '<p>暂无记录</p>'
 return html.escape(translate(value if value is not None else '未提供'))

def wrapper(title,body):
 return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{font:15px/1.6 system-ui;margin:20px;color:#183047}table{border-collapse:collapse;max-width:100%}td,th{border-bottom:1px solid #ddd;padding:6px 10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}details{margin:5px 0}.scroll{overflow:auto}</style><h1>'+html.escape(title)+'</h1><p>这是原始记录的中文阅读视图，金额、日期与结论未更改；研究或模拟结果不代表真实成交。</p>'+body+'</html>'

def account_cell(field,value):
 """Format displayed money/returns only; retain full precision in source evidence."""
 try:number=float(value)
 except (ValueError,TypeError):return html.escape(translate(value))
 if not math.isfinite(number):return '待核实'
 if field in ('daily_return','cumulative_return','max_drawdown'):return f'{number:.2%}'
 if field in ('nav','equity','cash','daily_pnl','realized_pnl','unrealized_pnl','fees','total_fees'):return f'{number:,.2f}'
 return html.escape(translate(value))


def attachment(path):
 path=Path(path)
 if path.suffix.lower()=='.json':return wrapper('详细记录',tree(json.loads(path.read_text())))
 if path.suffix.lower()=='.csv':
  rows=list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
  rows=[row for row in rows if any(cell.strip() for cell in row)]
  account=path.name=='账户每日与累计收益.csv'
  title='主账户每日与累计收益（模拟记账）' if account else ('主账户每日收益（模拟记账）' if path.name=='NAV.csv' else '明细表')
  note=''
  # Compatibility view of old exports: show only the same archived main account.
  # Never relabel broker data as paper fills or inject newer NAV into an old archive.
  if account and (not rows or 'mode' not in rows[0]):
   source=path.parent/'详细报告/dynamic/latest/NAV.csv'
   rows=list(csv.reader(io.StringIO(source.read_text(encoding='utf-8-sig')))) if source.exists() else []
   rows=[row for row in rows if any(cell.strip() for cell in row)]
   if rows and 'mode' in rows[0]:
    mode_index=rows[0].index('mode')
    if any(len(r)<=mode_index or r[mode_index]!='PAPER_ONLY' for r in rows[1:]):raise ValueError('账户数据模式不一致')
   elif len(rows)>1:raise ValueError('账户数据缺少模拟标识')
   note='<p>展示更正：旧入口误指向未使用的账户表。现改为本次归档保存的主账户结算记录；原始文件保留，未改写成交与收益，未补入后续日期。</p>'
  count=max(0,len(rows)-1)
  body=note+'<p>已记录 '+str(count)+' 条数据。</p>'
  if account or path.name=='NAV.csv':
   body+='<p>本系统仅使用这一套动态模拟主账户。日收益来自收盘结算；累计收益以本阶段起点为基准，未结算的日期不补造收益。金额显示到分，收益率显示为百分比，原始记录保留完整精度。</p>'
  if not count:
   body+='<section role="status"><h2>暂无可显示的结算记录</h2><p>本次报告尚未保存主账户收盘结算明细。没有记录不代表收益为零；请核对报告日期及结算状态。</p></section>'
  account_format=account or path.name=='NAV.csv'
  if rows:
   body+='<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(FIELDS.get(x,x).replace('（小数）','') if account_format else FIELDS.get(x,x))+'</th>' for x in rows[0])+'</tr>'
   body+=''.join('<tr>'+''.join('<td>'+(account_cell(rows[0][i],x) if account_format and i<len(rows[0]) else html.escape(translate(x)))+'</td>' for i,x in enumerate(row))+'</tr>' for row in rows[1:])+'</table></div>'
  return wrapper(title,body)
 return wrapper('运行记录','<p>以下为执行记录说明，非交易指令。</p><ul>'+''.join('<li>'+html.escape(translate(x))+'</li>' for x in path.read_text(errors='replace').splitlines() if x.strip())+'</ul>')

def render(page,path=None):
 soup=BeautifulSoup(page,'html.parser')
 for node in list(soup.find_all(string=True)):
  if node.parent.name in ('script','style'):continue
  s=str(node);t=translate(s)
  if t!=s:node.replace_with(t)
 for pre in soup.find_all('pre'):
  raw=pre.get_text()
  try:v=json.loads(raw)
  except (ValueError,TypeError):
   try:v=ast.literal_eval(raw)
   except (ValueError,SyntaxError):v=raw.splitlines()
  pre.replace_with(BeautifulSoup(tree(v),'html.parser'))
 # Values printed as Python lists/dicts in cells are audit data, not UI prose.
 for td in list(soup.find_all('td')):
  if td.find(True):continue
  raw=td.get_text().strip()
  if raw.startswith(('[','{')):
   try:v=ast.literal_eval(raw)
   except (ValueError,SyntaxError):continue
   td.clear();td.append(BeautifulSoup(tree(v),'html.parser'))
 if path:
  path=Path(path)
  for a in soup.find_all('a',href=True):
   h=a['href'];u=urlsplit(h)
   if u.scheme or not u.path:continue
   dest=(path.parent/unquote(u.path)).resolve()
   if dest.is_file() and dest.suffix.lower() in ('.json','.csv','.txt','.log'):
    view=dest.with_name(dest.name+'.view.html')
    try:atomic_text(view,attachment(dest))
    except (ValueError,OSError):continue
    a['href']=quote(unquote(u.path)+'.view.html',safe='/')
    a.string=translate(a.get_text()).replace('下载','查看')
 return re.sub(r'(<!DOCTYPE[^>]*>)\s*',r'\1\n',str(soup),count=1,flags=re.I)

def localize(directory):
 result={'pages':0,'broken':[],'external':[]}
 paths=[p for p in Path(directory).rglob('*.html') if not p.name.endswith('.view.html')]
 for p in paths:
  old=p.read_text();new=render(old,p)
  if old!=new:atomic_text(p,new)
  result['pages']+=1
 for p in Path(directory).rglob('*.html'):
  soup=BeautifulSoup(p.read_text(),'html.parser')
  for a in soup.find_all('a',href=True):
   h=a['href'];u=urlsplit(h)
   if u.scheme in ('http','https'):result['external'].append(h);continue
   if u.scheme not in ('','file'):continue
   target=Path(unquote(u.path)) if u.scheme=='file' else ((p.parent/unquote(u.path)).resolve() if u.path else p)
   if not target.exists():result['broken'].append({'page':str(p),'href':h,'reason':'目标不存在'})
   elif u.fragment and target.suffix=='.html':
    dest=BeautifulSoup(target.read_text(),'html.parser')
    if not dest.find(id=unquote(u.fragment)) and not dest.find('a',attrs={'name':unquote(u.fragment)}):result['broken'].append({'page':str(p),'href':h,'reason':'页内位置不存在'})
 return result
