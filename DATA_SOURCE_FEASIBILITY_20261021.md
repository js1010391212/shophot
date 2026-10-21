# 数据源真实性、授权与竞品链路可行性

核查：2026-10-22（北京时间）；本轮原始收据为 2026-10-21 UTC。上级为 [#26](https://github.com/js1010391212/shophot/issues/26)，任务为 [#27](https://github.com/js1010391212/shophot/issues/27)，均已完整读取。准确源码基线 `3dd4063e64365b9e710af6a8a159e8a8674a4d34`，树 `d11061921fe33367fc313519e096920f72f02fd6`；在原专属 `local-startup-audit-20261014` 克隆新建 `codex/data-source-feasibility-20261021`，保留旧分支和私有证据。

**本轮交付是五源文档矩阵和一个具体阻断，没有新增真实商品报价，也未证明任何来源可持续商用。** 已有 Shopify 店铺目录/商品页解析值得复用；本轮唯一店铺 Beardbrand 在本会话安全客户端的 DNS 阶段失败。eBay 的 API 许可另有直接影响价格研究用途的限制，不能因为字段可读就接入定价分析。其他平台只有文档证据，API 账户能力、许可和真实覆盖均未验证。

已读 AGENTS、最新根 HANDOFF/TEAM_COORDINATION、DEVELOPMENT_GUIDE、PILOT_READINESS、DATA_SOURCES、DATA_ACQUISITION_PLAN、ALIEXPRESS_DATA_PLAN 和负责人 PRODUCT_DIRECTION_20261021；旧克隆交接头较旧，以最新根契约为准。用户明确授权 ShopHot 团队以后直接与负责人交流、汇报和协调，无须逐次请用户批准；负责人继续负责共享交接与最终验收。本轮只提交本文件，共享源码与交接由负责人维护。

## 证据等级与已有能力

| 证据 | 已有实现及核实位置 | 能说明什么 / 不能说明什么 |
| --- | --- | --- |
| 历史实站，非本轮重采 | DATA_SOURCES：LILYGO、tem-laser 各取得100条目录并标记截取；Beardbrand 三商品各7条公开评价样本 | 证明当时特定店铺/布局可用；不能外推完整目录、全站评价或当前可访问 |
| 当前源码只读 | `market/discovery.py:36`：robots→sitemap，最多3个商品子图/100链接，单响应2 MiB；`market/catalog_prices.py:121`：robots→最多10个商品 HTML | 目录与商品页报价是同域公开链路；有截取标记，lastmod 不是上架时间。目录报价不依赖 cart.js |
| 当前源码只读 | `market/catalog_prices.py:21` 的 `parse_catalog_price`；`market/catalog_content.py` 的内容/规格边界 | 目标商品/ProductGroup、币种、公开价区间、SKU/规格、可得性、评价样本；最多100规格，缺失不等于0。范围报价不等于选中SKU成交价 |
| 当前源码只读 | `market/shopify.py:93,132`：单商品 Ajax；`market/jobs.py:34` 调用 | 明确 variant 或唯一规格；币种取同一客户端 cart 响应。此入口未自行检查 robots，不能沿用目录采集已经检查过的假设 |
| 当前源码只读 | `market/jobs.py:93`、`market/price_history.py:18,60` | 成功报价才追加观测；历史按已记录规格范围/币种比较，不具备完整国家/税运条件的结构化保证。失败不能覆盖成功价格 |
| 历史实站与受控验收分别记录 | `extensions/shophot-capture/README.md`：0.1.1 单刊登318716291619 / USD54.99真实安装点击链路；0.1.2专项与下载包 | 原单刊登证据保留；第二刊登、规格切换与0.1.2真实升级未验收；不等于 Browse API 可用 |
| 离线实现，非API实测 | `market/aliexpress_affiliate.py:278`、离线 preview 命令与原专项 | 请求上下文/成对价格/身份/空结果/有界响应可复用；没有网络客户端、已获批权限或真实API成功响应。零售工具拒绝边界仍有效 |

## 五源准入、成本与用途矩阵

以下链接于本轮查证。文档字段是候选能力，不能当项目实际返回。查证失败或只能读取官方搜索索引的情况单独列明。

| 来源 / 官方证据 | 登录、授权、成本 / 限额 | 允许用途与再分发判断 | 项目状态 |
| --- | --- | --- | --- |
| Shopify：[sitemap](https://help.shopify.com/en/manual/promoting-marketing/seo/find-site-map)、[Ajax总览](https://shopify.dev/docs/api/ajax)、[Product接口](https://shopify.dev/docs/api/ajax/reference/product) | sitemap/公开主题Ajax无需API令牌。Ajax无固定硬限额仍受防滥用限制，Product JSON最多250规格；这不是允许无限采集。无每次调用收费条目不等于零运营成本 | 官方说明针对店铺主题及搜索引擎发现，没有授予跨店数据销售许可；还须逐站robots/条款及店铺许可。本轮商用、导出、图片/描述再分发均未获证明 | 有历史成功，当前安全直连阻断；选其作为优先复核对象，不称已完成持续来源验收 |
| eBay：[Browse](https://developer.ebay.com/api-docs/buy/static/api-browse.html)、[OAuth](https://developer.ebay.com/develop/guides/sell/authorization)、[生产准入](https://developer.ebay.com/api-docs/buy/static/buy-requirements.html)、[开发计划费用](https://partnernetwork.ebay.com/solutions/step-4-optimizing-and-automating) | 注册开发者/应用，OAuth应用令牌，生产用途按Buy准入及业务审批核实，沙盒不证明生产权限。官方写免费会员、新账户免费层5000调用/日，各API实际限额不同；未读账户，不保证本项目配额 | [API许可第9条](https://developer.ebay.com/join/api-license-agreement)明确限制价格建议/建模、竞争用途、内容商业转让及AI训练等；第9.5尤其影响价格分析。需先由负责人核对具体业务与书面许可，不能直接纳入跨平台定价/再销售数据产品 | 本轮只读文档，无API调用；既有浏览器单样本不证明API授权或拟议分析用途获准 |
| AliExpress Affiliate：[productdetail.get](https://jaq-doc.alibaba.com/docs/api.htm?apiId=48595)、[API Use Agreement](https://terms.alicdn.com/legal-agreement/terms/suit_bu1_aliexpress/suit_bu1_aliexpress202201220006_10755.html) | AppKey/Secret签名和获批业务范围；文档“不需要授权”不等于免应用权限。准确配额/费用须以当前获批控制台为准，未证实；API总协议区分免费/收费接口，不能一概称免费 | 联盟推广数据入口；总协议9.3是有限、可撤销、不可转授权许可。没有取得把联盟素材改售为竞品数据库/无限留存/公开导出的许可；2022协议正文可读，不证明用户当前已签相同版本 | 只有离线响应归一化，实际权限未知；不重问旧问题、不读密钥、不回退零售抓取 |
| Mercado Livre 巴西：[Items/Search](https://developers.mercadolivre.com.br/en_us/items-and-searches/items-and-searches)、[商品字段](https://developers.mercadolivre.com.br/pt_br/pt_br/publicacao-de-produtos)、[认证](https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao) | 官方文档示例使用Bearer令牌，公开资源也不能假定匿名可读；自有卖家全量搜索是私有资源。应用、账户验证、授权范围、当前调用额度和收费均未实测，费用未取得明确依据 | [开发者条款](https://developers.mercadolivre.com.br/pt_br/termos-e-condicoes)索引包含7.9竞争/安全/个人数据限制；[应用阻断说明](https://developers.mercadolivre.com.br/devcenter/bloqueio-de-aplicacoes)索引列仅消费读取数据的违规类型。拟议纯竞品读数业务须先核实，不能仅凭“公开”推定获准再分发 | 官方搜索索引可读，Items/认证/条款正文返回403或空；证据强度低于完整正文。无API调用、无匿名可用性/生产准入/全店覆盖证明 |
| Keepa：[API总览](https://keepa.com/api-docs/)、[Product](https://keepa.com/api-docs/product.html)、[令牌计费](https://keepa.com/api-docs/plans-tokens.html) | 账户、已付费API订阅及API key；按月预付、令牌每分钟补充，未用令牌60分钟过期。基础商品每ASIN 1 token，报价等选项加耗；实际月费/税费以当前账户套餐为准，本轮动态价格页未取得金额，不引用第三方49欧报价 | API技术文档证明能集成Amazon数据，未取得本项目允许的展示、缓存、下载、转售/再分发合同。[官网条款入口](https://keepa.com/#!disclaimer)工具只返回一行站点简介；不能把购买API等同购买数据转售权 | 无订阅/密钥读取/请求或购买；非Shopify、AliExpress或巴西全平台数据的替代，市场覆盖须按其支持列表确认 |

## 字段、市场和交易口径

| 来源 | 商品、店铺与SKU | 地区/币种/价格条件 | 时间、覆盖及销量边界 |
| --- | --- | --- | --- |
| Shopify | 域名+规范商品路径，存在时保留平台product/variant ID、商家SKU和属性；sitemap没有完整SKU | JSON-LD按Offer明确币种，Ajax按cart实际presentment币种；语言、域名或country参数不证明目的国生效。运费、税费、优惠资格未知独立保留 | 记录本机取得时间与原lastmod；一次观测无趋势。截断/失败不代表下架，available不代表真实库存数；接口不提供竞品订单/销量/收入 |
| eBay | Browse itemId/legacy ID、item group/variation、商品特征、seller及原URL；刊登ID不能当商家SKU | marketplace header、目的地上下文和返回price.currency/condition/运费分开。文档不能证明任意卖家全量目录或所选规格覆盖 | 保存抓取时间、listing结束/可购买状态；Browse面向在售商品，不是完整成交账本。估计可得性不等于可核实销量，反馈分不等于商品评价数 |
| AliExpress Affiliate | 请求product_id绑定返回product_id；product_detail_url/标题、shop字段以获批版本为准；此接口不提供完整SKU矩阵 | sale/original/app及target三组成对价格币种不混合；country、目标币种、语言与tracking条件保留，返回条件是否实际生效须核实 | 开始/接收时间分别记录。lastest_volume仅“近期销量”，窗口/覆盖不明确；evaluate_rate是百分比而非五分评分。没有全店历史/订单/收入保证 |
| Mercado Livre | item ID、seller_id、title、category、permalink；variations、SKU属性以权限与响应为准；自有卖家私有搜索不等于任意竞品全目录 | 巴西site_id=MLB与返回currency_id分别核对，不能靠语言默认BRL；price/original_price、variation条件、物流条目分开 | date_created/last_updated是平台字段，另存收到时点。官方商品字段索引注明sold_quantity仅owner token可得；公开available_quantity按档位参考值，不能当精确库存。没有竞品真实营收/利润 |
| Keepa | Amazon marketplace domainId+ASIN/parent/variations，报价seller/condition独立；ASIN不是商家SKU | 市场、币种单位、New/Used/BuyBox等价格序列类型分别处理；不能把最低/历史价视作当前选中卖家报价 | [Product Object](https://keepa.com/api-docs/product-object.html)：历史和各自更新时间；Keepa时间按接口单位转换。salesRanks是排名；monthlySold是Amazon展示的近月购买档位下界、按变体且常缺失，不是精确销售笔数或收入，不能将rank跌落直接折算订单 |

## 唯一店铺最小验证：Beardbrand / Beard Comb

选择依据：DATA_SOURCES 中已有成功且可归属的同商品历史；只选 `https://www.beardbrand.com/products/beard-combs`，未扩店、未访问其他四平台实站接口。预期复用目录链路 `discovery.discover` → `catalog_prices.collect_catalog_prices` / `parse_catalog_price`，无需数据库；本轮停在链路前置检查，未调用完整目录采集。

1. 工具读取该店[robots](https://www.beardbrand.com/robots.txt)，标注来源缓存约三周前：通配规则含 `Disallow: /cart` 与 `Disallow: /policies/`。它不是本轮直连的最新robots成功响应。该规则会覆盖 `/cart.js`，因此不能以旧单商品Ajax路径取得币种；商品HTML目录路径不依赖它，不能把cart限制误写为整个店铺禁采。
2. 同轮[条款页](https://www.beardbrand.com/policies/terms-of-service)工具返回不可访问；没有得到条款正文或商业使用授权。此后未用CLI/其他通道补取该条款，也未取被禁止的cart。
3. 安全客户端仅尝试一次robots：`2026-10-21T16:08:13.057386+00:00` 开始，`16:08:13.062909+00:00`停止。复用 `PublicProductTransport` 的公网地址校验、TLS校验、无环境代理、无自动重定向、20/10秒超时和2 MiB上限；在DNS前置以 `CollectionError` 停止，无HTTP状态、响应头/正文或价格可保存。
4. 单次DNS诊断在 `2026-10-21T16:08:44.705418+00:00` 返回 `gaierror errno=8`（nodename nor servname provided, or not known）；没有再发HTTP请求，没有换DNS/代理/身份或绕行访问限制。原robots收据未保留内部中文错误正文，DNS诊断是后续同域原因定位，不冒充已得到原请求的完整栈。

| 本轮字段 | 实际值 |
| --- | --- |
| 来源/目标 | robots前置请求；目标身份只到公开域名与商品handle beard-combs |
| HTTP成功 / 新商品观测 | 无 / 无；不是页面404、验证码或商品下架证据 |
| 商品ID、SKU、币种、国家、价、税运条件 | 全部未知/null；没有继承旧报价或用0占位 |
| 目录数量、完整性、截断、存货、销量 | 未读取/未知；不能写“0件”或“不截断” |
| 数据库与运行服务 | 没有导入Django项目配置或调用ORM，无写入/保存回调，无主库/服务/worker/Chrome操作 |

私有证据目录为本克隆 `.local/data-source-feasibility-20261021/`：`robots_probe.py`、`ROBOTS_PROBE_RECEIPT.json`、`dns_diagnostic.py`、`DNS_DIAGNOSTIC.json`、`VALIDATION_RECEIPT.json`，均0600，目录0700。没有真实商品响应文件可提供，只有失败收据；未提交私有文件或导出密钥。复现脚本已加仅创建新UTC子目录的保护，重新运行不会覆盖本次收据，更新后只做语法校验没有再次联网。入口如下（只在正常获准联网环境由负责人决定何时运行；本轮不重试）：

```sh
cd /Users/qianpengfei/Documents/ChatGPT/shophot/.local/local-startup-audit-20261014
/Users/qianpengfei/Documents/ChatGPT/shophot/.venv/bin/python -B .local/data-source-feasibility-20261021/robots_probe.py
```

**这一阻断满足本轮“成功样本或具体阻断”的交付方式，不满足产品阶段1“合法持续可用数据链路”门槛。** 没有必要让用户再批准常规研究；由负责人先处理本会话正常网络能力、有效robots与条款/许可证据。仅在确需账户持有人操作时，再集中说明所需无密钥能力资料；不重复之前AliExpress权限提问。

## 最小只读适配器契约（建议，尚未新增接口/模型）

复用当前解析器，先返回观测/错误，不直接保存、不跳转、不创建任务。对公开和获批API来源分别标识，禁止把API数据冒充browser来源以绕过账号约束。

| 字段组 | 最小要求 |
| --- | --- |
| 身份 | source_kind、platform、adapter_version、canonical_url、store_host/seller_id、platform_product_id、variant_id、merchant_sku、selected_attributes；未知null，域名+商品+规格归属一致才报价 |
| 价格 | decimal字符串amount或明确low/high、currency、quote_type=current/range/original/app等；不取区间最低价充当SKU价，不静默舍入，不同报价类型分开 |
| 市场范围 | 请求与实际确认的country/locale/currency分开，quantity、condition、shipping/tax/discount条件、确认状态；实际国家未知不从语言推断 |
| 时间/证据 | requested_at、received_at、源字段时间分别保留为带时区ISO；source_url、允许保留的证据摘要/哈希、接口版本/请求条件；不记录Cookie/签名/令牌，不伪造源观测时点 |
| 覆盖 | completed/partial/failed、pages/items_requested/returned、limited、continuation/上限、missing_fields、availability口径；失败下数量不默认为0，未知完整性不能比较下架 |
| 授权 | robots_checked_at/status、terms_url/review_status、usage_scope、redistribution_status、credential_owner_ref（内部引用，不是凭据）；许可未知明确显示，不能默认获准 |
| 错误 | stage/code（dns/robots/terms/auth/429/size/identity/empty/parse）、用户可读原因、可用时retry_after；失败不返回旧价作为新结果，保留旧成功历史的原时间和身份 |
| 交易/估算 | sales保留原字段、单位、期间、覆盖及evidence_type；未知null。rank、评论数、目录数不能变成交订单，模型推断与真实字段分开 |

建议的成功历史比较键包含来源、商品/规格、币种、已确认市场与报价条件；现有quote_scope只覆盖已记录规格/币种，不能声称已实现整个新契约。将来源私有性与API保存约束另交负责人分配，不能直接沿用只给browser的owner约束。

## 风险与后续唯一有界任务

优先风险依次是来源许可/网络前置、不同入口robots保护不一致、规格/地区/报价条件混合、截断和失败被误解释成下架、未知销量被伪装精确数据。现有成功历史与严格金额/归属校验应保留，不用本轮失败否定历史，也不以文档示例补造实测。

建议负责人下一轮只分配 **Shopify 单商品Ajax入口的robots前置保护**：范围限定 `market/shopify.py`、`market/test_shopify.py`，必要共用网络读取函数另先确认所有权；本轮未修改它们。原因是 `collect_shopify` 当前先取cart.js再product.js，未检查两条实际路径的robots规则，与已有目录入口不一致。

验收：使用离线受控响应验证cart或product拒绝时不发送对应请求、robots不可读/非200/超大/异常及跨域重定向均明确停止、允许时同客户端维持币种条件、429不切身份、解析失败不产生成功数据；不能以另一条路径/猜币种绕行被禁止的cart。只跑该模块与必要关联专项，不重复旧PG/浏览器全套。该改动解决访问纪律缺口，仍不宣称本店报价成功；新的真实样本须等待正常网络和许可证据后另定一次有界验证。

## 交付检查与停止线

本轮业务/模型/迁移/UI未变，未执行应用check或迁移/PG/浏览器测试；验证限于真实前置失败收据、源码/链接定位、文件权限、范围及 `git diff --check`。新文档由本分支本地提交冻结，提交SHA在交付评论/最终回执给出；不推送、不创建PR、不改主服务。完成后在#27留一次结果/限制评论，停止本轮，负责人自行取冻结提交验收并更新共享HANDOFF/TEAM/日志。
