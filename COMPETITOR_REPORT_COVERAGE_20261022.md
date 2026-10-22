# 真实竞品报告里程碑：报告覆盖与流程接线

本地协调基线：`89d59f97a09dfa3571744c772b8b54b171c27305`（业务 main `4090f258`）。独立分支 `codex/milestone-competitor-report-20261022`，工作目录 `.local/milestone-competitor-report-20261022`。本任务为 Medium 的 B 部分；真实来源/网络采集由 High、最终真实后台获取和浏览器验收由负责人完成。本文及受控测试不作为本轮真实获取证据。

## 已实现的产品行为

- 复用首页 POST→StoreDiscovery→原单 worker→workflow→原店铺报告，不新增模型/迁移、路由、worker、采集器或另一个报告系统。
- 新 `market/catalog_coverage.py` 为同一份目录和最近报价 job 生成只读展示副本。新报价仅统计 **当前 job 外键 + 当前 discovery 外键 + 任务商品 URL** 匹配、金额上下限与币种有效的 `CatalogPriceObservation`；不拿 processed、任务 succeeded 字样、旧 job 或旧 JSON 时间戳代替报价成功。
- 本批明确失败仅取任务安排范围内、`price_attempted_at` 落在该 job 开始/结束时间窗、且有逐项 `price_error` 的记录。任务中断而没有 callback 时，现有模型没有逐项 HTTP 记录；计划内无结果明确写“待处理/逐项结果未记录”，**不声称未请求，也不把未知计作确定失败**。`failed_count=0` 只表示无已确认失败记录，不代表实际零失败。
- 任务范围外写“未安排本批采集”；旧保存报价独立写“沿用已保存报价”，按原时间展示，未计入本批新取得。旧价格与原数据不被 GET 覆盖。目录报价缺失不等于零商品，未知金额/币种不补零。
- 报告上部展示实际来源链接、目录完成观测时间（无完成时间则未知）、目录截断、目录去重链接数、本批有效报价、明确失败、旧报价、未安排和未记录结果。任务创建时间另标，不冒充来源观测时间。
- 商品表显示本批状态、新/沿用/无有效报价、原币种价格/规格范围与对应观测时间；词条、同币种分布与关系树复用原实现。当前 job 独立观测用于报告价格展示，确保新取得计数与展示金额一致，保留原目录索引及商品详情链接。
- 最小修正 `research.py` 的有效报价计数：仅有 timestamp 不够，必须有合法上下限与明确大写三位币种；计数、筛选、分布和商品行一致。有效零价保留，NaN/缺币种/坏范围不显示成零价。此修正也影响复用研究服务的跨店/候选/样本市场，已覆盖对应兼容回归。
- 既有目录复用行为保持；已保存报告清楚提示打开页面不会采集。报告内直接用既有 CSRF POST `discover_store`（url + workflow=1）“重新获取店铺数据”，不要求用户去侧栏。已有同店目录/报价任务时显示相应进度入口，避免界面重复排队。
- 刷新目录失败时 workflow 保留上次成功报告入口；刷新目录成功但报价失败时，新报告也保留上一份保存报告入口。失败、部分成功、无报价和无筛选结果各自展示，不用“0 商品”掩盖失败。

## 文件所有权与范围

- 新服务/测试：`market/catalog_coverage.py`、`market/test_catalog_coverage.py`。
- 进度：`market/workflow_views.py`、`market/templates/market/workflow.html`。
- 报告：`market/templates/market/research.html`、独立 `partials/catalog_coverage.html`、`market/static/market/catalog_coverage.css`。
- 经负责人明确授权的最小共享接线：`market/views.py` **仅 keyword_research 函数**；`market/research.py` 的有效报价判断/计数及对应复用。其余视图函数、顶层 imports 经 AST 对比保持不变。
- 不改 models/迁移/market.urls/jobs/worker/网络来源/利润数学；没有根目录代码修改、主库/主服务操作、账号或凭据操作、浏览器和平台访问。

## 负责人操作与验收

在整合 High 本轮来源及本提交后的显式隔离库/普通 QA 环境操作；本地队没有启动 QA 网页或 worker，也没有准备主库 fixture。

1. 新真实店铺 URL 从首页提交，进入原进度页。JSON 原有 title/message/active/redirect_url 保留，新增有限 coverage 计数；GET 不创建任务或采集。
2. 让原 worker 实际完成本轮目录/首批报价。结果自动到对应报告，核对本批新报价与本 job 观测数、URL、币种、规格范围、观测时点；截断目录必须可见。尚未覆盖商品继续走原“继续采集下一批”。
3. 展开原价格分布/词条树，检查币种独立及未知报价不进分布。单次样本不声称趋势、销量或上下架；lastmod 不当上架日期。
4. 已保存网址再次输入，仍打开保存报告；可直接点“重新获取店铺数据”开始新任务。队列活动时回进度，刷新失败后通过原页面返回旧报告。
5. 对部分失败、全批无价、目录失败/空目录、筛选无匹配/无效条件验证不同状态。某个请求在 callback 前终止，应显示逐项结果未记录，不能借 processed 推断成功或未请求。
6. 负责人实际桌面/390 检查摘要、长 URL 换行、商品表横向滚动、进度→报告、刷新/失败返回路径和截图。本轮只提供响应式 CSS 与受控 HTML 回归，未连接浏览器，真实 UI 与 High 新来源仍待验收。

## 验证与收据

显式私有 settings `.local/report_qa_settings.py` 在任何 ORM 前断言本克隆绝对 cwd、加载源码路径及 SQLite 后端/数据库路径；测试库固定本克隆 `.local/test-report-qa.sqlite3`，从不 fallback 到根 PG。测试仅普通用户，不创建管理员。

最终受影响回归：**53 项 / 14.560 秒，通过，无跳过**；包括新覆盖专项、workflow、research、跨店研究、候选和样本市场。命令：

```sh
cd /Users/qianpengfei/Documents/ChatGPT/shophot/.local/milestone-competitor-report-20261022
env PYTHONPATH="$PWD:$PWD/.local" DJANGO_SETTINGS_MODULE=report_qa_settings /Users/qianpengfei/Documents/ChatGPT/shophot/.venv/bin/python manage.py test market.test_catalog_coverage market.test_workflows market.test_research market.test_catalog_market market.test_candidates market.test_sample_market --noinput
```

Django check、makemigrations --check --dry-run、git diff --check 通过，无新迁移；没有重复前轮 576 全套或利润 UI。私有 `.local/coverage-regression-final.log` 和 `.local/DELIVERY_RECEIPT.json` 保存最终结果与精确源码哈希。初版测试中有同一测试 fixture 违反 job/url 唯一约束的问题，已修正受控 fixture；最终日志为上述 53 项无失败，未修改数据库约束。

剩余限制：任务没有持久化逐项 HTTP 尝试，未知结果按未知显示；保留报价只来自该目录已保存元数据，不把其他扫描的价格自动补成当前扫描成功，上一扫描可通过保存报告入口查看。旧数据没有可靠完成时间时标未知；未做全店新上架/下架监听、销量推算、全量评价或跨币种合并。真实来源可用性、最终隔离 PG 和浏览器验收由负责人/High 完成；本任务冻结后停止，未经具体反馈不扩建。
