# ShopHot 本地开发交接

整理日期：2026-10-07（北京时间）。本文描述代码基线 `3adc2ab`；本次交接提交只补充文档。

## 1. 目标与当前结论

最终产品是一个竞品分析网站：用户输入速卖通等平台的竞品商品链接，后台取得可用公开数据，保存历史快照，在网站中生成单商品报告和多商品对比。

当前已实现网站、数据库、采集任务队列、公开页面 JSON-LD 解析和分析展示。**真实速卖通采集尚未成功验证**：云环境实测存在代理 403 和本地 DNS 解析失败。当前可用的数据入口是 CSV 和手动记录；自动分析成功路径使用受控测试夹具验证，不能当作实站采集成功。

在本地接着做时，第一优先级是验证真实商品访问，再根据实际页面选择 HTTP 采集或浏览器采集，不必重做网站基础。

仓库：https://github.com/js1010391212/shophot ，分支 `main`。功能与历史验证记录分别见 [README.md](README.md) 和 [VALIDATION.md](VALIDATION.md)。

## 2. 已有功能及边界

| 功能 | 当前实现 |
| --- | --- |
| 首页输入竞品 | 接受完整速卖通 HTTPS `/item/商品编号.html` 链接；标准链接统一为 www 域名并去除查询参数，建档并排队 |
| 商品管理 | 添加、编辑、名称/店铺搜索、平台/最新币种筛选 |
| 单商品报告 | 最新公开数据、所选币种历史最低/最高价、价格曲线和快照列表；单次观测不推断趋势 |
| 竞品对比 | 2–8 件商品，同币种，最近 7/30/90 天或全部历史；显示来源、报价条件和观测时间 |
| 数据入口 | CSV 校验与事务导入、重复快照更新、手动记录公开数据、CSV 导出 |
| 采集任务 | 排队、原子认领、状态刷新、失败原因、手动重试、超过 10 分钟的中断任务回收 |
| 公开指标 | 明确价格、币种、五分制评分、评价数；自动采集不猜测销量 |
| 利润工具 | 使用手动汇率与成本计算单件利润；不代表掌握竞品真实利润 |
| 账号和后台 | Django 登录和管理后台；所有登录账号共享数据，未做多租户隔离 |

尚未实现：稳定的真实速卖通采集、动态页面采集、官方 API、自动定时调度、降价提醒、历史数据服务接入、公网生产部署。

历史价格从开始记录时积累，网站不能凭一次访问还原过去三个月的走势。需要已有历史时，要导入真实数据或验证可用的历史数据服务。

## 3. 本地启动

要求 Python 3.12 或以上。运行依赖在 `requirements.txt` 中固定版本；无需 Node.js、Redis、单独的数据库服务。前端 ECharts 与 HTMX 已随代码保存到本地静态资源目录。

首次获取代码：

```bash
git clone https://github.com/js1010391212/shophot.git
cd shophot
```

已有 checkout 可在保存本地修改后执行 `git pull --ff-only origin main`。ZIP 解压后的根目录是 `ShopHot`，所有命令均在包含 `manage.py` 的目录执行。

### Windows / PowerShell

```powershell
py -3 --version
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
# 可选：虚构演示数据，不是实际市场价格
.venv\Scripts\python manage.py seed_demo
.venv\Scripts\python manage.py runserver 127.0.0.1:8000 --noreload
```

如果 `py -3` 选到的版本低于 3.12，请安装合适版本，或改用已安装的 `py -3.12`。

第二个终端进入相同目录：

```powershell
.venv\Scripts\python manage.py collect_worker
```

更新代码后重新安装依赖、执行 `migrate`，再重启网页和 worker。

### macOS / Linux

确认 `python3 --version` 至少为 3.12，然后运行：

```bash
bash scripts/setup.sh
.venv/bin/python manage.py createsuperuser
# 可选：虚构演示数据
.venv/bin/python manage.py seed_demo
bash scripts/start.sh
```

`start.sh` 自动应用迁移、检查配置，同时启动网页与一个 worker；任一进程退出会清理另一个。默认关闭热重载，修改代码后需要停止并重新启动。

本地浏览器输入 `http://127.0.0.1:8000`；管理后台路径为 `/admin/`。首次使用自己创建账号，没有默认密码。Windows 在两个终端分别按 Ctrl+C 停止；macOS/Linux 停止启动脚本即可。

## 4. 数据、配置和日志

- 数据库：项目根目录的 `db.sqlite3`，首次 `migrate` 时创建。
- 日志：`logs/shophot.log`，最大 2 MB，保留 3 个轮转备份。
- 数据库、日志、虚拟环境和 `.env` 均不提交 Git，也不包含在源码 ZIP 中。
- 云环境中的账号、商品与测试记录不会随 Git/源码 ZIP 自动迁移；本地首次启动是新数据库。
- `seed_demo` 可重复执行，生成 3 个虚构商品和 21 条虚构快照；`examples/products.csv` 也是演示数据。
- `.env.example` 只是说明，应用不会自动加载 `.env`。当前配置直接读取进程环境。
- 开发默认监听本机、DEBUG 开启；不需要配置云环境的代理地址或凭据。不要把云环境的代理配置照搬到本地。

如需修改配置，在对应 shell 设置环境变量，例如 Windows：

```powershell
$env:SHOPHOT_DEBUG = "1"
$env:SHOPHOT_ALLOWED_HOSTS = "localhost,127.0.0.1,[::1]"
```

Linux/macOS 可用 `export SHOPHOT_DEBUG=1`。主要变量还包括 `SHOPHOT_SECRET_KEY`、`SHOPHOT_CSRF_TRUSTED_ORIGINS`；`SHOPHOT_BIND` 只供 `start.sh` 选择监听地址。正式部署要求独立密钥、DEBUG 关闭、HTTPS 和正式 WSGI 服务，尚未验证生产部署。

备份数据库前停止网页与 worker，再复制 `db.sqlite3` 到项目外；恢复时停服替换数据库并运行 `migrate`。不要从陌生版本覆盖迁移文件或删除现有数据来消除错误。

## 5. 代码入口与数据结构

| 文件 | 接续开发时的用途 |
| --- | --- |
| `market/forms.py` | 自动分析链接校验、手动观测表单、竞品选择与输入校验 |
| `market/views.py` | 自动建档/排队、报告统计、对比、CSV 和利润工具 |
| `market/collectors.py` | 域名与地址检查、HTTP 下载、JSON-LD 目标商品识别及指标解析 |
| `market/jobs.py` | 去重、认领任务、调用采集器、写快照、完成/失败记录 |
| `market/models.py` | Product、Snapshot、CollectionJob 模型与约束 |
| `market/management/commands/` | worker、批量排队和演示数据命令 |
| `market/templates/market/` | 首页、详情/报告、对比、导入、手动记录等中文页面 |
| `market/static/market/` | 页面样式、图表与任务轮询 |
| `market/tests.py` | 业务、异常输入、采集目标身份等单元测试 |
| `scripts/browser_smoke.py` | 使用临时数据库和独立端口的浏览器自检 |
| `config/settings.py` | SQLite、登录、时区、日志、环境变量等配置 |

调用链：`analyze_competitor()` → `enqueue()` → `collect_worker` → `run_next()` → `collect()` / `parse_product()` → Snapshot → 详情报告。网页本身不执行爬虫，worker 未启动时任务会一直排队。

- **Product**：名称、唯一链接、平台、店铺、备注。
- **Snapshot**：商品、观测时间、价格/币种、可空销量/评分/评价数、报价条件、来源。唯一键是“商品 + 时间 + 来源”。评分约束为 0–5，价格非负。
- **CollectionJob**：queued / running / succeeded / failed，开始与完成时间、说明。每个商品最多一个 queued/running 任务。
- 迁移：`0001_initial` 与 `0002_snapshot_context_snapshot_rating_and_more` 均已存在；本地运行 `migrate` 即可应用。
- 来源值：`web`、`manual`、`csv`、`demo`。CSV 的来源标签由上传者提供，不表示平台认证。

采集器返回 dict，包含 `price`、`currency`、`sales` 及可选 `rating`、`review_count`、`title`。`jobs.py` 取出 title 后将其他字段写入快照；仅自动更新“待识别竞品”名称，不覆盖用户命名。扩展采集元数据时不要直接把快照模型不支持的键传给 ORM。

## 6. 真实采集的实测证据

测试链接：<https://www.aliexpress.com/item/32922106384.html>

出处：[Meshtastic 固定版本文档中的 0.96 英寸 OLED 显示屏购买链接](https://github.com/meshtastic/meshtastic/blob/34df69bc427e508de9ecd627a47091197de59488/docs/hardware/devices/lilygo/tbeam/screens.mdx)。它不是随意拼出的测试编号，但因为没有成功读取商品页，**未确认是否仍在售**。

云环境结果：

| 检查 | 实测结果 |
| --- | --- |
| 网站输入链接 | 成功建档，云数据库商品 #5 |
| 采集队列 | 任务 #3 执行，失败提示“商品地址无效或域名无法解析” |
| 直接 HTTPX 请求 | ProxyError，代理返回 403 |
| 本机 DNS 检查 | socket.gaierror，错误编号 -3 |
| 报告页面 | HTTP 200，正确说明没有公开价格 |
| 实际价格快照 | 0 条，未写入虚构数据 |

后续云运行配置检查显示：当前运行实例没有速卖通自定义允许域名，网络状态为 `unknown`；草稿里添加域名不等于已经发布或应用到当前实例。这是云环境结果，不能据此判断用户电脑也存在相同故障。

`collectors.py` 在 HTTP 请求前用 `socket.getaddrinfo()` 校验目标是否为公网地址。即使代理能处理请求，本机无法解析 DNS 时采集仍会提前失败。当地网络验证时，需要分别检查 DNS、HTTP、页面内容和解析结果，不能把所有失败都当成 JSON-LD 解析问题。

本地可先在浏览器打开该链接，并测试 DNS：

```powershell
# Windows
Resolve-DnsName www.aliexpress.com
.venv\Scripts\python -c "import httpx; r=httpx.get('https://www.aliexpress.com/item/32922106384.html',timeout=20,follow_redirects=False); print(r.status_code,r.headers.get('content-type'))"
```

```bash
# Linux / macOS
.venv/bin/python -c "import socket; print(socket.getaddrinfo('www.aliexpress.com',443))"
.venv/bin/python -c "import httpx; r=httpx.get('https://www.aliexpress.com/item/32922106384.html',timeout=20,follow_redirects=False); print(r.status_code,r.headers.get('content-type'))"
```

浏览器能打开但 HTTP 返回验证页面时，继续调查实际响应；HTTP 200 也可能是登录或访问验证页面，不代表获得商品数据。链接已失效时换另一个能人工确认的在售商品。

当前仅支持 HTTPS 的 `aliexpress.com` 子域，**不支持 `aliexpress.us`**。HTTP 下载限制：连接超时 10 秒、其他网络阶段超时 20 秒、最多 5 次跳转、HTML 最大 2 MB；这是请求阶段超时，不是整个任务的总时长上限。

解析器仅读取 JSON-LD 中明确单价；不把 lowPrice 当作明确规格价格。多商品优先匹配目标 ID，无法确定身份则失败；无法区分多个规格价格也失败。真实页面若没有 JSON-LD，这版不会从其他脚本或 DOM 获取价格。

## 7. 本地验证与验收

以下结果已在云 Linux/Python 3.12 环境执行：45 项 Django 测试通过，迁移/依赖/系统检查通过；系统 Chromium 浏览器自检通过。Windows 命令已提供，未在 Windows 执行；GitHub Actions 结果以远程实际记录为准。

```bash
# Linux/macOS；Windows 把 .venv/bin/python 换成 .venv\Scripts\python
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
.venv/bin/python -m pip check
```

浏览器测试为可选开发依赖，不是自动采集能力：

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/browser_smoke.py
```

有系统 Chromium 时可用 `--chromium /usr/bin/chromium`，无需下载浏览器。Linux 缺少浏览器系统依赖时参考 Playwright 的 `install --with-deps chromium`。截图可通过 `--artifacts` 保存到项目外。

自检会创建临时数据库、账号与独立端口，完成后清理。自动分析成功路径使用 `examples/fixtures/competitor_product.html`，不是实时速卖通页面；不要将这个夹具替换成真实结果或把通过自检当作爬虫已打通。

本地功能验收：

1. 创建账号、登录、加载演示数据，确认详情图表与竞品对比可显示。
2. 导入 `examples/products.csv` 两次，第二次应更新已有快照而不重复新增。
3. 手动记录价格、评分、评价数和报价条件，确认报告、列表和 CSV 导出一致。
4. 启动一个 worker，输入人工确认的真实速卖通商品链接；确认任务完成且字段与页面一致。
5. 换规格、换币种、缺失评价、访问失败时，不应保存错误目标或虚构指标。
6. 在后续时间再次采集相同报价条件，确认新增历史记录且之前的快照保留。

## 8. 后续任务优先级

### P0：打通一个真实商品

先完成本地 DNS 与 HTTP 检查，再检查真实页面结构。如果 HTTP HTML 已有可用数据，扩展当前解析器；如果数据必须由 JavaScript 加载，再设计 Playwright 采集适配器。目前项目只把 Playwright 用于测试，尚无浏览器爬虫。

完成标准：记录一个人工确认仍在售的真实链接；来源、规格、币种和观测时间明确；自动任务成功，价格/评分/评价数与页面对得上；失效、缺失、多个规格及验证页面有明确失败或缺失反馈。先验证少量商品，不以绕过访问验证或禁用 TLS 校验作为成功条件。

### P1：固定报价条件与稳定调度

当前报价条件 `context` 只是备注，不是结构化国家、SKU、税费或运费字段。标准链接去除查询参数后，可能丢失规格选择；历史曲线目前按商品和币种筛选，不按规格筛选。正式用于选品前，应建立结构化报价/规格身份，避免不同条件混在一条曲线里。

现有 `queue_products` 只负责批量排队；没有自动定时器、自动失败重试、请求间限速策略、总任务时长上限或降价提醒。实现关注列表、更新频率、限速、退避重试及调度，再设计提醒阈值。

### P2：更有用的报告和历史数据

在真实数据积累后增加新鲜度、同口径价格差、评价数变化等指标。若需要跟踪开始前的历史，验证授权历史数据服务或导入来源；竞品真实订单量、真实利润不能由公开价格和评价数推出。

### P3：正式部署

确认使用者与权限要求；当前所有账号共享数据。随后配置正式 WSGI 服务、HTTPS、独立密钥、数据库备份和进程守护；并发增加时再迁移 PostgreSQL、Celery/Redis，不把开发服务器当作生产部署。

## 9. 给下一位开发者的任务说明

> 在现有 ShopHot Django 项目上继续，不重建基础网站。先启动本地网页和一个 worker，运行现有测试，验证一个人工确认在售的速卖通商品。分别诊断 DNS、代理/HTTP、动态内容和解析。保留历史快照、数据来源、币种隔离与明确的失败反馈，不用模拟数据冒充实站成功。若扩展采集器，同步添加受控响应测试和实际页面验证说明；若引入规格/市场身份，同步修改模型、迁移、CSV、表单、对比和测试。完成后更新 README、VALIDATION 并提交 Git。
