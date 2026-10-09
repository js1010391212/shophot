# ShopHot 按模块开发指南

当前架构为 Django + PostgreSQL、服务端模板、少量原生 JavaScript 与 ECharts。先逐模块完善现有流程，避免同时更换框架、采集方式和界面。

## 模块地图

| 模块 | 服务 / 数据 | 页面与交互 | 主要验证 |
| --- | --- | --- | --- |
| 报价带入利润测算 | `profit_references.py` 只读解析公共商品或本账号浏览器报价，复用金额/币种校验；`profit_views.py` 复用原物流利润表单与计算服务 | 报价报告逐条链接到利润页，原报价/规格/条件/时间与可改假设分开；HTMX保留归属引用，重置清除 | `test_profit_references.py`，GET无写入、两账号隔离、重复引用、精度、POST/HTMX生命周期、原手填/顺丰兼容 |
| 速卖通联盟只读响应适配 | `aliexpress_affiliate.py`，不可变请求上下文与六类成对价格；无网络/DB/保存 | 开发用 `preview_aliexpress_affiliate` 离线响应命令，强制测试标签，不是用户JSON导入入口或实站验收 | `test_aliexpress_affiliate.py` / `test_aliexpress_affiliate_command.py`，身份/精度/未知口径/错误正文抑制/有界只读；当前凭据与实际API未接通 |
| 浏览器观测契约（B1） | `browser_capture.py`，有界JSON接收/账号商品签名预览，复用链接规范化/QuoteTarget/金额校验，不保存 | 纯契约由浏览器主动观测模块复用；实站边界见扩展README | `test_browser_capture.py`：编码/重复键/输入边界、商品规格/签名归属及过期；实站未验收 |
| 商品页面文件导入 | `page_import.py` / `structured_page.py` / `page_import_forms.py`；复用 Product / Snapshot；`otto.py` 保留链接规范化 | `page_import_views.py` / `page_import{,_start}.html`；首页、失败页、商品报告入口；旧 OTTO URL/表单兼容 | `test_page_import.py` / `test_otto.py`；身份/规格/未知值、签名归属与过期、CSRF、历史保护；真实文件兼容性待验收 |
| 平台识别与验收 | `platforms.py`；`AnalyzeForm`；只读 `scripts/validate_platform_samples.py` | 首页与现有分析表单明确提示未接入平台 | `test_platforms.py`，真实域名/边界、兼容、不误排队；实站见 CROSS_PLATFORM_VALIDATION.md |
| 分析流程 | `workflows.py`、`jobs.py`；StoreDiscovery / CollectionJob | `workflow_views.py`、`workflow.html`、`workflow.js` | `test_workflows.py`，输入到报告、空目录、失败、重试、重复任务 |
| 店铺发现与公开采集 | `discovery.py`、`network.py`、`shopify.py`、`collectors.py`、`catalog_prices.py`、`catalog_content.py`、`reviews.py` | 采集任务与商品报告 | 对应 discovery/shopify/catalog/reviews 测试，来源归属与请求边界 |
| 商品研究 | `research.py`、`catalog_research.py` | `research.html`、`catalog_market.html`、`catalog_compare.html`、相关图表 JS | 筛选、排序、原商品身份、币种、导出 |
| 样本市场分析 | `sample_market.py`，复用最新目录与商品研究行 | `sample_market_views.py`、`sample_market_forms.py`、`sample_market.html`、`sample_market.js` | `test_sample_market.py`，币种隔离、去重、价格段联动、覆盖分母与新鲜度 |
| 目录报价历史分析 | `price_history.py`；CatalogPriceObservation / quote_scope | `price_history_views.py`、`price_history_forms.py`、`price_history.html`、`price_history.js` | `test_price_history.py`，跨目录、币种、规格条件、零基准、旧记录与失败 |
| 定时价格监测 | `price_monitoring.py`；PriceMonitor / StorePriceJob，现有 worker 调度 | `price_monitoring_views.py`、`price_monitoring_forms.py`、监测清单/设置模板 | `test_price_monitoring.py`，到期、共享队列、目录重排、归属、暂停恢复、失败退避与历史保留 |
| 评论分析与观测历史 | `review_analysis.py` / `product_reviews.py` / ProductReviewBatch；复用 Snapshot 与已有目录样本 | `product_review_forms.py` / `product_review_views.py` / `product_reviews.html`；导入预览与商品报告入口；复用 review_analysis 图表 | `test_product_reviews.py` / `test_review_analysis.py` / `test_reviews.py`；归属/去重/历史/证据/未知/否定/目录复用 |
| 候选清单 | `candidates.py`；CatalogCandidate | 清单/编辑模板；现有候选视图下一次修改时可迁出 `views.py` | `test_candidates.py`，归属、重复、恢复、跨目录关联 |
| 浏览器主动观测 | `browser_capture.py` / `browser_capture_targets.py` / `ebay.py` / `browser_capture_records.py` / 固定资源及资源版本 `browser_capture_package.py`；Snapshot browser账号归属 | `browser_capture_views.py`、预览/私有报告模板、首页browser_recent私有卡片、独立CSS；Chrome扩展 `extensions/shophot-capture/` | `test_browser_capture*` / `test_ebay.py`，账号/CSRF/签名/幂等/并发/公共数据隔离；`test_browser_capture_onboarding.py`检查版本未知/安全读取/下载一致及桥接契约；Node popup专项与真实DOM证据，实站范围见扩展README |
| 物流核算与报价导入 | `shipping.py` / `shipping_forms.py` / `shipping_import.py` / `shipping_mapping.py` / `sf_rates.py` 固定官方逐档数据；ShippingRate，公开参考独立目录 | `shipping_views.py` / shipping 模板与 partial / `shipping.js` / `shipping.css`，利润内直接选择报价 | `test_shipping.py` / `test_shipping_mapping.py` / `test_sf_rates.py`，顺丰明确档位边界及物流→利润恢复、重量/燃油/币种/尾差、标准模板兼容、自有列及共同值、原行号/日期epoch/公式拒绝、签名归属/CSRF/幂等；来源与限制见 SHIPPING_MODULE.md |
| 利润工具 | `profit.py` 的 ledger 与定价反算，`profit_pricing.py` 零固定成本舍入边界；LogisticsProfitForm（复用 ProfitForm） | `profit.html`、`profit.js`、物流 partial | `test_profit.py` / `test_profit_flow.py` / `test_profit_pricing.py`，币种、减价比例、逐项舍入、HTMX元数据更新与最小达标价/有界搜索；物流 POST 重新核算 |
| 公共界面 | `ui.css`、`ui.js`、`base.html`、`partials/navigation.html`、`partials/research_filters.html` | 导航、布局、表单层级、手机菜单 | 浏览器桌面/移动及键盘验证 |
| 跟踪价格历史与导入 | Product / Snapshot、`importing.py`、现有视图 | 商品跟踪报告、导入、历史对比 | `tests.py`，快照顺序、导入原子性、CSV 安全 |

所有 Python 路径相对 `market/`，模板相对 `market/templates/market/`，资源相对 `market/static/market/`。模型暂时集中在 `models.py`，路由集中在 `urls.py`，迁移集中在 `migrations/`。

## 新模块的落地步骤

1. 写清用户入口、主要结果、数据来源、失败与空状态，明确本次范围。
2. 检查是否已有同类模型和服务。明确模块如何调用其他模块，保留商品链接与币种等稳定身份。
3. 先实现服务，再接视图与路由；新增模块使用 `<module>.py` 与 `<module>_views.py`，避免扩大历史 `views.py`。较大模块再提升为包，不预先拆空目录。
4. 模板复用公共导航、筛选组件和 UI 样式。领域规则留在服务中，JavaScript 负责交互，不重复实现统计规则。
5. 测试需要保护的行为：正确路径、未知值、非法输入、权限/CSRF、重复或重试及与现有数据兼容。不要仅断言模板长得像代码。
6. 实际浏览器确认结果、失败状态和手机布局；适当保存截图。模型变化检查迁移，公共逻辑变化跑全套。
7. 更新开发日志、用户文档与续接入口，说明已完成与仍有限制的部分。功能完成后再提交或交付，遵循用户授权。

## 主流程约定

首页优先一个网址输入框，默认自动识别。已保存报告可直接打开，但明确保存时间与更新入口；新店铺发现目录后采集首批最多 10 件，进度页轮询只读接口，完成后进入该店铺报告。其他商品显示采集进度，成功进入报告，失败显示原因与重试。

报告先让用户看到商品和报价，再提供高级筛选、词条树和价格分布。候选清单用于记录研究判断；数据管理入口为辅助，不要求用户在侧栏完成每一步。尚未接入的数据或缺失评价直接说明，不能通过 UI 填入假结论。

## 本地验证

```sh
bash scripts/start.sh
.venv/bin/python manage.py test market.test_workflows --noinput
.venv/bin/python manage.py test --noinput
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
git diff --check
```

服务为 `127.0.0.1:8000`，PostgreSQL 配置及启动见 `DATABASE.md`。测试使用单独测试数据库。开发进程采用 `--noreload`，更改 Python 或缓存模板后需重启；不要启动多个 worker。更新静态资源时更改相应版本标记，避免界面仍使用旧缓存。

## 物流自有表格维护边界

现有 `/tools/logistics/import/` 同时支持标准模板直接预览，以及自有CSV/单工作表XLSX的上传→表头/最多3条样本→选择源列或共同值→逐行校验→原签名报价预览→确认保存。不要另建报价库或导入入口；手填路径和标准模板含说明工作表继续兼容。

有界读取与单元格类型在 `shipping_import.py`，临时签名及对应表单在 `shipping_mapping.py`，接线在 `shipping_views.py`。映射目标只使用已有 `COLUMNS` / `ShippingRateForm`，不要根据列名猜金额、国家、币种、计费方式或未知费用。唯一完全一致标准表头可默认对应；共同值必须可见并由用户明确填写，计费方式/燃油基数中文下拉不设默认。日期映射后才按XLSX epoch转换；原行号不能丢失。同一源列不可复用，目标字段allowlist、POST重复字段和签名账号/过期校验必须保留。

本轮仅kg与明确币种的平面报价：2MB、100行、40列，样本和宽表内部横向滚动；复杂矩阵、多工作表选择、单位/汇率推断、公式或AI识别均未接入。扩大格式前应先取得真实货代样本并协调负责人，不松开ZIP/XML/公式/合并/未知字段边界。专项使用独立测试库，失败/空状态须实际浏览器留证，预览和失败不写库；最终全套和主服务统一由负责人执行。详细口径、数据上限和当前证据见 `SHIPPING_MODULE.md`。

原表样本宽表使用独立 `shipping-source-samples` / `shipping-source-scroll` 样式，普通列保持可读最小宽度、行号更窄、长文本限制宽度后换行，溢出只在 `.table-wrap` 内部滚动。不要让继承的任意位置换行把几十列压成逐字表头；实际浏览器同时检查样本区scrollWidth大于clientWidth、整页scrollWidth等于视口，并保留错误提示。改CSS时同步导入页面版本参数。


## 个人远程浏览器入口

独立运行边界见PERSONAL_ACCESS.md：config.personal_access/personal_runtime/personal_wsgi，scripts.start_personal与personal_gunicorn，requirements-personal额外依赖。只供个人HTTPS代理+邮箱门禁试用，原8000及单worker保持；测试config.test_personal_access，原config.production策略不降低。真实远端登录与公司网络仍需验收，项目私有配置/邮箱/URL/PID在.local，不提交。平台数据攻坚的官方字段/限制与下一入口见ALIEXPRESS_DATA_PLAN.md，文档和离线测试不等于实站支持。
