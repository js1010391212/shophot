# ShopHot 当前商品采集扩展

当前源包版本 **0.1.2**；弹窗从 `chrome.runtime.getManifest()` 显示实际安装版本，旧目录未重新加载时不会自动升级。eBay观测标记为 ebay-dom/2。

首版 Chrome Manifest V3 扩展，要求 **Chrome 102 或以上**。用户在正常商品页点击采集后，扩展读取当前顶层页面的有限公开 DOM，打开本地 ShopHot 报价预览；**用户核对并点击确认后才保存**。不读取或导出 cookie、账号存储、登录凭据，不请求私有接口，不自动打开外站，不绕过登录或访问验证。

## 安装和使用

1. 启动已集成浏览器接收模块的 ShopHot，并在 **http://127.0.0.1:8000** 正常登录。扩展固定使用此地址；`localhost`、其他端口或 HTTPS 本地地址暂不接收。
2. 将扩展 ZIP 解压到固定目录，或者使用本目录。根目录必须直接包含 `manifest.json`。
3. 在 Chrome 打开 `chrome://extensions/`，开启开发者模式，点击“加载已解压的扩展程序”，选择上述目录。可在工具栏固定“ShopHot 当前商品采集”。
4. 打开正常商品页，选好规格，等待页面报价、规格标记和 URL 更新完成。点击扩展，再点击“采集到 ShopHot”。
5. 扩展打开本地接收页并提交预览。核对来源链接、规格编号、当前价、币种、条件和时间；点击本地页面的“确认并保存报价”，随后查看当前账号的浏览器观测报告。

出现验证页时，先在平台正常完成登录或验证，再进入商品页采集；扩展不处理验证。若本地登录过期，先登录 ShopHot，然后回商品页重新采集。页面或扩展更新后，需要刷新商品页再采集。取消预览不会保存观测。

## 升级与本地接收提示

0.1.2 仅改进弹窗版本、状态及上手说明；权限、地址匹配、采集器与接收契约保持原范围。将新 ZIP 解压覆盖原来的固定安装目录，在 `chrome://extensions/` 对该扩展点击“重新加载”，再刷新外站商品页；打开弹窗核对实际安装版本为 0.1.2。避免同时启用多份扩展。若首次安装使用新目录，应在 Chrome 中选择该目录；弹窗不会自动修改安装目录、升级扩展或刷新商品页。

“打开 ShopHot / 登录”固定打开 `http://127.0.0.1:8000/`，“安装说明 / 接收页”固定打开 `http://127.0.0.1:8000/browser/capture/`。这两个入口只打开页面，不采集、不确认保存，也不能自动启动本地服务。地址打不开时先启动 ShopHot；登录过期时先本地登录，再从商品页重新采集。弹窗状态来自既有扩展记录，不是实时服务探活，旧“预览已显示”也不代表报价已保存。等待响应时先检查原接收页，已有预览应先处理，避免反复采集。

0.1.2 的弹窗专项是受控 runtime/DOM 组件回归，不代表该版本在外站已完成安装点击验收。此前 0.1.1 的真实 eBay 单刊登证据仍保持以下边界。

## 平台状态和限制

| 平台 | 本轮证据 | 当前边界 |
| --- | --- | --- |
| OTTO | 真实读取两件商品：[Guru-Shop 灯笼](https://www.otto.de/p/guru-shop-laterne-orientalische-metall-glas-laterne-in-S0R0I0F0/) 10.90 EUR，黄色/绿色各有明确规格；[COSTWAY 护理桌](https://www.otto.de/p/costway-hundeschermaschine-hundepflegetisch-trimmtisch-arbeitstisch-klappbar-S08F10JE/) 165.99 EUR。源码 `EVIDENCE.md` 记录完整证据 | 当前价区、商品编号、动态购买区、所选规格与 URL 交叉校验。其他布局、未处理的规格控件、矛盾或含糊报价严格拒绝。 |
| AliExpress | 用户已正常登录；工具站点策略拒绝操作，尚无正常商品DOM验收 | 仅候选语义 DOM 适配，**未实站验收**。必须单个 Product/Offer 明确归属，并有可见准确价格；带 SKU 或规格控件因映射未核验而拒绝。 |
| eBay | 真实Chrome同一刊登318716291619目录/详情均读取US $54.99；0.1.1用户实际点击→预览→确认→报告通过，见 `EVIDENCE.md` | 仅已观察布局、无var/可见规格控件、明确USD主报价；独立刊登归属与一口价状态校验。第二个刊登验证阻断。仅一个刊登通过安装扩展完整链路，规格切换未验收。 |

OTTO 切换规格后，外层容器及 JSON-LD 可能仍保留旧规格；本适配器读取动态当前价区、购买区与规格控件，不采用旧 JSON-LD 报价。推荐区、划线价、分期金额和含糊区间不得充当当前报价。收货国家保持 `null`，不从页面语言推断；空条件数组表示未知。一次浏览器观测不能用于推断销量或整体市场。

eBay目录链接要求 `/p/<数字目录ID>?iid=<9–15位ASCII数字刊登编号>`，iid恰好一个；规范目标使用iid而非目录ePID，保留地区站。URL层保留合法var，但本轮DOM采集拒绝任何var或可见规格控件。目录主区域当前详情链接必须与iid一致；详情须canonical、og、唯一ItemPage与当前Product/Offer归属一致。两种布局要求对应刊登的一口价按钮可用，只读公开href及禁用状态，不点击或访问支付。主价取已核验 `.x-price-primary` 内独立USD节点，不采划线原价、推荐或日元换算；详情取唯一BOLD主标题，排除独立展示后缀。同币种结构化报价冲突拒绝。缺少/重复/无效iid或itm冲突iid拒绝。精确契约和分工见 `EBAY_CATALOG_HANDOFF.md`。

**0.1.1安装后的eBay单刊登完整链路已通过**：用户在原目录页实际点击采集，负责人核对22:44的54.99 USD预览并确认保存，当前账号报告保留该条与之前记录。真实函数读取、Node doubles、此前高级JSON接收与此次实际安装链路分别记录，不能互相代替。未验收第二件商品或规格切换；原高级独立分支未写业务库或操作真实浏览器，安装验收由负责人完成。Chrome手机版不支持此桌面扩展，手机端主要验收本地预览/报告。

## 接收契约和数据生命周期

- 仅用户点击时注入 `activeTab` 顶层脚本；无外站永久 host 权限。
- 本地内容脚本只匹配 `127.0.0.1:8000/browser/capture/*` 和同源登录页。数据通过扩展内部 runtime 消息交给此次创建的本地标签页；校验 sender 扩展 ID、顶层 frame、当前标签页、精确 origin/path。
- 不提供 `window.postMessage` 或 `externally_connectable` 接口，不把 JSON 或令牌放入 URL。`storage.session` 设为 `TRUSTED_CONTEXTS`，10 分钟过期并用闹钟清理；最多三个待处理页面。标签页关闭、未知跳转、登录阻断或接收失败时清除其数据。数据交给表单后立即删除原始 session payload。
- 初始表单必须为 `#browser-capture-form[data-browser-capture-bridge="ready"]`，普通同源 POST，含唯一的 `target_url`、`capture` 与有效 CSRF。内容脚本保留 CSRF，只执行一次 `requestSubmit()`。预览页无 ready 标记，绝不再次发送。
- JSON 严格保持 B1 的 15 个字段。价格是十进制字符串、报价类型仅 `current`；跟踪参数清理，商品规格参数保留。后端仍需独立校验登录、CSRF、来源身份、时间与签名。
- “等待接收”“已发送”“预览已显示”均不等于保存成功。保存成功由本地确认后的报告页面显示。

权限 `activeTab`/`scripting` 用于用户点击采集；`storage` 用于内存 session；`alarms` 清理过期记录。Chrome 102 下限来自 [`storage.session` 与 `setAccessLevel`](https://developer.chrome.com/docs/extensions/reference/api/storage)。[activeTab 官方说明](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)。扩展无网络采集服务，也不需要 worker 参与点击采集。

ZIP只包含运行资源及本说明；开发测试和原始证据在[源仓库](https://github.com/js1010391212/shophot/tree/main/extensions/shophot-capture)，不混入安装包。

## 专项验证（源仓库开发者）

在仓库根目录执行：

```sh
node --test extensions/shophot-capture/tests/*.test.mjs
```

0.1.1 基线Node专项 **131项通过**（不是0.1.2本轮全套重跑结论），包含eBay iid9–15、独立刊登/可购买状态、标题后缀和币种换算边界。新增弹窗专项可单独执行 `node --test extensions/shophot-capture/tests/popup.test.mjs`，核对实际版本、采集状态/异常、等待旧响应不覆盖新点击、帮助入口不发送采集或保存消息。基线测试覆盖来源 URL/规格冲突、区间/推荐/分期/划线价、可见币种、验证页、错商品、顶层 sender、标签页隔离、同源 POST/CSRF、重复/刷新、10 分钟 TTL、离线/登录状态及 session 恢复。DOM doubles 与真实 DOM 证据分别记录。

可用仓库 Python 环境验证冻结的真实 OTTO 读数与现有 B1 契约：

```sh
.venv/bin/python extensions/shophot-capture/tests/backend_contract.py
```

这项检查只配置最小 Django settings，不连接数据库、不创建或保存观测、不启动服务。使用原始观测时间作为校验时钟，历史证据不重标为新采集。eBay 后端由负责人独立集成，本测试仅验证本轮实际 OTTO 输出。
