# Adafruit真实价格来源：Phase A样本与接线契约

基线 `f2b2feb78174fbc46a3b742d97031d3e2f8d6936`；专属克隆`.local/live-prices-source-20261022`，分支`codex/live-prices-source-20261022`。本阶段仅事实取证与本说明，未改业务代码、主库、账号、配置或服务；只使用一个新候选，没有重取任何EFF/LILYGO/Beardbrand/Ali受限资源。

**本轮实际取得新的公开挂牌价：商家明确SKU4864，已选“Pico without Headers”，4.00 USD，缺货。** 商品身份、选择控件、可见主价格、结构化与OG币种/金额已离线交叉核对。不是API成功、成交价或可下单承诺，也不是已完成整条店铺报告链路。

## 访问与用途依据

[官方API说明](https://www.adafruit.com/products_api)真实200，说明应用导入和网店用途、最多5次/分钟、不得图片热链。当前真实robots却明确排除`/api/`，所以**API请求0次**；不把文档宣传或无需密钥误当可绕robots，也不将API内容授权迁移给HTML。

独立HTML路径依据：[现行网站条款](https://www.adafruit.com/terms_of_service/)与[隐私/法律页](https://www.adafruit.com/privacy)均已实取并核全文，未发现禁止本次低量私人公开事实观察的适用条款；robots明确允许商品展示路径。负责人亦独立核保存正文并将范围限定为本机私人研究。只记录身份、明确SKU/版本、金额/币种、条件与时间，不转载描述/图片/商标素材，不热链图片，不称获得通用商业再分发许可或法律保证。

原PublicProductTransport、TLS/公网IP校验、trust_env=False、不跟随重定向继续；元数据和商品请求均有界，保存非敏感的Content-Type/Date/Retry-After及挑战/认证提示头，不保存cookie/授权头。当前机器人规则的API禁止与独立HTML允许分别执行，没有借HTML重取被禁API资源。

## 真实样本与语义

| 字段 | 已验证事实 / 明确未知 |
| --- | --- |
| 展示URL及真实报价端点 | 均为`https://www.adafruit.com/product/4864`，一次正常HTML GET |
| 名称 / 身份 | Raspberry Pi Pico RP2040；目标路径PID、可见Product ID、JSON-LD显式sku均为4864 |
| SKU / 选中版本 | `sku=4864`确实来自声明SKU字段，不仅是猜测product_id。重复响应式选项均以`ui-selected`、`aria-current=page`、`data-part-id=4864`及`/product/4864`指向无排针版本 |
| 金额 / 单位 | 主价格content=4、可见$4.00、OG4.00与JSON-LD Offer4一致；主要货币单位4.00，不是Shopify的分值整数，不除100 |
| 币种 | DOM priceCurrency、OG currency、JSON-LD均明确USD，未从裸$、语言或域名推测 |
| 价格类型 / 条件 | 未登录公开挂牌/零售展示价。当前缺货，不能解释为可执行购买报价；数量门槛/阶梯、会员或经销商价、税运、优惠适用性、收货国家均未确认，不补0或“无” |
| 其他版本 | 当前页还链接4883/5525/5526/5544，不属于所选SKU；未请求、未混价，没有因为low==high就声称它们是一规格 |
| 状态 | DOM、已选版本文字与schema均OutOfStock；不是库存数量0的推算。没有浏览器切换版本实测承诺 |
| 原始价格as-of | 未获得可验证的价格更新时间；HTTP Date不是价格更新时点 |
| 本次观察 | 开始UTC`2026-10-22T07:05:27.288790+00:00`，正文取得`07:05:28.997414+00:00`；HTTP Date`Thu, 22 Oct 2026 07:05:28 GMT` |

## 关键网络证据

均为客户端解码后正文长度/SHA256；所有资源HTTPS200，无额外重定向、挑战或权限失败。该次保存的Retry-After、WWW-Authenticate、CF-Mitigated头均为null，指本次没有返回这些头，不保证未来无访问限制。

| 资源 | 字节 | SHA256 |
| --- | --- | --- |
| `/robots.txt`，06:58:25–06:58:26 UTC | 310 | `d48c3bfae49688bf2c504f8596d62ad036a3f31ebc028d1a64f3c42adcbaf7f7` |
| `/products_api`，06:58:38–06:58:39 UTC | 38969 | `12c04f903519e5371d5a099f5318b0626d1f2cfcee6190936783634eb3aa07b6` |
| `/terms_of_service/`，07:02:34–07:02:36 UTC | 58697 | `9622f71e4c53302cf5539012a808cbd83d458a5b2fdb4c3cf0582f074f2e1f07` |
| `/privacy`，07:02:48–07:02:49 UTC | 78250 | `3008062ef64b01a3534398f6b12eee3290de671f0a24429b53e3873682b752db` |
| 商品HTML，07:05:27–07:05:28 UTC | 109893 | `d110fd58dcf4952e94a78fa4f2b2d02e8b866cf207eb3e8be1896223edcaa29f` |
| `/sitemap.xml`，07:11:59–07:12:01 UTC | 1204160 | `38594f85fda00675f0b1c32ab602186ca14b6352a902fbfd766d113f4c3fa5a0` |

## 官方目录与复用路径

robots声明了HTTP sitemap路径；本轮从未请求HTTP，而独立验证其HTTPS同路径端点200。该原始urlset包含**6396个URL，其中5665个唯一规范`https://www.adafruit.com/product/正整数`商品URL**，确实包含4864。没有直接title字段；其余条目不能补造标题或报价。该商品声明lastmod为2025-01-23，不是本轮价格as-of，不据此推断价格一直未变。

当前`discovery.py`只接受Shopify的`/products/handle`，会跳过Adafruit的`/product/PID`，但现有StoreDiscovery/products、报价DTO和报告仍可复用。需要精确主机白名单的来源分派与规范URL校验，不需要另建商品库或假造Shopify链接。对5665个链接仍应采用有限目录/批次，标记截取；不能称库存、在售数量或市场覆盖。

当前通用`parse_catalog_price`对该保存正文**正确拒绝**：主Product没有url/@id/canonical，只有Offer指向非www的同商家URL；sku还是JSON整数。不能为一个新来源全局放宽商品归属、强行伪造canonical、把PID当任何平台SKU或把JSON冒充HTML。

最小后续契约：仅精确Adafruit主机的HTML适配，强制目标PID、显式schema SKU、可见PID、明确所选版本与多处主价格/币种一致；非www Offer只作该固定来源的离线身份声明，实际网络始终规范www URL。DTO复用`price_title/low/high/currency/availability/price_source/price_observed_at/variants`，所选SKU归一为字符串4864、金额4.00。其他版本不混入；描述/图片不抓。目录与报价薄分派由负责人协调，通用identity/transport/模型/worker/路由保持。

现有独立观测仅保存范围和scope，不会自动持久化任意新方法/条件字段。本例来源端点就是商品HTML展示URL；未知数量/税运/会员条件继续未知。接线及报告/利润仍须负责人明确条件、身份与保存契约后独立验收，不因一份源样本就声称已支持整个商家、连续价格或购货决策。

## 私有复演证据与验证

本克隆`.local/live-price-evidence/`全部目录0700、文件0600，Git不提交原HTML/政策/脚本/JSON：

- `adafruit-20261022T065825345601Z/`：robots与API文档、API被规则禁止且未请求的RUN_RECEIPT。
- `adafruit-html-terms-20261022T070234872626Z/`：独立HTML条款/隐私原文及头信息。
- `adafruit-html-20261022T070527287865Z/`：商品原HTML、显式使用边界、HTML_RUN_RECEIPT、仅最少事实的NORMALIZED_SAMPLE.json与OFFLINE_VALIDATION.json。
- `adafruit-directory-20261022T071159059749Z/`：原sitemap与DIRECTORY_RECEIPT/CONTRACT，明确6396总URL和5665规范商品链接。
- `adafruit_once.py`、`adafruit_html_terms.py`、`adafruit_html_once.py`、`adafruit_directory_probe.py`为精确执行脚本；`validate_saved_html.py`仅离线交叉核对，未改共享代码或访问数据库。

原始响应身份/金额/币种/选中版本和正文哈希已离线核验；旧解析器拒绝已复现。无应用代码变化，不重复PG/浏览器全套。实际自动Web输入→目录→价格→报告仍待接线，当前不宣称通过。Phase A准确提交及受限复演方法由`.local/PHASE_A_DELIVERY_RECEIPT.json`固定；将来网络重演仍须重新核当前允许用途与robots，不自动重取任何受拒资源。

## PRICE-HTML-B：专用离线适配交付

Phase A已冻结为`4a3e6ee225c9aefd30a9c149a20c6be3baec1df0`。本次新增仅`market/adafruit_catalog.py`、`market/test_adafruit_catalog.py`，并更新本说明；不改共享模块、模型、服务、数据库或网络策略。负责人管理薄接线与UI，本提交不宣称报告全链路通过。

接口：`is_adafruit_store(root)`只认精确HTTPS www根；`normalize_adafruit_product_url(value)`只认同主机`/product/正整数`，拒绝端口、认证、查询、片段和别名，错误抛`ValidationError`；`parse_adafruit_price(html,target)`纯离线，失败抛`CollectionError`。无`discovery`/`catalog_prices`导入。非www只认固定商家Offer身份声明，绝不生成对它的网络请求。

解析要求唯一Product、显式整数/数字字符串SKU、主/移动可见PID、名称、Offer URL、主DOM金额/可见金额/OG/JSON-LD金额与明确USD币种一致；版本控件必须唯一选择且响应式重复一致，只返回当前SKU，不混其他PID。无控件仅在其余强证据完整且无多版本声明、未知select/radio控件时可支持；多主Product、组/范围/数量/会员/市场条件报价、未知库存/币种/布局均拒绝。InStock控制样本还校验选中选项金额；真实样本仍仅证明OutOfStock布局。

DTO沿用报价/单规格字段并加`content_policy='facts_only'`，`images=[]`、`description=''`；不造评分/评论或未知税运、数量、市场条件。4.00为主要货币单位。`price_observed_at`为调用观察时间，离线复演不是新HTTP观察；原始获取时点仍见Phase A收据，不等于价格as-of。

15项专项（含参数化冲突样本）通过；用独立`settings.configure(DATABASES={},INSTALLED_APPS=[])`和Django DiscoverRunner仅运行本测试文件，跳过数据库，Django最小配置check通过。覆盖错误PID/SKU/身份/币种/金额、多主商品、假外域、缺字段、选中冲突、无控件证据、未知控件、非法JSON/编码/大小。真实保存HTML在阻断socket的离线运行中通过，仍得到SKU4864、4.00 USD、Pico without Headers、OutOfStock、facts_only。`git diff --check`通过；没有全套、浏览器或新HTTP请求。

最小复演脚本为`.local/validate_adafruit_adapter.py`，证据为原商品目录`ADAPTER_OFFLINE_VALIDATION.json`；准确提交、文件哈希与验证范围写`.local/PHASE_B_DELIVERY_RECEIPT.json`。原HTML与执行收据不入Git。后续由负责人/Medium基于准确SHA验证薄接线、保存与展示，本轮适配交付后停止，不自行扩项。
