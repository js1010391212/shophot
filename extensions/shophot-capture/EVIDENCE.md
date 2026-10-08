# 实际页面证据与交付记录

以下B2是历史首版证据；本轮eBay 0.1.1新增记录在文末，范围与状态分别说明。

基线 `6b922eba220a6b08e24e12859510023cb8f944c8`，分支 `feat/browser-capture-extension`。所有修改仅在 `extensions/shophot-capture/`。未启动服务/worker、未访问业务数据库、未修改后端、未推送或合并。

2026-10-08 在 Codex 内置浏览器正常可见页面，通过 `dom-reader.mjs` 的实际 `readPublicPage` 函数读取；没有 HTTP 重试、私有接口或凭据访问。结构化输出与原始记录时间见 `evidence/otto-readings.json`。记录时间来自本机写入时钟，不对外站时间作真实性保证。

| 商品/明确规格 | 准确采集目标 | 可见当前报价 | 规格证据 |
| --- | --- | --- | --- |
| Guru-Shop 灯笼，gelb 黄色 | https://www.otto.de/p/guru-shop-laterne-orientalische-metall-glas-laterne-in-S0R0I0F0/?variationId=S0R0I0F04SO6 | 10.90 EUR | 所选 radio gelb、selected tile、动态 price/ordering 区及 URL variationId 一致 |
| 同一灯笼，grün 绿色 | https://www.otto.de/p/guru-shop-laterne-orientalische-metall-glas-laterne-in-S0R0I0F0/?variationId=S0R0I0F0C3SE | 10.90 EUR | 正常 radio 选择后等待更新，selected tile、price/ordering 区及 URL variationId 一致 |
| COSTWAY 护理桌 | https://www.otto.de/p/costway-hundeschermaschine-hundepflegetisch-trimmtisch-arbeitstisch-klappbar-S08F10JE/?variationId=S08F10JEM769 | 165.99 EUR | 当前 price/ordering 区明确 variationId；没有可见规格选项，不补造颜色/尺寸条件 |

三次读取条件均可见 `inkl. MwSt. zzgl. Versandkosten`（含增值税、另计运费）。当前收货国家未知。COSTWAY 另有 UVP 224.99 EUR 划线价、15.16 EUR 月供；灯笼另有 1.00 EUR 月供与推荐区其他价格，均未采入。

发现并处理：灯笼动态规格切换后，JSON-LD 和外层 frame 的 SKU 仍是首次加载的黄色；因此不能把这两个标记当作当前所选规格依据。动态价区、购买区、规格控件和 URL 已随绿色切换；部分更新中的临时矛盾返回 `variant`，用户需等页面更新后重新点击。

截图位于本独立克隆的 `extensions/shophot-capture/.local/`（Git 排除）：

- `otto-yellow.jpg`：真实黄色、10.90 EUR。
- `otto-green.jpg`：真实绿色、10.90 EUR。
- `otto-costway.jpg`：真实当前价165.99 EUR与划线/分期价区别。
- `ebay-challenge.jpg`：eBay 浏览器验证页，未执行验证或继续重试。

eBay 一次实站访问 `https://www.ebay.com/itm/297641468411`，跳转验证 `/splashui/challenge`，无正常商品报价，未验收。速卖通先前历史链接进入验证路径被安全策略阻断，本轮没有换通道重试；缺少正常登录的商品页，未验收。候选适配器及 URL 规则通过受控测试不等于实站通过。

本轮 Node 专项 57 项通过，真实3份 OTTO DOM 输出与 B1 的15字段/目标/金额/规格/时间契约单独检查。Chrome API 和本地桥接测试为隔离 doubles；未安装 Chrome 扩展，未实际确认写入，未完成浏览器 → 预览 → 保存 → 报告。负责人负责安装联调、后端最终回归和桌面/390px本地 UI 验收；不能用本记录宣称完整平台流程已经上线。

无迁移和 Django 共享逻辑变化，不重复 H1 或全套 Django 测试。最终提交与检查结果由交付消息提供。后续限定为负责人集成与安装验收，不在本分支展开评论/店铺/无人值守采集。

## eBay 0.1.1：同一刊登两种真实布局

本轮基线 `26f37f9d0688613e74966c0fa48b71ebd3bf1ea8`，独立克隆 `.local/ebay-catalog-20261008`，分支 `codex/ebay-catalog-link`。Chrome和截图由负责人控制；本分支依据负责人提供的公开 DOM 开发，没有操作真实站点、支付、业务库或服务。

负责人在原有真实 Chrome 对两种页面执行 readPublicPage 静态源函数（纯只读 DOM，无网络/页面写入），前版14:20:46Z成功；增加一口价状态校验后的最终源于 **2026-10-08T14:28:42Z** 两次重新执行成功。最终真实时钟与公开输出见 `evidence/ebay-readings.json`，不包含 cookie、账号、原始 HTML 或跟踪属性，不把旧读数重标为新采集。

| 布局 | 真实页面 | 输出 |
| --- | --- | --- |
| 目录页 | `https://www.ebay.com/p/813169729?iid=318716291619` | productId=318716291619、sku=null、US $54.99、USD、referencePrice=null、conditions=[]、规范/itm/318716291619 |
| 详情页 | `https://www.ebay.com/itm/318716291619` | 相同刊登/规范链接/金额/币种；标题为唯一 BOLD 主标题；条件为 `またはベストオファー`（或最佳报价） |

这是**同一刊登的目录和详情布局**，不代表两件商品或规格功能通过。目录ePID813169729未用作刊登编号。详情 Product 无自身url，但唯一 ItemPage/Offer.url 绑定此刊登；JSON-LD的8693.0 JPY换算未替代美元主价。可见原价US $68.99、其他推荐报价不采入；目录另19个JPY Offers不用于当前报价/归属。

负责人在两种布局均只读观察到主区域 `a#binBtn_btn_1`：HTTPS pay.ebay.com/rxo，单个item=318716291619、action=create，可见且未禁用，文案今すぐ買う。最终源要求该按钮唯一、可用并匹配刊登，缺少、禁用、错编号/域名或重复参数返回unavailable。只检查DOM href，不点击、不访问支付。

第二个候选377489913401遇到/splashui/challenge，负责人已停止；未获取正常报价。AliExpress缺少正常DOM，未扩大适配或换通道重试。此时高级队交付仅含DOM读数，安装扩展全链路尚未验收；下节为负责人随后完成的独立安装验收，不以高级JSON接收代替。

本轮Node专项131项通过，其中新增eBay专项74项均为受控DOM/Chrome API doubles；引用真实公开读数对照输出，不能替代安装测试。覆盖iid9–15/itm1–80、归属、一口价状态、非字符串名称具体失败、无规格边界、原价/换算、标题后缀、错误不打开接收页及本地标签绑定。未重跑Django全套或新增迁移，Python由负责人集成。精确契约见 `EBAY_CATALOG_HANDOFF.md`，语法/差异检查和提交见交付消息。

## 2026-10-08 22:46：负责人验收已安装扩展

用户重新加载已安装ShopHot 0.1.1，在原目录页 `https://www.ebay.com/p/813169729?iid=318716291619` 点击“采集到ShopHot”，并在本聊天明确反馈已进入报价预览。负责人接入Chrome新建的本地预览标签页，实际可见54.99 USD、规范 `/itm/318716291619`、原始观测 `2026-10-08T14:44:16.311000+00:00`、来源“浏览器主动观测 · ebay-dom/2”；收货国家、规格及条件均保持未知。负责人通过页面“确认并保存报价”保存，随后报告 `/products/7/browser/` 显示成功提示、最新22:44（北京时间）和共2条记录。

这验证了**已安装扩展用户点击 → 自动送达预览 → 核对确认 → 当前账号报告**。前条22:28记录来自真实DOM经高级JSON入口，与此次实际扩展链路明确区分。截图 `.local/platform-live-20261008/ebay-extension-preview.png`、`ebay-extension-report.png` 和简要验收 `native-extension-verification.json` 在本地保留，截图/原始HTML/账号不入Git。此次仍是一件商品，无第二件或规格切换验收；AliExpress工具站点策略拒绝操作，未通过实站验证。
