> 最新续接入口（2026-10-08，物流/R1待负责人集成）：物流报价及利润联动已完成，迁移0011 ShippingRate应用，独立shipping服务/表单/导入/视图及界面；官方顺丰8线路0.5–5kg参考价非协议价，支持每公斤/首重续重、体积重、燃油基数、币种和同款分摊尾差；CSV/XLSX签名预览确认、账号隔离、公式拒绝、失败不覆盖。负责人R1已修复统一分项舍入ledger与实际达标定价，0.05收入两费各0.01→总费0.02/净利0.03。初轮全套213通过，R1/日期补丁后末次36项专项通过；最终整合全套由负责人统一执行，不重复。check/迁移/diff通过，桌面/390px及导入/非法输入验收，业务ShippingRate=0。细节与文件/来源见SHIPPING_MODULE.md和DEVELOPMENT_LOG末条；截图.local/shipping-artifacts/。最终服务session80659、父19253/worker19263/web19264，停前核PID。用户指定只与负责人对接，遵守TEAM_COORDINATION；本团队未提交/推送/部署，Git基线由负责人审查建立。实际货代合同未提供，未做实账对账或实时费用/任意多级矩阵/混款分摊。本轮完成后停，勿扩展功能。

> 最新续接入口（2026-10-08）：商品评论样本主功能已接通。ProductReviewBatch一对一Snapshot，迁移0010已应用；统一文件导入预览/保存明确商品评论最多10条，未知不补造、重复不新增、冲突保护历史。product_reviews / product_review_forms / product_review_views / product_reviews.html独立模块，复用现有规则图表及原文证据；GET可只读复用同商品已保存目录评论、切换导入观测，来源不合并。完整188项通过，末次12项专项通过（含旧坏链接容错）；migration/check/diff通过。真实Beard Comb Product#5评论报告/products/5/reviews/，只读复用目录#6商品0的7条真实样本，发现5星评论也有尺寸/效果线索。桌面390px、来源切换、证据跳转、空数据及受控文件评论预览均验收。实库Product#4/#5均0快照/0任务、ProductReviewBatch为0，未保存测试数据。最终服务session62356，单worker，未提交/推送/部署。用户询问MySQL差异已说明，未请求切换，继续PostgreSQL。下一步真实OTTO/速卖通文件兼容验收，或按用户方向继续选品模块；全量/动态评论、AI语义与其他平台文件未接入，不启动最终交付。

> 最新续接入口（2026-10-08）：统一商品页面导入模块完成，入口 /import/page/，接入 OTTO 与速卖通 aliexpress.com 严格JSON-LD解析。page_import / structured_page / page_import_forms / page_import_views 独立模块；旧OTTO URL/解析/表单兼容。签名预览→确认保存MANUAL历史，来源/规格/观测时间/文件校验码明确。速卖通sku_id保留并直接导入，自动入口与worker保护不采集通用价格。全套177项通过，最后端口边界专项24项通过；无新迁移，check与diff通过。浏览器测试夹具只预览不保存，Product#4为0快照/0任务；真实商品当前在售未知，真实HTML兼容性待验收，非自动成功。桌面/390px截图与限制见 CROSS_PLATFORM_VALIDATION.md。最终服务session38309，单worker，未提交/推送/部署。下一步取得正常保存的真实OTTO/速卖通HTML核对明确商品规格报价；SHEIN/Ozon文件未接入，不用夹具冒充实站数据。

> 小额度续开发（2026-10-08）：补齐 OTTO 保存HTML步骤、手动来源/动态内容/历史起点说明，报告空数据提供直接导入与手动记录链接，预览含税/运费说明以原页面为准。11项专项通过，桌面与390px展开说明无溢出；截图 .local/platform-validation/otto-help{,-mobile}.png。最终服务session69736。额度刷新后：先验证真实OTTO保存HTML，再将导入流程抽成平台适配入口，优先速卖通；保留各平台身份/规格/币种校验，测试夹具不得混入业务库。尚未实施速卖通HTML适配，不宣称新平台自动支持。

> 最新续接入口（2026-10-08）：OTTO 单品离线 HTML 导入模块完成，首页链接→预览→确认保存 MANUAL 历史；保留 variationId、币种、规格与真实观测时间，签名绑定账号/商品、20分钟过期。自动请求 HTTP400 是 KPSDK 验证，未绕过，尚未接入自动采集/店铺目录/评价正文。真实 Guru-Shop 链接创建 Product#3，无报价和自动任务；真实保存 HTML 兼容性仍待验收，夹具仅在测试库。全套167通过、末次11项OTTO专项通过，迁移无变化。桌面及390px手机无溢出，证据见 CROSS_PLATFORM_VALIDATION.md。服务 session39879，先查实际进程，未提交/推送/部署。下一步取得正常保存的真实 OTTO HTML 样本进行报价归属验收，不能宣称自动成功。

> 最新续接入口：跨平台实站验收完成，详细链接与证据见 CROSS_PLATFORM_VALIDATION.md。OTTO 两卖家商品浏览器可见价格，但安全HTTP400；SHEIN两入口验证，Ozon两店铺连接错误，速卖通店铺验证。自动分析尚未通过。修复首页把非速卖通平台误当Shopify的问题，新platforms.py明确识别并提示未接入，156项全套通过；最终服务session72610，未提交部署。下一建议OTTO单品适配，先解决公开数据获取和身份归属，不宣称已支持新平台。

> 最新续接入口：样本市场分析模块已实现，入口在跨店商品研究页，/research/market/；按最新目录去重、币种独立价格段/中位数、品牌分布、评价覆盖及报价新鲜度，可从图表/链接筛选商品并进入报告。实库 5 家/314 商品/52 报价/3 评论样本商品；全套 152 项通过，末次金额边界专项结果见 DEVELOPMENT_LOG.md。平台计划仍见 PLATFORM_ROADMAP.md，新平台采集尚未接入。继续按模块开发，不启动最终交付。

> 最新续接入口（2026-10-08）：定时价格监测模块已实现，迁移 0009 已应用；从商品报告设置 6/12/24 小时频率，账号隔离、暂停恢复、队列去重、失败退避、跨目录按 URL 匹配，复用单 worker。真实 Beard Comb 监测 #1，任务 #13/#14 写入观测 #51/#52（USD 19–21），最终每日监测启用，下次 10 月 9 日 10:12 CST。全套验证和最终进程状态见 DEVELOPMENT_LOG.md；服务未设系统自启动，停机不采集。用户最新要求后续支持 SHEIN/OTTO/Ozon，并已用截图确认参考插件 Sorftime Save；规划与调研见 PLATFORM_ROADMAP.md，建议下一模块样本市场看板，尚未实施新平台采集。遵守 AGENTS.md，按模块继续；尚未进入最终交付。

> 最新续接入口：先读 [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)、[DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md)，遵守 AGENTS.md。独立报价历史模块已完成，按商品链接合并跨目录记录、币种/时间过滤并依据新保存的规格范围比较报价上下限；旧记录不补造走势。真实 Beard Comb 连续两次更新验证，141 项全套通过、末次 5 项专项通过，迁移 0008 已应用。最终服务 session 57638，先查进程。用户要求按模块继续开发；下一模块方向尚未选择，不自动启动最终交付。

## 本地续开发更新（2026-10-07）

v0.2 新增 Shopify 公开商品采集、平台选择、店铺样本研究、采集中心与响应式侧栏。利润工具支持双币种、手动汇率、折扣、支付费用、成本拆分与保本/目标利润率计算。78 项测试在 SQLite 和 PostgreSQL 上均通过。

已解决本地 Fake-IP DNS 兼容和 Shopify text/javascript 响应解析。真实验证结果见 LIVE_VALIDATION.md；速卖通申请步骤见 ALIEXPRESS_API.md。新增公开 sitemap 商品发现，LILYGO 与 TEM Laser 各保存 100 个真实商品链接（截取目录）。PostgreSQL 17.11 已安装并启用；旧数据逐项迁移校验一致，原 SQLite 和导出备份保留。启动见 DATABASE.md。尚未接入官方 API、完整全店目录、销售估算、图片或定时监控。下文为历史基线记录，新增功能以上述更新和 README v0.2 为准。

---

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
