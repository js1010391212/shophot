# B2 实际页面证据与交付记录

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
