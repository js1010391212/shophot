# ShopHot MVP 复用审计（Issue #28）

审计交付日：2026-10-22（北京时间）；文件日期沿用任务编号。上级产品方向为 [Issue #26](https://github.com/js1010391212/shophot/issues/26)，本任务为 [Issue #28](https://github.com/js1010391212/shophot/issues/28)。

准确源码基线：`3dd4063e64365b9e710af6a8a159e8a8674a4d34`，树 `d11061921fe33367fc313519e096920f72f02fd6`；工作分支 `codex/mvp-reuse-audit-20261021`。本次恢复后的文档交付仅整理只读盘点和方案，没有执行业务实现、数据库操作、平台采集、浏览器或旧测试运行，也未改变服务或账号。本次唯一新增受跟踪文件为本文；不推送或部署。

范围说明：此前同轮续接曾转到创建管理员的账号事项，与 #28 文档范围分开；负责人报告已暂时停用仅该新增账号并私有留证，原有账号未改，详情见负责人交接。执行者曾说明该事项依据直接用户建账号要求；本文不披露账号或凭据。

结论：现有目录研究、报价历史、候选、物流核算、利润账本及私有记录值得复用。**“Shopify 目录中的某一次报价 → 利润 → 可追溯私有记录”尚未闭环**，不能用已有浏览器报价闭环代替验收。当前平台数据可用性由 #27 提供新证据；旧 Chrome 待验收不再阻挡本轮方案，但访问验证和来源限制继续保留。

## 一、复用矩阵与证据分级

下表路径以 `market/` 为根，模板以 `market/templates/market/` 为根；路由以 [market/urls.py](market/urls.py) 为准。“已实现”指基线代码存在；“历史实站”仅指既有日志明确记录的有限样本，不表示今天仍可采集；“受控”指回归或隔离 QA；“缺失”不以示意页面或历史测试代替。测试文件列为后续受影响回归定位，本轮未执行。

| 模块 | 服务、视图与 URL | 模板、测试 | 证据与复用决定 |
|---|---|---|---|
| 店铺输入与目录 | `workflows.py`、`discovery.py`、`jobs.py`；`views.analyze_competitor` POST `/analyze/` → `workflow_views.store_analysis` `/analysis/stores/<pk>/` | `workflow.html`、`research.html`；`test_workflows.py`、`test_discovery.py` | 已实现输入→进度→店铺报告。历史 Millys 自定义域名目录。直接复用；需让覆盖数和部分失败更明确。 |
| 目录报价和单品报告 | `catalog_prices.py`、`catalog_content.py`、`jobs.run_store_prices`；`views.catalog_detail` `/stores/<pk>/products/<index>/`，刷新为 POST `…/refresh/` | `catalog_detail.html`；`test_catalog_prices.py`、`test_catalog_content.py`、`test_catalog_detail.py` | 已实现公开 HTML/结构化报价、规格范围及部分评论。历史三店样本；身份错误/币种混合等为受控边界。复用，不能承诺全店/全部 SKU 或成交价。 |
| 独立跟踪商品 | `shopify.py`、`jobs.run_next`；`workflow_views.product_analysis` `/analysis/products/<pk>/` → `views.product_detail` `/products/<pk>/` | `workflow.html`、`detail.html`；`test_shopify.py`、`test_workflows.py`、`tests.py` | 已实现 Product/Snapshot 路径。多规格须明确选择，不能自动选最低价。与目录模型独立；不作为已存在的目录映射。 |
| 目录价格历史 | `price_history.py`；`price_history_views.catalog_history` `/stores/<pk>/products/<index>/history/` | `price_history.html`；`test_price_history.py` | 已实现同 URL、同币种和同规格签名比较。历史 Beard Comb 两次更新及空状态实测。直接复用；旧无签名点保留但不判断涨跌。 |
| 定时价格监测 | `price_monitoring.py`、现有 worker；`price_monitoring_views.monitors/configure/toggle`，`/monitoring/`、目录 `…/monitor/` | `price_monitors.html`、`price_monitor_config.html`；`test_price_monitoring.py` | 已实现账号计划、共享报价队列、暂停恢复与退避。历史短时开启/暂停/恢复；跨天运行仅受控，不称长期实测。复用；缺全店新品/下架监听和通知。 |
| 店铺词条与跨店研究 | `research.py`、`catalog_research.py`；`views.keyword_research/catalog_market/catalog_compare/catalog_export`，`/stores/<pk>/research/`、`/research/products/`、`…/compare/`、`…/export/` | `research.html`、`catalog_market.html`、`catalog_compare.html`；`test_catalog_market.py`、`test_catalog_detail.py` | 已实现词条树、筛选、同币种比较和导出，历史样本页面验证。复用；词频不是搜索量，异类商品可展示但不自动认定竞争关系。 |
| 样本市场 | `sample_market.py`；`sample_market_views.sample_market` `/research/market/` | `sample_market.html`；`test_sample_market.py` | 已实现最新目录有限样本、价格段与覆盖分母。历史存量目录页面验证；去重和币种为受控。复用，名称坚持“样本”，不推算全市场销量/份额。 |
| 候选清单 | `candidates.py`；`views.candidates/candidate_add/candidate_compare`，`/candidates/`、`…/compare/`、POST 目录 `…/save/`，编辑/归档/恢复沿用既有路由 | `candidates.html`、`candidate_edit.html`、`catalog_compare.html`；`test_candidates.py` | 已实现私有收藏/备注、按 URL 关联最新目录。历史页面与受控归属验证。直接复用；缺精确目录报价进入利润及候选→研究记录的来源接线。 |
| 评论与商品内容 | `reviews.py`、`review_analysis.py`、`product_reviews.py`；`views.catalog_detail`、`product_review_views.product_reviews` `/products/<pk>/reviews/` | `catalog_detail.html`、`product_reviews.html`；`test_reviews.py`、`test_review_analysis.py`、`test_product_reviews.py` | 已实现有限公开评论/导入样本主题。历史 Beardbrand 有样本，其他来源可未知。复用；小样本不能推断整体质量，不承诺全量评论。 |
| 物流报价与导入 | `shipping.py`、`shipping_import.py`、`shipping_mapping.py`、`sf_rates.py`；`shipping_views.logistics/rate_edit/import_rates`，`/tools/logistics/`、`…/rates/new/`、`…/import/` | `shipping.html`、`shipping_rate_form.html`、`shipping_import.html`；`test_shipping.py`、`test_shipping_mapping.py`、`test_sf_rates.py` | 已实现手填/私有报价库、CSV/单表 XLSX 映射预览确认、官方顺丰参考档位。历史 UI 与受控核算；真实货代合同和复杂矩阵缺失。直接复用，不猜单位/费用/税费。 |
| 利润账本与定价 | `profit.py`、`profit_pricing.py`、`profit_references.py`；`profit_views.profit` `/tools/profit/` | `profit.html`；`test_profit.py`、`test_profit_flow.py`、`test_profit_pricing.py`、`test_profit_references.py` | 已实现多币种、汇率、逐项舍入、物流重算和反算；已有来源引用仅两类，见下节。历史个人核验和受控 QA。复用计算，不重写数学。 |
| 预算和成本判断 | `trial_budget.py`、`selection_assessment.py`，复用 `profit_views.profit` 和原表单链 | `profit.html`；`test_trial_budget.py`、`test_selection_assessment.py` | 已实现单件/批次成本、资金准备与成本判断；受控 QA。复用，不把资金储备当费用，不把成本结论当需求预测。 |
| 私有记录/历史比较 | `profit_studies.py`、`study_comparison.py`；`profit_study_views.save/library/detail/toggle` `/tools/profit/studies/`、POST `…/save/`、`…/<pk>/`；`study_comparison_views.comparison` `…/compare/` | `profit_study_list.html`、`profit_study_detail.html`、`study_comparison.html`；`test_profit_studies.py`、`test_study_comparison.py` | 已实现签名、重新核算、不可变历史、继续、软移出恢复及账号隔离。2026-10-13 受控普通账号完整流程，不是 Shopify 新采集闭环。复用；扩来源须演进契约。 |

证据入口（均为基线内既有材料）：

- [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)：2026-10-07 目录/详情；2026-10-08“研究筛选、价格分布与随机三店验证”“个人候选商品清单”“公开报价历史分析”“定时价格监测”“样本市场分析”；2026-10-09 物流映射/顺丰与利润核验；2026-10-13 私有研究记录/比较及最终受控流程。历史测试数量不作为本轮新测试结果。
- [CROSS_PLATFORM_VALIDATION.md](CROSS_PLATFORM_VALIDATION.md)：Millys、Beardbrand、Occam 每家有限商品样本。2026-10-08 三店共六条报价成功不能推广为任意店可用。评论未知保留未知。
- [MVP_ACCEPTANCE_MATRIX.md](MVP_ACCEPTANCE_MATRIX.md)、[PILOT_READINESS.md](PILOT_READINESS.md)：个人本机与外部试用发布门槛分开。旧 eBay 单刊登、Ali 受限和扩展待验收不作为 Shopify 全链路证据。
- [SHIPPING_MODULE.md](SHIPPING_MODULE.md)：导入格式/重量/燃油/来源口径；官方参考不替代卖家实际合同价。

## 二、一条主路径及真实断点

目标路径：**Shopify 店铺 URL → 进度 → 店铺目录/商品报价/历史 → 私有候选 → 物流手填或导入 → 利润 → 私有保存**。

当前可运行段：

1. 首页 POST `/analyze/`，店铺根 URL 经规范化进入现有 workflow；GET 进度不创建任务。完成进入 `/stores/<pk>/research/`，报告内开商品/历史。已有成功报告可能复用，必须显示保存时间，不能暗示刚采集。
2. 目录写入 `StoreDiscovery.products` JSON；成功报价另外写 `CatalogPriceObservation`。后者保存 URL、上下限、币种、观测时间和 `quote_scope`，**没有 Product/Snapshot 外键，也没有专用已确认国家/市场字段**。任务仅部分报价成功也可能总体 succeeded，应看分子/分母和失败详情。
3. 候选按账号和规范化 URL 保存，保留目录/原始项上下文，能返回商品报告；最新目录缺少链接时保留旧项，不表示下架。报告、候选与对比目前没有精确目录观测利润入口。
4. 用户今天仍可打开原利润工具，手填假设售价、币种与采购成本；直接选择现有物流报价或手填，必要时进入既有导入预览确认。利润内 POST 重算，再保存私有记录。这是**用户假设测算**，没有自动保存完整候选/目录报价来源关联；离开利润去物流管理/导入也没有已验证的来源上下文往返闭环。

不能省略的契约：

- `Product/Snapshot` 为另一条跟踪数据图。目录刷新不会自动建这两个对象；把同一个目录商品基础 URL 再提交首页还可能返回既有目录报告，不能称为转换入口。
- `profit_references.resolve_reference` 的 `observation` 是本账号 **browser Snapshot** 的精确 PK；`product` 是 Product PK，解析该商品当时最新的公共 Snapshot。它们都不是 CatalogPriceObservation PK，即使整数相同也不能混用。
- 公共 Product 引用不是任意历史点精确固定；图表选择币种不代表利润链接固定该历史点。公共引用的 `data={}`，原 Snapshot.context 中规格/地区提示不会完整转成来源事实。浏览器精确引用可用，仍不得推定未知市场条件。
- `profit_studies.unpack` 严格检查 source 键集合、`kind in ('observation','product')` 和 `snapshot_id`；保存重新解析并锁定 Snapshot，继续/来源链接/比较也按该契约工作。**新增 catalog 来源须同时处理签名、保存再核验、继续测算、历史展示和旧 version1 兼容；不是增加 URL 参数或按钮即可完成。** 旧私有记录不得改写。
- 目录低价/高价是公开规格范围，不是单个 SKU 的售价，更不是采购成本。不能默认最低价进入利润。精确引用需明确一条历史观测及其中可验证的规格身份；未知或截断规格只允许明确手填假设。
- `quote_scope` 的可比签名含 URL/币种/规格身份，不含价格；签名相同才比较上下限。请求国家参数不证明国家实际生效；税/运费/结账价格不明必须继续标未知。未来引用应独立保留原 URL（含市场参数）、观测 PK/时间/币种、范围与规格、来源及未知条件，不从标题猜市场。
- 现有目录、公共 Product/报价共享；候选、浏览器报价、物流自有报价、监测计划和研究记录按账号隔离。不能称全部数据已租户隔离；新引用不得泄露别人的私有来源。

缺失的独立能力：全店商品新增/消失差异服务、确切上架/下架日期、全量评论、真实销量/广告/流量、采购供应商报价匹配、受限平台稳定数据接口。本首轮不新增这些功能；已有样本研究/物流/数学成果保留。

## 三、状态文案与页级线框

| 状态 | 建议可见文案与行为 |
|---|---|
| 成功 | “目录发现 N 个链接；本批尝试 A 个，取得 Q 个报价；观测于 T。” 展示真实覆盖口径，首批最多 10 件不得写“全店已分析”。 |
| 未覆盖/未支持 | “当前来源尚不能分析该平台/网址；未创建有效报告。” 不假装排队成功，不借 Shopify 域名后缀推断自定义域名身份。 |
| 截断 | “只展示受限公开目录样本（最多前三份商品站点地图/100 个链接）；未覆盖部分未知。” 有限规格也明确截断，不以样本数当库存总量。 |
| 失败/部分失败 | “本次更新失败：具体原因；保留上次成功报价（T）。” 部分成功逐项展示，区分未尝试、访问限制和解析失败；不覆盖成功历史、不绕过验证。 |
| 空结果 | “没有发现可识别的公开商品链接，不代表店铺没有商品。” 筛选无匹配另写“当前筛选无结果，可清除筛选”。当前 discovery 无链接会抛 CollectionError，workflow 虽有 succeeded-empty 分支，尚不能称来源空目录已统一为成功空状态。 |
| 无报价 | “已有商品链接，尚无有效报价”；补充“未采集/本次失败/仅有旧报价/规格范围未明确”之一。未知不补零，不能显示无依据的涨跌或利润。 |

`sitemap.lastmod` 仅为站点地图声明的更新时间，不是上架时间。未来目录差异只可写“本次首次观察到链接（非上架日期）”“本次覆盖未见（非下架）”；覆盖截断或采集失败更不能据此删旧数据。目前尚无该差异服务。

建议页级文字线框（方案，不是已实现 UI）：

```text
首页：网址输入 → [分析] → 同流程进度/具体失败原因
店铺报告：店名/URL/观测时间
          覆盖 N、尝试 A、有效 Q、截断/旧数据提示
          商品列表：价格+币种+规格范围 / 历史 / [加入候选]
商品或候选详情：原报价与证据 / 历史 / 备注
          [成本测算]（须先完成下面的来源契约任务；当前缺失）
利润页：来源事实（只读） | 假设售价与成本（可改）
          物流手填/已有报价；需要导入时使用原物流模块
          [计算] → 单件账本/预算/缺失项 → [保存私有研究记录]
保存后：本次来源与假设 / 不可变历史 / [继续测算]
```

每页只有一个主要动作；树图、筛选与比较留在报告内作辅助。来源无效、无价、范围未选时保留报告/手填说明，不制造可自动带入的假金额。导入/保存均维持 POST、CSRF、账号归属；GET 只读。

## 四、最多两个后续有界任务（待负责人立项）

### 任务 1：报告覆盖口径和失败状态收口

目的：先让用户读懂“拿到多少、哪些未知”，不新增采集器/模型/侧栏。

- 本地 medium 所有权：新增独立 `market/catalog_coverage.py` 和 `market/test_catalog_coverage.py`；有限调整 `market/workflow_views.py`、`market/templates/market/workflow.html`、`market/templates/market/research.html`。若报告需额外上下文，仅由负责人协调 `views.keyword_research` 的薄接线，不扩展历史集中视图职责。
- 输入契约：既有 discovery/products、limited、当前/最近报价任务与成功观测元数据；输出明确的目录覆盖数、任务尝试/成功数、旧报价时间及状态。不能把任务 processed 当成功，不能用旧有效报价当本次成功，不能凭缺失字段补 0。
- 依赖：#27 明确新样本来源和当前访问结果；已有受控样本足以验证状态，真实来源重新可用才标实站通过。无新增全店差异或定时任务。
- 验收：完整成功、部分成功、截断、空筛选、无链接失败、未尝试及保留旧成功历史均有明确文案；GET 无任务写入；受影响 workflow/coverage 回归。负责人在获准运行环境验证桌面/390 布局及实际错误页截图。纯文案不重复全套数学测试。

### 任务 2：一个明确目录报价进入私有测算记录

目的：只补齐“单条明确报价→利润→保存→继续”的断点，不扩成所有 SKU/所有市场或 ERP。

- 先决范围：仅一条具有可核验明确规格、单值金额与币种的 CatalogPriceObservation；聚合范围、多规格/截断/未知市场不可静默选择。无满足条件样本时先报告阻断，手填仍标假设。
- 本地 medium 主责新增 `market/catalog_profit_references.py`、专项测试及目录详情/利润来源展示的有限接线；负责人统一所有权协调 `profit_references.py`、`profit_views.py`、`profit_studies.py`、`study_comparison.py`、`profit_study_views.py` 和相关测试的共享契约修改。高级 high 只审数据身份/市场/规格判定，负责 #27 数据前提；不并发修改同文件。不引入新 URL/模型前先由负责人评估现有路由与 JSON 场景能否复用。
- 契约交付须先定稿：独立 catalog 来源标识，不能复用 browser observation 参数；准确观测 PK/URL/规格/币种/时间/quote_scope 与已知和未知市场事实。成本和假设售价与原报价分开；不为接线自动创建 Product/Snapshot。私有 candidate 上下文必须校验归属，未关联可明确为空。
- 来源契约要覆盖签名/再核验/锁定策略、保存幂等、历史详情/报告链接/继续和比较兼容。应设计显式新场景版本并保留 version1 读取/继续与比较边界，不能放宽旧 source allowlist 后声称兼容。若文件范围过大，在立项时缩为单值且来源事实只读的子范围，但未完成保存契约之前**不得称主路径闭环**。
- 物流沿用利润内手填和已保存报价，金额按原服务重算；本任务不承诺来源保留的管理页/导入往返。真实表格仍走原导入模块，返回利润重新选择报价。若要求保持未保存情景往返，必须另立契约，不能猜 GET 参数恢复成功。
- 验收：精确观测不因后续刷新漂移；币种/规格不明、失效来源、重复参数、整数撞号不能误带；范围报价不取最低价；原公共 Product/私有 browser 引用与手填兼容；另一账号无法引用私有候选/记录；保存后来源和假设可区分，继续再核算，旧 v1 历史不改写。跑受影响 reference/studies/comparison 回归；共享逻辑完成后由负责人统一必要全套、check/迁移一致性及一次真实店铺→保存验收。无实际证据不标实站通过。

本次恢复后的文档交付停止线：只冻结本文与既有 #28 结果评论的范围更正，不执行账号、数据库或服务操作。上述任务均未实施；新采集证据、真实物流合同和发布验收由负责人结合 #27 安排。保留全部既有成果和数据，不因产品方向调整删除旧模块或放宽平台访问边界。
