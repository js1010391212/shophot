# 联盟详情响应的只读适配

基线：`3919c07b8571fa72579ff82e17846a1ac8445701`。模块仅解析调用方提供的响应字节；不发网络、不签名、不请求零售站点、不读写数据库。没有真实应用凭据，因此只完成适配准备，不代表官方调用成功或速卖通采集已打通。

## 调用契约

`market.aliexpress_affiliate.normalize_affiliate_response(raw: bytes, context: AffiliateRequestContext)` 返回不可变 `AffiliatePreview`，通过 `.as_dict()` 获取只含标准 JSON 类型的预览。上下文为 frozen dataclass：`product_id`（单个正数字字符串）、`country`、`target_currency`、`requested_at`、`received_at`（带时区 datetime）。两个时间按 UTC 瞬间比较，保留原时区，不依赖当前系统时间；接收时间不等于商家价格更新时间。

`country` 可为 None 或两位大写代码；这里只验证格式，官方资料未列出完整可送达国家，不能据此证明覆盖。`target_currency` 可为 None，或文档列出的 USD/GBP/CAD/EUR/UAH/MXN/TRY/RUB/BRL/AUD/INR/JPY/IDR/SEK/KRW；不推断缺省国家或币种。原币报价按项目的三字母币种规则验证。

只接受[官方 48595 文档](https://jaq-doc.alibaba.com/docs/api.htm?apiId=48595)中的 non-simplify JSON 包裹：`aliexpress_affiliate_productdetail_get_response → resp_result → result → products → product[]`。`resp_code` 必须为数字 200 才解析商品；空数组返回 `status=empty`，多条或商品 ID 不符拒绝。`current_record_count` 作为可空原报告数量保留，不推导销量或用它替代数组长度；官方示例该数字与数组展示长度并不一致。未验证的 simplify、单对象、缺失产品容器或 XML 布局会被拒绝。

商品必须有明确 ID 与非空标题。提供商品 URL 时须为 HTTPS 的 aliexpress.com/www.aliexpress.com 同商品路径，不含用户名密码；返回链接由 ID 生成规范地址，移除查询/片段，未提供 URL 时亦明确生成身份链接，不访问它。六类价格分别保留，不互相替代：sale/original/app_sale 及其 target 对应价格，每项价格必须与币种成对，整对缺失返回 null；目标价币种须与已知请求目标币种相同。

价格内部为 Decimal，限项目金额范围 0–9999999999.99。接受可精确表示到分的十进制字符串，`15.900` 可规范为 `15.90`，`15.901` 拒绝；小数文本最多 20 位作为读取上限，不接受指数、区间、浮点 JSON 值或默默舍入。明确返回的零与缺失值区分。结果固定 `sku_id=null`、`specification_status=unknown`、`may_use_as_selected_sku_cost=false`；商品级价格不能当作已选 SKU 的采购成本。

`evaluate_rate` 保留百分比语义，不转换成五星 rating；`lastest_volume` 保留供应方原字段名且 `recent_volume_window=null`，不当累计订单/收入或推算全市场。数字数量要求非负整数且限项目数量范围。折扣与优惠条件仅保留有界文字，不自动应用，优惠代码的资格/门槛也不代表当前用户可获得。未知字段、响应 message、推广/追踪 URL 均不输出。

## 失败与读取上限

`AffiliateResponseError` 的 `code`、`messages`、异常 args 和 `.as_dict()` 只含固定中文提示、安全字段名称及可选的有界数字 `vendor_code`。不输出原 `msg/sub_msg/sub_code` 或解析正文，不按未核实错误码猜测权限、配额或原因。

| code | 含义 |
| --- | --- |
| invalid_context | 请求身份、条件或时间无效 |
| response_too_large / invalid_json / duplicate_key | 超限、非 UTF-8/JSON、HTML、非标准数字或任意层重复键 |
| invalid_structure | 未验证响应布局、状态类型或结构上限不符 |
| vendor_error / service_error | TOP error_response / 联盟非成功状态；仅保留通用分类 |
| ambiguous_product / identity_mismatch | 多条商品或商品/URL 身份不符 |
| invalid_field / incomplete_price / unsupported_price / currency_mismatch | 字段无效、配对缺失、金额不可表示到分或目标币种矛盾 |

输入上限 256 KiB；结构深度 24、节点 10000、键长 128、未知文本 8192 字符；商品标题 240、商品 URL 1000、一般条件文字 240 字符；控制字符及孤立代理字符不能进入已知展示字段。所有边界是本项目读取约束，不是平台接口限额。`.as_dict()` 适合通过 JSON 序列化展示，文本依然应由页面/CLI正常转义，不能标为可信 HTML。

## 验证与后续

`market.test_aliexpress_affiliate` 为 SimpleTestCase，使用明确标注的受控离线响应，验证官方包裹/六价/未知与零/身份与 URL/精确金额/上下文时区与 DST/错误抑制/重复键/大小深度节点限制，数据库 setup 被跳过。不写入观测，不复跑 PG331，不制作静态截图冒充 UI 验收。

后续由负责人接开发用离线预览命令；真实网络调用仍须核当前获批接口、网关/签名与权限。保存层的来源、账号隔离和迁移也未接线，本模块不会伪装 browser 来源。真实 API 成功、商品覆盖、当前 SKU 报价、完整评价/历史/销量口径、用户 UI 均未验收。

## 开发用离线命令

负责人已接入 `preview_aliexpress_affiliate` 管理命令，只读取 `--fixture-path` 指定的有界普通文件；拒绝符号链接、管道、空文件与超限文件，固定输出 `mode=offline_fixture`、`live_api_verified=false`、`database_written=false`。显式提供 `--product-id`、`--country`、`--target-currency`、`--requested-at` 和 `--received-at`，时间不能以导入时刻替代。命令关闭自动系统/迁移检查，不查询数据库、不发网络；错误只输出固定消息。该入口用于开发验收，不要求用户复制 JSON，也不是网站的第二导入流程。

负责人准确集成后服务24项和命令6项合计30项 SimpleTestCase 0.053秒通过，check、迁移一致性与diff通过。真正调用仍等待当前开发者应用权限/凭据，不能拿受控成功响应当平台已打通。
