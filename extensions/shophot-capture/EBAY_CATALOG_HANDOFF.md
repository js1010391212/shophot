# eBay 无规格主报价适配：交接

基线 `26f37f9d0688613e74966c0fa48b71ebd3bf1ea8`，独立克隆 `.local/ebay-catalog-20261008`，分支 `codex/ebay-catalog-link`。范围仅 `extensions/shophot-capture/`，manifest `0.1.1`、观测 `ebay-dom/2`。未修改 Python/共享模型/路由/迁移/worker，未启动服务或写业务库，未推送/合并。负责人控制真实 Chrome、后端集成和发布；本分支没有访问 profile、cookie、凭据、支付或验证页。

## 身份和精确 URL 契约

[eBay 官方 ePID 说明](https://developer.ebay.com/support/knowledge-base/1475)说明其为目录产品身份；[ItemID 说明](https://developer.ebay.com/support/knowledge-base/1854)说明卖家刊登有唯一 ItemID。不能用目录 ePID 代替刊登编号。这两篇说明没有证明任意 `/p?iid=` 必然对应当前卖家，因此仍须公开 DOM 独立核对。

- `/p/[0-9]{1,80}/?` 必须有恰好一个 iid，ASCII数字 **9–15** 位。空值、重复（含同值/编码参数名）、非数字、8位/16位均拒绝，错误 catalog。
- `/itm/(可选标题/)[0-9]{1,80}/?` 保留已有1–80位兼容；如有 iid，必须恰好一个且与路径编号完全一致，否则 identity。
- 保留受支持地区站，规范为原地区 `https://www.<地区域名>/itm/<ItemID>`；去跟踪参数。URL 层保留单个数字1–80位 var，DOM 层本轮拒绝所有 var/可见规格控件，不能从 iid、标题或语言补造 SKU/市场。
- B1仍为15字段，product_id=ItemID、sku_id=null、market_country=null，价格为 decimal string、quote_type=current。

## 实际观察驱动的读取边界

| 布局 | 主区域 | 标题 | 刊登归属 | 主报价 |
| --- | --- | --- | --- | --- |
| 目录 | 唯一可见 `.x-prp-main-container_col-right` | `.x-item-title h1` | 唯一可见 `.x-see-details-action a[href]` 必须与 iid 同站同刊登 | `.x-price-primary` 的直接 `:scope > .ux-textspans` |
| 详情 | 唯一可见 `#mainContent.x-evo-atf-right-river` | `.x-item-title h1` 内唯一可见 `.ux-textspans--BOLD` | canonical、og各一个，唯一 ItemPage.url 与唯一 Product/Offer.url 同站同刊登；Product.name 如存在须字符串且与主标题一致 | `.x-price-primary__price > .ux-textspans` |

两种主区域还要求唯一可见、非禁用 `a#binBtn_btn_1`，公开 href 为 HTTPS `pay.ebay.com/rxo`、无凭据/自定义端口，单个 item 匹配当前刊登且单个 action=create。缺失/禁用/错误或重复参数返回 unavailable。只读 DOM，不请求支付地址、不点击购买。

只支持观察过的显式 US $/USD 主报价；其他币种、混合换算、区间、划线/隐藏/多报价均拒绝。详情页须明确 Offer.availability=/InStock。JSON-LD 同币种 USD 价格作为参考交叉校验，金额冲突拒绝；不同币种 JPY 只用于所属 Offer 身份，不拿换算金额校验 USD。目录 JSON-LD 有多个其他刊登，不读取其报价/身份。推荐区、原价、转换价没有兜底路径。详情独立展示的 - 后缀不入标题，也不全局删除真实标题标点。

挑战/登录页具体阻断；缺失/矛盾主区域、归属或标题具体失败；失败不打开本地页、不写原始 capture。成功只进入待预览状态，用户确认后才保存；既有 sender、CSRF、session TTL、一次提交和预览/保存边界不变。

## 实站证据与受控验证

负责人提供只读公开源：主工作空间 `.local/platform-live-20261008/ebay-catalog-public.json`（14:06:07Z）、`ebay-listing-public.json`（14:08:12Z），另核对详情 BOLD 标题与一口价按钮。原始 HTML/跟踪属性不入 Git。

负责人先于14:20:46Z执行前一版读取源，在追加一口价校验后又于 **2026-10-08T14:28:42Z** 在原有真实 Chrome 对同一刊登318716291619的目录 `https://www.ebay.com/p/813169729?iid=318716291619` 和详情 `https://www.ebay.com/itm/318716291619` 执行最终实际 readPublicPage 源，两次均返回 USD主报价54.99、规范同一/itm、SKU未知。最终两份公开读数及原观察时间冻结在 `evidence/ebay-readings.json`；详情可见“或最佳报价”，目录条件未知。仅执行读取函数，没有网络或页面写入。

第二个候选377489913401验证阻断后已停止，未取得其正常 DOM。以上仅为**一个刊登、两种布局**，不代表两件商品、规格切换或已安装扩展完整链路通过。不扩大 AliExpress、其他eBay币种/布局、竞拍或无人值守采集。

Node专项 **131项全部通过**，其中新增 eBay 专项74项：URL边界、ePID/iid分离、各归属证据、无规格、可购买状态、币种/原价/换算隔离、标题展示后缀/非字符串、具体失败和本地tab绑定。DOM与Chrome API均为受控 doubles，真实函数执行另记 `EVIDENCE.md`。语法和 git diff --check 结果与精确提交在交付消息给出；不重复 Django 全套。

## 负责人续接范围

Python `market/ebay.py`、目标注册和B1归属由负责人统一集成，边界采用上述 /p iid9–15与/itm路径1–80/冲突iid规则；本分支不另建目录模型、迁移或接收入口。既有自动HTTP与旧文件导入范围不随之扩大。

负责人安装0.1.1并完成实际扩展点击 → 本地预览 → 确认 → 当前账号报告、报价/来源/时间核对及截图。DOM成功不等于已保存。主 `HANDOFF.md`/`DEVELOPMENT_LOG.md`、最终发布由负责人维护。本分支交付提交后停止，不推送、合并或部署。

## 负责人安装验收补记

2026-10-08 22:46：用户重新加载0.1.1后在原目录页实际点击；负责人接入自动生成的报价预览，核对54.99 USD、ebay-dom/2和14:44:16.311Z原观察时间并确认保存，账号报告显示最新22:44与共2条记录。安装全链路单刊登通过，证据见EVIDENCE末节。上文高级独立分支范围与测试性质保持；第二商品/规格/其他币种仍未验收。
