# 价格与 SKU 传递：只读复用审查

日期：2026-10-22（北京时间）。准确基线 `f2b2feb78174fbc46a3b742d97031d3e2f8d6936`；业务 main `36184b9faaa756e5de53c9788d560bf1c7554ea5`。独立克隆 `.local/live-prices-reuse-20261022`，分支 `codex/live-prices-reuse-20261022`。本轮只读源码/既有测试定位，仅新增本文；未运行 ORM、测试、浏览器、服务或外部 HTTP，未读取主库/凭据。

结论：**原生 Shopify HTML 若取得唯一目标 Product/ProductGroup 的 price + currency + 明确 SKU/规格，可以直接复用现有采集结果→目录 JSON/独立观测→报告→私有候选链路。单值金额不等于单 SKU，多规格同价也不等于单 SKU。** High 新来源尚无本轮样本，本审查不证明实时来源成功；若最终来源是另一平台的官方 API，不能把它当成现有 HTML collector 的即插即用输入。

## 1. 实际数据流与源码位置

位置均按上述基线定位，文件链接相对仓库；行号为本轮核验位置。

| 环节 | 已有实现/位置 | 可直接复用与限制 |
|---|---|---|
| 店铺→目录 | [discovery.py](market/discovery.py):18 `store_url`、:36 `discover`；[models.py](market/models.py):127 `StoreDiscovery` | HTTPS 根 URL、同域 sitemap、有限链接写 `products` JSON；默认是 Shopify 风格路径/商品 sitemap，不是任意电商/API 的目录适配器。纯目录只有链接/标题，不能生成价格/SKU。 |
| HTML→报价/规格 | [catalog_prices.py](market/catalog_prices.py):21 `parse_catalog_price`，尤其 :75–118；[catalog_content.py](market/catalog_content.py):45 `product_content` | 唯一目标结构化 Product/ProductGroup；每个 Offer 生成规格行，读 offer/owner 的 SKU，保留 name/size/color、URL、上下限、币种、库存。商品级 sku 与规格 sku 是两处字段，父级空不应抹去子规格真实 SKU。 |
| 分规格与聚合 | `catalog_prices.py`:81–106、:114–118；`catalog_content.py`:68–73 | price 为主要货币单位；AggregateOffer 保留 low/high。整商品用所有已解析 Offer 的 min/max；混币种整个结果拒绝。`variants` 最多 100 行，`variants_limited` 保留截断；不能把展示的前 100 行说成完整规格。 |
| 写库 | [jobs.py](market/jobs.py):93 `run_store_prices`，:111–123 callback；[models.py](market/models.py):160 `CatalogPriceObservation` | 成功同时更新目录项完整结果并创建本 job 的独立报价；失败只回写错误/尝试时间，保留旧成功。独立观测有商品 URL、上下限、币种、时间、quote_scope，**没有独立 SKU 字段/每 SKU 历史金额行**；job+URL 唯一。 |
| 规格身份/历史 | [price_history.py](market/price_history.py):18 `capture_quote_scope`、:53 `observations_for_url`、:60 `compare_quotes` | scope v1 保存规格 URL/SKU/名称/尺寸/颜色/range 和身份签名；签名含币种/目标，不含金额/库存。仅同币种同签名比较上下限。旧 scope 缺失/截断/身份不明不推涨跌；一次报价不是趋势。 |
| 店铺竞品报告 | [catalog_coverage.py](market/catalog_coverage.py):21 `quote_values`、:54 `build_catalog_coverage`；[research.py](market/research.py):61 `build_research`、:31 `price_distribution`；[views.py](market/views.py):340 `keyword_research` | 当前 job 真实独立观测驱动新报价数量和价格展示，词条/价格段继续复用。价格分布每商品取最低边界、币种分组，既不是选定 SKU 报价，也不是销售分布。主商品表目前无 SKU/规格数量摘要。 |
| 商品详情 | `views.py`:384 `catalog_detail`；[catalog_detail.html](market/templates/market/catalog_detail.html):37–41 | 已有逐规格 SKU/URL/价格范围/币种/库存表；近期独立报价与历史入口已有。规格表来自当前目录 JSON，历史观测并没有同样的逐 SKU 金额表，不能把当前规格价格填回过去。 |
| 私有候选 | [candidates.py](market/candidates.py):11 `candidate_url`、:19 `save_candidate`、:32 `candidate_rows`；`views.py`:451 `candidate_add`、:463 `candidates` | 保存的是目录商品项 `saved_item`（可含完整规格）及 URL，按账号+URL 唯一，备注私有。URL 保留规格/市场 query；展示优先最新成功目录，否则保留旧项，不因目录缺失判下架。收藏入口取目录 index，**没有显式选择某 SKU 的收藏动作**，也不固定某条报价观测。 |
| 候选比较与利润引用 | [catalog_research.py](market/catalog_research.py):15 `catalog_rows`、:26 `comparison_rows`；[catalog_profit_references.py](market/catalog_profit_references.py):20 `single_scope`、:58 `validate_quote`、:72 `resolve_catalog`、:148 `candidate_profit_link` | 候选比较限制同币种，不等于规格等价。目录利润只接单值+单个可验证明确规格，候选链接固定实际 observation id/私有候选上下文；范围/多规格同价/无身份均拒绝。已有 v2 来源签名/保存/继续完整链路，无需重建。 |

关键补充：候选页面价格来自“最新目录 JSON 或保存项”；利润按钮则从同店同 URL 的独立观测取最近一条并校验（`candidate_profit_link`:148）。二者不是天然同一时点，必须以利润页实际引用的 id/时间/条件为准，不把候选当作固定单 SKU 价格历史记录。

## 2. 不能混称的四种情况

| 真实数据形态 | 正确展示/可用能力 | 不能作出的结论 |
|---|---|---|
| 一个明确规格，SKU 或可验证规格身份，单值+币种 | “单一明确规格公开报价”；原报告/详情/候选可用，满足既有 single_scope 后可进利润 | 未提供 SKU 编号时只能说规格明确，不能说“SKU 编号已确认”；地区/优惠/税运继续未知。 |
| 一个单值，但无 SKU/规格身份 | “单值公开报价，规格身份未知”；有效金额可进商品统计 | `capture_quote_scope` 允许单一匿名非范围 Offer 生成 scope，因此“有签名/variant_count=1”本身不证明精确 SKU。既有利润 single_scope 会进一步拒绝无身份。 |
| 多规格，金额相同 | 商品边界仍为 X–X；详情显示各规格，身份数量仍为多条 | low==high 不证明只有一个 SKU；既有利润入口仍应拒绝多规格直接引用。 |
| AggregateOffer 或多规格不同价 | “公开规格范围/报价边界”；详情可展示当前逐规格，历史仅比较同范围边界 | 最低价不是用户选定 SKU 价；上下限不变不证明中间每个 SKU 价格不变，不能从范围反推每 SKU 历史价格。 |

`catalog_content.same_product`:15 比较 HTTPS 主机/商品 path，**不验证 query 已选择某一 variant 或国家已生效**。它证明同一个基础商品，不足以证明某个 SKU/市场。SKU 是来源声明的商品/规格标识；不能拿标题、内部记录 id、商品 handle 或价格猜一个 SKU。

与独立跟踪区分：`shopify.py`:94 `parse_shopify` 确认 handle，显式 variant 必须唯一匹配；多规格未选择则失败；从真实 cart 取币种、整数价格按该接口的 minor-unit 约定转换。它走 Product/Snapshot，与目录观测不自动映射；`collect_shopify`:133 会请求 product.js/cart.js，**不得为接线擅自请求受禁接口或拿它绕开原 HTML 限制**。另一 API 的主要货币单位金额不能套用这里 `/100`。

## 3. High 新样本交接的最小契约

样本必须先有合法访问/允许用途、当前真实响应及身份证据，由负责人统一验收；以下是接线要求，不是已经拿到的数据：

1. 确认来源方法（HTML/API）、真实店铺与商品 URL、实际返回商品身份、观测时间、响应证据 hash/范围；公开展示链接与真正报价 API endpoint 不应互相冒充。
2. 价格明确单位、币种和条件：retail/促销/会员/数量阶梯、是否最低起购数量、税运未知、规格覆盖是否截断。若只提供 product id 而未定义其为 SKU，不填 SKU；按来源真实字段保留。
3. 最小成功结果遵循既有 callback：`price_title`、合法两位主要单位 `price_low/price_high`、三位币种、`availability`（未知空字符串，不猜有货），以及 `price_source/price_observed_at`。
4. 需要规格能力时提供真实 `variants` 列表：`url/name/sku/size/color/price_low/price_high/currency/availability/is_range`；`variants_limited` 保留。单 SKU 行 low=high；范围行 is_range=True；多个相同价的规格仍为多行。没有原始逐规格价格时不拆造。
5. 继续用 `capture_quote_scope` 的原始生成逻辑，不由适配器自造“可信 signature”；没有完整匹配规格时 scope={}。失败 result 只含明确 `price_error` 等错误信息，不塞 price=0 或借旧规格补新观测。

保存时 `run_store_prices` 使用写入回调的 `now` 作为独立观测 `observed_at`，目录内另有结果时间字符串；如果未来来源携带早于本轮获取的 source as-of 时间，不能把采集时点与来源生效时点混为一谈。现有模型没有专门 source-as-of 字段，需要单独定契约，而不是覆盖历史 observed_at。

## 4. 最小改动建议（尚未实施）

**优先情形 A：当前原生 HTML 链路已经能产出上述结构。** 不改模型/路由/worker/利润；先以原首批任务保存本轮数据，原详情直接可展示 SKU。若主报告/候选必须在列表里看到规格信息，仅新增一个只读规格摘要 helper/partial，接入当前报告和候选展示：把“金额形态（单值/范围）”与“规格覆盖（单一明确/多条/未知/截断）”分成两个事实，不用一个 low==high 布尔值代替 SKU 身份。先不改报价计数、分布、历史比较或候选 key。具体文件所有权由负责人依样本另行授权。

**条件情形 B：新来源只提供另一平台的 API 响应。** 当前 `collect_catalog_prices`:121 固定校验 Shopify 商品路径、同域和 HTML content-type；`discover`:36 固定 sitemap 路径/商品链接，不能直接把 JSON URL 填进现有网络函数。最小方案应是独立的受限来源适配服务，复用输入校验和相同结果 DTO，再由负责人批准必要的来源识别/任务 dispatch 薄接线；不把 API 包装成伪造 Product HTML/Snapshot，也不预先扩建全平台系统。

API 情形还有一个具体存储缺口：目录 JSON 能保留 `price_source`，但 CatalogPriceObservation 当前没有独立的“HTML/API方法、真实证据 endpoint、来源条件/as-of”字段；scope v1 只含身份、利润 catalog v2 条件文案也写“公开页面历史报价”。因此**不能声称只接 callback 就已经完整保存 API 来源与条件**。先由负责人决定必要的不可变来源契约（含旧 scope/v2 兼容），再做最小实现；不能事先假定不需迁移，也不能把方法/数量阶梯条件丢掉。样本未到，本轮不设计新模型或改签名版本。

**暂缓：历史逐 SKU 价格、按 SKU 私有收藏、批量选某规格进利润。** 旧 scope 只记录身份而没有每 SKU 价格，当前候选还是商品 URL 收藏。需要真实不可变逐规格金额和明确选中身份后另立小任务；不能靠当前目录 JSON 回填历史、把每个 SKU 偷换成目录商品分母，或把每次范围最低价当“目标 SKU”来绕过现有校验。

验收建议仅定位，不在本轮执行：`test_catalog_prices.py`（目标身份/单一币种/主要单位）；`test_catalog_content.py`（逐规格 SKU/范围/截断）；`test_price_history.py`（同条件/旧 scope/真实成功才保存）；`test_catalog_profit_references.py`（多规格同价拒绝、范围拒绝、市场不匹配、精确引用）；`test_candidates.py`（归属/URL/重排/保留旧项）。若新 API 特有数量/单位/来源形态，应有独立受控适配测试，不能拿现有 HTML 回归或历史样本冒充本轮真实获取。

## 5. 本轮停止线

仅本文冻结提交。执行的检查为源码函数/位置的 AST 定位、文档本地链接存在与 diff 检查；没有业务代码改动、测试/ORM/主库/管理员/凭据/浏览器/HTTP/服务操作。High 提供真实样本后，负责人再分派必要接线；本地队不等待并扩建未获授权的功能，不重审此前覆盖/范围 P2，也不向其他线程发送消息。
