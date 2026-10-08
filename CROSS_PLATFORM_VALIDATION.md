# 跨平台真实样本验收（2026-10-08，北京时间）

结论：非 Shopify 平台尚未通过自动分析验收。必须区分“浏览器看到商品”“后台取得数据”“ShopHot 保存并分析”三步，不能把搜索摘要或手动浏览冒充自动采集。用户授权真实跨平台验收；没有登录、提交订单、解验证码、关闭安全校验、轮换代理或伪造数据。

## 样本与结果

| 平台 / 样本 | 真实链接 | 本地结果 | ShopHot 自动分析 |
| --- | --- | --- | --- |
| OTTO / FDS GmbH（COSTWAY） | https://www.otto.de/p/costway-hundeschermaschine-hundepflegetisch-trimmtisch-arbeitstisch-klappbar-S08F10JE/ | 浏览器显示真实商品、165.99 EUR；卖家名称由 OTTO 官方页公开说明确认。后台 robots 200，但商品请求 HTTP400、无 JSON-LD | 未接入；明确提示，不入队 |
| OTTO / Guru-Shop | https://www.otto.de/p/guru-shop-kerzenlaterne-orientalische-metall-glas-laterne-in-S0R0I0F0/ | 浏览器显示黄色规格 10.90 EUR、评分5.0/1条、卖家 Guru-Shop。后台 HTTP400、无 JSON-LD | 未接入；明确提示，不入队 |
| Ozon / Tefal 店铺 | https://www.ozon.ru/seller/tefal-ofitsialnyy-magazin/ | 浏览器显示“似乎没有连接”平台错误页；robots307，探针未自动跟随，规则无法确认，因此未请求目录 | 未接入；明确提示，不入队 |
| Ozon / Xiaomi 店铺 | https://www.ozon.ru/seller/xiaomi-ofitsialnyy-magazin/products/ | 同样显示平台连接错误。共用前项 robots 结果，未继续 HTTP 请求目录 | 未接入；明确提示，不入队 |
| SHEIN / All boutiques 页面 | https://us.shein.com/store/home?contentIds=&pageType=topBanner&store_code=1061637975 | 该地址为搜索找到的 store/home 测试入口，未取得商品目录，不能确认有效卖家；robots200，HTTP302到/risk/challenge，未跟随。浏览器显示“I am human”验证 | 未接入；明确提示，不入队 |
| SHEIN / ALET TREND 店铺 | https://m.shein.com.mx/store/home?store_code=9658247474 | 卖家链接来自 SHEIN 商品公开描述。robots200，HTTP302到/risk/challenge。浏览器显示西语人工验证，未完成验证；店内商品未核对 | 未接入；明确提示，不入队 |
| AliExpress / UMIDIGI 店铺 | https://www.aliexpress.com/store/4089001 | robots200，HTTP200仅2071字节验证内容，无JSON-LD。店铺地址为公开历史链接，未取得当前目录，不能确认在售状态 | 当前仅支持 /item/商品ID.html，不支持店铺目录；明确拒绝，无数据入库 |

OTTO 使用两家真实卖家的商品作为探测入口，尚未完成全店目录验证。Ozon 搜索索引能提供店铺摘要，但它不代表当前本地请求可获取数据。本轮没有复测速卖通单品，因为本轮目标为店铺入口且未拿到当前商品目录；不要把店铺验证结果扩大为全部商品链接的结论。

## 发现并修复的问题

旧首页自动识别把所有非 aliexpress.com 地址当成 Shopify，所以其他平台报错“请填写 /products/ 商品链接”，误导用户。新增 market/platforms.py，在 Auto 及手动指定 Shopify/AliExpress 时均检查真实域名边界，识别 SHEIN（含墨西哥域名）、OTTO、Ozon 并明确尚未接入；AliExpress美国站也给出明确边界。保留 Shopify 自定义域名兼容与正常速卖通商品归一化。当前是识别/反馈修复，不是新增数据采集能力。

真实浏览器从首页提交 Ozon、SHEIN、OTTO 均显示对应提示，保留原网址、不创建目录/商品采集任务。错误页面 HTTP400 正常表示输入暂不可分析。桌面/390×844手机无整页溢出。

## 证据与回归

- scripts/validate_platform_samples.py：只读HTTP验收探针，调用现有安全公网传输，不存价格，尊重 robots；规则无法确认不采集，403/429停止同域重复请求，不跟随验证跳转。不使用浏览器会话/cookies或请求私有接口。
- .local/platform-validation/http-results.json：7条实际HTTP/表单记录，重定向只保存路径，不保留风险参数。
- /tmp/shophot-otto-guru-validation.txt：浏览器公开商品DOM证据。
- /tmp/shophot-{otto,ozon,shein}-validation.png：外站实际截图；/tmp/shophot-platform-feedback{,-mobile}.png：ShopHot反馈截图，均备份至.local/platform-validation。
- 最终 PostgreSQL 全套156项通过，新增3项跨平台域名/流程测试；check、迁移一致性、diff通过。新测试包括真实域名、错误相似域名、手动指定平台也不误入队、原有平台兼容和美国站提示。

## 后续优先级

优先验证 OTTO 单品适配：公开浏览器字段已有，但需解释本地HTTP400与浏览器差异，固定商品/卖家/规格身份，不能把推荐商品、划线价或分期月付款当成价格。之后再做卖家商品发现。SHEIN/Ozon先保留未接入提示，调查许可数据源或用户主动保存可见公开数据的工作流；不以绕过验证作为验收成功条件。


## 续开发：OTTO 文件导入（2026-10-08）

进一步诊断安全 HTTP400 响应包含 window.KPSDK 和 ips.js 验证脚本；不是普通业务商品页，停止自动获取适配，没有执行验证或伪装请求。

新增离线 HTML 解析与预览确认模块：OTTO `/p/` URL 独立规范化，保留 variationId；仅接受唯一匹配目标商品、唯一明确 Offer 的价格和币种。规格不能确认、仅 AggregateOffer、推荐商品、验证文件全部拒绝。评分/评价数仅取明确字段，未知保持空；不包含评价正文分析。

实际本地浏览器从首页输入此前验证过的 Guru-Shop 商品链接，跳转 `/products/3/otto/import/`，未创建自动任务或报价。桌面、390px 手机布局通过，页面无横向溢出，截图 `.local/platform-validation/otto-import.png` / `otto-import-mobile.png`。测试夹具预览与确认仅在隔离测试数据库运行，不混入正式数据。

完整 167 项回归通过，包含 11 项 OTTO 新测试。实际正常浏览器保存的 HTML 尚未取得，故**文件解析的真实 OTTO 页面兼容性未验收，自动采集仍未通过**。之前 HTTP 验证 JSON 中 OTTO 表单拒绝结果是旧版；新版首页仅创建导入入口，自动队列入口依旧拒绝。


## 统一文件导入与速卖通适配（2026-10-08）

新增 `/import/page/` URL选择及 `/products/<pk>/page/import/` 上传预览确认，复用严格 JSON-LD 解析。速卖通规范化仅支持 aliexpress.com 商品，保留 numeric sku_id、清除营销参数；无规格链接遇到报价的明确规格URL时拒绝混入通用历史。带sku_id的首页分析不排队，旧误排队任务保护失败，不请求通用报价。OTTO旧URL、表单与解析入口兼容。

实际浏览器从首页进入统一入口，使用历史验证过但当前在售状态未知的速卖通链接 `https://www.aliexpress.com/item/32922106384.html` 建立 Product#4。上传明确标注“受控测试示例（不是实站数据，请勿保存）”的本地JSON-LD夹具，预览报价/规格/未知评分评价数/时间/手动来源及校验码；没有确认保存。另上传x5secdata验证夹具，提示未保存价格。数据库只读核对Product#4为0快照、0任务。

桌面和390px手机预览无横向溢出，截图 `.local/platform-validation/page-import-preview{,-mobile}.png` / `page-import-failure.png` / `page-import-entry.png`。完整177项回归通过；正常保存的真实速卖通和OTTO文件未取得，实站HTML兼容性尚未通过。文件功能不等于后台自动采集、定时监测或完整评价正文分析；SHEIN/Ozon文件仍未接入。


## 商品评论样本主功能（2026-10-08）

统一文件导入现在读取已匹配商品节点里的 JSON-LD review（最多10条），过滤店铺评价、明确其他商品、外域同ID、无正文与重复，评分未知保持空。评论标题/正文以纯文本保存，未保存作者身份；评论日期与查看时间分开。评论与Snapshot一起确认保存，ProductReviewBatch一对一绑定，不以评价总数补造正文，重复导入/同时间冲突保护历史。

实际本地浏览器用已有真实Beardbrand目录URL建立Product#5 Beard Comb，评论报告 `/products/5/reviews/` 只读复用目录#6商品0的7条有效公开评论，来源与UTC采集时间明确，不混入手动导入历史。7条均5星，仍匹配到1条尺寸偏小和效果不足线索（原文第4条），证据跳转到#review-sample-3成功；这只是样本线索，非整体质量结论。桌面/390px手机无横向溢出。

Product#4速卖通无正文时不生成词频和图表。另上传明确标注“受控评论测试（不是实站数据，请勿保存）”的夹具：2条正确商品评论可预览，其他商品样本被排除，没有点击确认保存。真实OTTO/速卖通文件兼容性仍待验收，不能当作自动采集成功。完整188项通过；最终专项及进程见开发日志。

截图：`.local/platform-validation/product-reviews.png` / `product-reviews-mobile.png` / `product-reviews-empty.png` / `imported-review-preview.png`。
