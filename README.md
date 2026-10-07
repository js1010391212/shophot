# ShopHot

面向速卖通（AliExpress）等海外电商卖家的商品分析与运营工具网站。第一版采用 **Python 3.12+ / Django 5.2 / SQLite / HTMX / ECharts**，无需安装 Node.js、Redis 或单独的数据库服务。

## 第一版功能

- 首页输入速卖通竞品完整链接，自动加入采集队列，成功后识别名称并展示公开数据分析摘要。
- 登录保护的商品列表与详情，添加、编辑商品，按商品、店铺、平台和最新币种筛选。
- 多件竞品按同币种、同观测窗口对比价格曲线与公开评分；支持手动记录真实页面数据和报价条件。
- CSV 导入历史价格：全量校验、出错回滚、重复数据更新、空销量保留为未知。
- 按币种展示历史价格图表、首尾变化率与分页快照，导出筛选商品的全部历史。
- 独立采集进程、数据库任务队列、状态查看、失败原因、手动重试与中断任务恢复。
- 速卖通公开页面 JSON-LD 价格采集；记录观测时间与来源，不覆盖历史，不猜测销量。
- 单件利润估算：手动汇率、采购成本、运费、平台费率和其他成本。
- Django 管理后台、轮转日志、明确标注的可重复加载演示数据。

**范围限制：** 尚未接入速卖通官方 API；页面采集需要目标返回含明确价格的 JSON-LD。需要登录、动态加载、访问验证、价格区间或多个规格时会失败并显示原因，不绕过验证。其他平台目前支持 CSV 数据导入，不提供实时采集。首版为个人或可信小团队的共享工作台，所有登录账号共享商品数据，未实现租户隔离、自动选品或实时汇率。

## 快速开始

Linux/macOS，在仓库目录运行：

```bash
bash scripts/setup.sh
.venv/bin/python manage.py createsuperuser
# 可选：加载虚构演示商品，重复运行不会增加重复记录
.venv/bin/python manage.py seed_demo
bash scripts/start.sh
```

浏览器打开 `http://127.0.0.1:8000`，使用自己创建的账号登录。脚本同时启动网页和一个采集进程；按 Ctrl+C 停止。启动脚本使用 Django 开发服务器，仅用于本地开发。

Windows PowerShell 可分别执行：

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
# 在第二个终端执行
.venv\Scripts\python manage.py collect_worker
```

管理员可在 `/admin/` 管理账号、商品和快照。没有默认账号或默认密码；日常账号无需管理员权限。后台编辑快照会修改数据，历史采集与导入应优先使用网站提供的入口。

## 使用流程

1. 在“商品分析”添加商品，填写名称、链接、平台和店铺；速卖通平台填写 `AliExpress`。
2. 有已有数据时，到“导入数据”下载表头模板，填写后上传；仓库 `examples/products.csv` 是虚构示例。
3. 查看商品详情，通过币种切换查看价格趋势和快照。
4. 使用速卖通公开商品链接时，点击“采集最新价格”；采集进程约每 2 秒检查队列，页面约每 3 秒检查任务是否完成。
5. 采集失败后查看任务说明，可以改用 CSV，或修正链接后重新采集。队列等待通常表示采集进程尚未运行。
6. 在列表页导出筛选商品的历史，或打开“利润工具”估算成本。

演示商品链接指向 `example.com`，不能进行速卖通采集。演示数据不是实际市场数据。

## CSV 格式

```csv
title,url,platform,shop,price,currency,sales,observed_at,source
示例商品,https://example.com/item/1,Other,示例店铺,19.90,USD,,2026-10-01T10:00:00+08:00,csv
```

- 必填 `title,url,price,currency,observed_at`，其他列可省略。表头不能有重复或空白字段。UTF-8 编码，支持 BOM，最大 2 MB / 5000 行。
- 币种为三个英文字母；价格非负、最多两位小数；销量未知留空。
- 时间使用 ISO 8601，推荐包含时区；无时区按 `Asia/Shanghai` 解释。图表与快照表统一使用该时区，不随浏览器时区改变。
- 商品按链接识别。重复导入会更新名称、平台、店铺，保留备注。
- 快照按“商品 + 观测时间 + source”去重；同键导入会更新价格、币种和销量。
- source 默认 `csv`，支持 `web`、`manual` 和 `demo`，用于保留导出来源。这是用户提供的来源标签，不代表平台认证。
- 导出会在可能被表格软件执行为公式的文本前加单引号；这类文本重新导入时会保留该引号。
- 可选 `rating`（0–5、最多两位小数）、`review_count`（非负整数）和 `context`（最多 300 字报价条件）；旧 CSV 文件无需新增这些列。
- 不同币种不合并计算变化率；图表最多展示所选币种最近 500 点，导出不受该限制。

## 采集与定时更新

网页请求只创建任务，网络请求在采集进程内执行，默认只运行一个 worker，避免 SQLite 写入竞争。

```bash
# 把所有 AliExpress 商品加入队列，已有活动任务不会重复加入
.venv/bin/python manage.py queue_products
# 处理当前队列后退出
.venv/bin/python manage.py collect_worker --once
# 持续运行
.venv/bin/python manage.py collect_worker
```

可用系统定时任务调用 `queue_products`。如果没有常驻 worker，再串行执行 `collect_worker --once`；不要安排多个重叠的 worker。命令使用仓库绝对路径或先切换到仓库目录。中断任务超过 10 分钟会在下次 worker 检查时标记失败，用户可以重新加入队列。

网络需允许 `aliexpress.com` 和 `*.aliexpress.com` 的 HTTPS 访问。安装依赖使用 `pypi.org`、`files.pythonhosted.org`。即使网络允许，目标网站也可能要求登录或拒绝自动访问。请仅采集自己有权访问的数据，优先使用官方接口、授权数据或 CSV。

## 配置、日志和备份

- 默认数据库为仓库内 `db.sqlite3`，日志为 `logs/shophot.log`，最大 2 MB、保留 3 个备份；这些文件均不提交 Git。
- 日志包含导入数量、任务 ID、执行结果和可公开的失败原因，不记录账号密码、Cookie 或完整页面正文。
- 环境变量示例见 `.env.example`，配置读取进程环境；文件不会自动加载。可在环境设置、shell 或进程管理器中设置。
- 默认仅监听本机。正式部署需设置 `SHOPHOT_DEBUG=0`、独立随机 `SHOPHOT_SECRET_KEY`、允许域名和 HTTPS CSRF 来源，并使用正式 WSGI 服务与 HTTPS；开发服务器不是生产部署方案。
- 备份前停止网页和 worker，再复制 `db.sqlite3` 到仓库外的安全位置；恢复时停服替换数据库并运行 `migrate`。不要把个人数据或密钥推送 Git。
- 当多人使用或并发采集增加时，再迁移到 PostgreSQL、Celery/Redis；本版不需要这些组件。

## 验证

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
.venv/bin/python -m pip check
```

测试使用独立测试数据库，采集 HTTP 使用受控模拟响应，覆盖业务成功与失败路径，不依赖外站。真实速卖通商品采集需要在网络可达并提供有效商品链接后单独验证；测试通过不代表外站采集已成功。

### 竞品分析流程

首页输入完整速卖通商品链接，例如 `/item/商品编号.html`，点击“开始分析”。网站会去除标准商品链接的营销参数，按商品 ID 跟踪，创建采集任务并打开报告页面。成功后展示识别到的名称、明确价格、五分制评分和公开评价数；首次采集只有一个观测点，不会生成虚构历史趋势。

“竞品对比”可选择 2–8 件商品，按币种和最近 7 / 30 / 90 天或全部历史对比。不同商品的采集时间、规格、折扣、税费和运费可能不同，对比表展示观测时间与报价条件，不把公开评价数当作订单数。每条曲线最多 500 点，价格变化率按整个筛选窗口计算。

若自动采集失败，报告会保留失败原因；已有历史仍可查看。“记录公开数据”可以保存你实际在商品页面看到的价格、评分、评价数、公开销量与报价条件，来源固定为 `manual`，不伪装成自动采集。相同商品、观测时间的手动记录重复提交会更新原记录。

页面采集优先按 JSON-LD 的商品编号识别目标，无法分辨多个商品时明确失败，不把推荐商品价格用于目标竞品。尚未接入完整动态页面采集或官方授权接口，代理 403 阻塞期间，自动分析入口可用不代表真实数据采集已成功。

### 浏览器自检（可选）

自检自动创建临时数据库、账号和独立端口，启动测试网页与 worker，完成后清理，不修改现有数据库。安装浏览器测试依赖后运行：

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/browser_smoke.py
```

Linux 缺少浏览器系统依赖时，可按 Playwright 官方要求安装：`python -m playwright install --with-deps chromium`。已安装系统 Chromium 时无需下载浏览器，可使用 `--chromium /usr/bin/chromium`。

用 `--artifacts /tmp/shophot-selfcheck-artifacts` 可保存详情和手机截图。脚本覆盖登录与退出、商品添加编辑、真实 worker 的失败反馈、CSV 错误提示和重复导入、导出、HTMX 利润计算，竞品对比、手动公开观测，以及美国浏览器时区下的图表一致性。自动分析使用 `examples/fixtures/competitor_product.html` 受控测试夹具，不请求该示例商品，不证明实站采集成功。截图和测试产物请保存在仓库外。单元测试不需要安装 Playwright。

## 目录

```text
config/                    Django 配置与路由
market/models.py           商品、历史快照、采集任务
market/importing.py        CSV 校验、事务导入与安全导出
market/collectors.py        HTTPS 采集与 JSON-LD 解析
market/jobs.py              任务去重、认领、执行与恢复
market/management/commands/ 采集、批量排队、演示数据命令
market/templates/          中文网站页面
market/static/             本地样式、交互与第三方静态资源
market/tests.py            业务与采集边界测试
scripts/                   可重复安装和启动脚本
examples/                  演示 CSV
```

第三方前端资源：ECharts 5.6.0（Apache-2.0）、HTMX 2.0.4（BSD-2-Clause），从 npm 官方注册表下载并校验注册表提供的 integrity；许可证随资源保存在 `market/static/vendor/`。
