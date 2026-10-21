# 第二轮 Shopify 来源分层验证与 robots 安全修复

2026-10-22，北京时间；下列取证时点均为UTC。本轮执行负责人第二轮优先2：分层诊断、一个既有Shopify来源的最小验证，以及发现真实robots误放行后负责人追加授权的统一安全修复。管理员审查已经结束，不重放历史建号请求，不操作既有账号、业务数据库、服务或全局网络设置。

准确基线 `db71186f848bb69f8cee2f24eb484d28de9e4e38`，独立克隆 `.local/round2-source-20261022`，分支 `codex/round2-source-validation-20261022`；起点受跟踪文件干净，原克隆/分支/证据保留。已读AGENTS、HANDOFF、DEVELOPMENT_GUIDE、TEAM_COORDINATION；旧停止头由本轮负责人明确恢复/派发覆盖。最终范围为新统一保护及专项、三个既有采集入口与对应专项、本文档，共9文件；未扩展五源矩阵。

## 结果

**已将本轮默认执行环境中的DNS失败与正常联网执行能力分离，取得Beardbrand最新robots真实200响应；没有新的商品报价。** 旧失败不能再当成本机DNS配置损坏、店铺宕机或API权限不足的证据。

默认执行器的公网TCP被拒、控制和目标域名同时无法解析；经工具正式权限审查许可，在正常执行环境运行同一只读探针后，控制站与目标robots均成功。没有修改DNS、代理、TLS或网络transport，也没有在平台拒绝后换工具取同一资源。

本轮停止点是**条款核查路径受robots禁止，且现有robots解析器有误放行**。商品HTML路径本身未被这些规则禁止；不能把停止点说成网站禁止所有商品、robots返回403或商品不存在。尚未完成允许用途核验，因此没有请求商品、cart、sitemap或条款正文，不将旧Fox Hunt USD50重标为今天样本。

## 分层证据

| 层次 | 默认执行器（20:11:57.823867–20:11:58.015012） | 正式权限审查许可的执行环境（20:12:31.579600–20:12:33.788488） | 判断边界 |
| --- | --- | --- | --- |
| 基本网络 | TCP `1.1.1.1:443` 返回errno1/EPERM | 同一TCP探针errno0；随后控制HTTPS 200 | TCP只做连接，无DNS请求/HTTP/TLS载荷；单个连接不证明所有外网健康 |
| 系统配置可见性 | scutil DNS返回1/No DNS configuration available；网络信息不可完整读取 | DNS返回0，可见10个resolver块/6个nameserver条目；网络信息读取返回0 | 默认执行器不可见不能推定主机没有DNS配置；只记录脱敏计数，不输出服务器/接口私有地址 |
| 系统DNS | example.com和www.beardbrand.com均gaierror/errno8 | 两域均解析成功，均落入198.18.0.0/15 Fake-IP范围 | 同环境控制与目标一致受影响，非单一目标证据；未设置新DNS、未人工换解析服务 |
| 代理环境 | 大小写HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY均不存在；系统信息受限 | 同八个环境变量均不存在；系统HTTP/HTTPS代理开关开启，自动配置/发现及SOCKS关闭 | 只读“是否存在/启用”，未保存端点/凭据；应用trust_env=False。不能由此否认系统路由、透明代理等网络层影响 |
| 应用安全访问 | 原PublicProductTransport在控制/robots前置均CollectionError，无HTTP状态/正文 | 同一transport、trust_env=False、TLS验证、IP固定与同域目标；控制200、robots200 | 复用既有Fake-IP兼容分支：校验固定可信DoH返回公网IP再固定连接，非本轮新增解析器/代理或关闭地址检查 |
| 目标服务 | 没有取得目标HTTP响应 | 仅robots端点真实200 | 不证明商品字段、整个店铺连续性或所有接口可用 |
| 业务API权限 | 未调用任何鉴权API | 未调用任何鉴权API | 无401/403或配额证据，不把DNS/robots结果解释成获批API权限或被拒 |

正常环境探针仅在默认环境出现操作系统级限制后通过工具的 `require_escalated` 正式审查执行；审查已通过，没有平台访问验证/验证码被绕过。对上轮errno8的解释来自本轮同类失败与对照结果，不声称重建上轮每一秒的主机网络状态。

### 实际响应

所有哈希均为客户端 `iter_bytes()` 得到的解码后正文SHA256，不是网页截图或文档示例。失败时状态、字节和哈希为null，未用空正文哈希冒充响应。

| URL / 阶段 | UTC开始→结束 | 状态 / 字节 | 正文SHA256 |
| --- | --- | --- | --- |
| `https://example.com`，控制HTTPS | 20:12:31.712557→20:12:32.747861 | 200 / 577 | `25ddf2c883e0d1958ea971d279a7e4f0fd446724ee3db7db19dadabd4a62e484` |
| `https://www.beardbrand.com/robots.txt`，目标前置 | 20:12:32.747880→20:12:33.788471 | 200 / 5842 | `cb5f296aa8946031f7720e4e05ac31cefb063efc2ca0e1120e18e0b896d85093` |

两项应用GET各执行一次；原transport处理Fake-IP时还使用其既有DoH解析请求，不能把“两个应用GET”误写成全流程仅有两次网络请求。20/10或10/5秒级有限超时、单响应2 MiB上限、无自动重定向；没有反复重试、扩店或切换身份。

## 真实robots与解析误放行

本次是正常联网实际取得并保存的目标响应，不沿用首轮工具缓存；不保证CDN背后源文件的最后更新时间。通配User-agent组在名称之后、每条规则之间均包含空行，正文明确有 `Disallow: /cart` 和 `Disallow: /policies/`。按组语义，`/cart.js`和`/policies/terms-of-service`不应自动访问；Fox Hunt/Beard Comb商品HTML路径不匹配上述禁止规则。

[RFC9309第2.1–2.2节](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2)允许组内空行，组以后续User-agent或文件结束为边界；空行不能把其后的规则变成没有归属。该标准同时说明robots不是访问授权，允许抓取路径也不授予商业再分发许可。

在本机Python3.12.15中，对保存的同一真实正文离线复现：

| 判断实现 | 商品HTML | `/cart.js` | `/policies/terms-of-service` |
| --- | --- | --- | --- |
| 现有RobotFileParser原样parse | true | **true，误放行** | **true，误放行** |
| 仅作诊断的去空行后parse | true | false | false |
| 本轮实际请求决定 | 未请求：条款前置未知 | 不请求 | 不请求 |

去空行比较是用于定位原因的受控诊断，**不是生产修复**；没有采用机械去空行的方式接线。首次 `ROBOTS_GATE.json`记录的是原解析器原始输出，不能据此作为实际许可。随后 `ROBOTS_PARSER_COMPARISON.json`与离线脚本记录对照及停止决定，保留首次结果而不改写历史；最终脚本另调用新统一保护，确认同一真实正文的商品路径true、cart和条款路径false。

基线影响位置：`market/discovery.py:59`、`market/catalog_prices.py:140`原样parse；`market/shopify.py:132`单商品Ajax没有自己的robots前置，直接cart再product。此风险已及时报告负责人，取得统一保护及三个入口的明确追加写权限后修复；Medium不修改这些文件。目录HTML链路无需cart，不能因cart被禁而宣称整个店铺商品不可读取。

## 最小统一修复与回归

新 `market/robots_policy.py` 由现有安全客户端读取一次根robots，2 MiB限额、UTF-8/纯文本检查，任何非200（含429/3xx）明确停止，无自动重定向/重试/缓存许可。保持既有公网地址与TLS检查，不创建另一套网络transport。

解析按组而非空行结束：忽略注释/空行，合并同名UA匹配组，存在精确UA时不混入通配组；最长规则匹配、同长度Allow优先，支持路径大小写、`*`/末尾`$`、UTF-8和未保留百分号编码比较。只支持REP通配，不把`[a-f]`等文本当任意正则；无效或无法安全读取的文本保守停止。crawl-delay作为项目扩展取匹配组最大值，至少1秒，支持有限非负数，超过30秒/无效值停止。

`discovery.py` 与 `catalog_prices.py` 复用该保护，保留100链接/3子图、10件批次及原单响应上限；先robots后地图或商品，失败仅返回错误而不生成成功价格。`shopify.py` 增加先robots、同时核实际locale/市场参数cart与product路径、再按delay依次请求；保留同客户端币种Cookie，原有限429重试也等待至少crawl-delay。任一端点被禁即不发送两个业务请求，不换来源猜币种。

这不是“已完整认证所有RFC行为”的承诺。项目继续保守停止重定向/4xx，而不采用标准中可选的放行策略；没有新增跨域跟随、缓存或任意爬虫能力。正常原HTML报价/目录与失败保留历史专项继续通过；默认禁止cart的店铺，其单商品Ajax现在会明确拒绝，这是一项有意的访问纪律收紧。主服务尚未由本队部署或重启。

受控回归与实站证据分开：`test_robots_policy.py` 使用重现真实空行形状的合成正文，覆盖分组/注释/多组/Allow优先/百分号/通配/延迟/状态/正文上限；对应三个入口专项验证无禁止请求、正常同客户端路径、目录/商品延迟、历史不变。真实5842字节正文只在私有离线复现脚本中重放，不将合成数据称实测商品。

## 商品字段和合法持续性状态

| 项目 | 本轮实际状态 |
| --- | --- |
| 来源身份 | 目标商店www.beardbrand.com；候选商品Fox Hunt `/products/fox-hunt-mens-cologne`，来自已有真实历史，不是本轮新商品响应 |
| 本轮商品ID / SKU / 币种 / 实际市场 / 价 | 全部未知；无新观测，不使用旧USD50或最低规格价填补 |
| 目录覆盖 / 截断 / 库存 / 上新下架 | 未请求、未知；没有“店铺0件/无库存/已下架”结论 |
| robots | 新鲜200已取得；明确禁止路径不能服从解析器误放行 |
| 条款正文 / 允许用途 / 商业再分发 | 标准条款入口在禁止路径下，未请求；用途和许可未知，不声称网站已拒绝某项API申请 |
| 销量 / 订单 / 营收 | 未取得、不推断；robots或商品目录均不是交易证据 |
| 持续合法可用数据链路 | **未通过**；本轮提供真实分层证据和具体停止路径，不以robots成功替代商品成功 |

负责人下一步先验收准确修复提交；仍需明确允许用途的来源证据，才能另定一次正常商品HTML样本验证。保持一个来源/商品的边界，不让用户为常规研发再批准，也不请求密钥/截图来绕过当前路径限制。

## 私有证据、复现与交付范围

本克隆 `.local/source-validation-20261022/` 下：

- `probe-20261021T201157823214Z/NETWORK_RECEIPT.json`：默认执行器失败，含所有阶段UTC与脱敏配置。
- `probe-20261021T201231579245Z/NETWORK_RECEIPT.json`、`control_https.body`、`target_robots.body`：正常环境成功；另有原始解析输出与后续比较收据。
- `network_probe.py`：有限网络/配置探针；每次仅建独立UTC目录不覆盖旧证据。网络复现必须另经正常执行权限许可，本轮不再次执行。
- `compare_robots.py`：只读取固定保存正文、先校验SHA再复现误判，无网络/ORM/数据库。
- `VALIDATION_RECEIPT.json`：Python版本、脚本语法、证据一致性、字节/哈希及0600文件/0700目录检查。
- `run_isolated_checks.py`及`tests-*.json`：显式内存SQLite配置，禁止导入config.settings；本轮受影响模块回归、check与迁移一致性。保留首次测试夹具重复进入client导致2项错误的收据；已改正夹具，最终准确源56项无跳过通过。

离线复现命令（不运行网络探针）：

```sh
cd /Users/qianpengfei/Documents/ChatGPT/shophot/.local/round2-source-20261022
/Users/qianpengfei/Documents/ChatGPT/shophot/.venv/bin/python -B .local/source-validation-20261022/compare_robots.py
```

验证：最终 `tests-20261021T202549722509Z.json`，56项0.601秒、完整调用1.241秒，无失败/skip；覆盖4个模块（含原失败历史与队列回归）。显式内存SQLite的test runner仅创建/销毁隔离测试schema与普通测试账号，未创建管理员；没有导入config.settings或连接既有数据库。Django check、makemigrations --check --dry-run（No changes detected）、`git diff --cached --check`通过。真实响应哈希/离线修复重放、私有权限和脚本语法通过；不重复PG/浏览器全套，不运行setup/生产迁移/worker。使用根.venv解释器运行本克隆代码，未写根cfg/源码。

本轮本地提交仅上述9文件，准确提交在负责人回执给出；不推送、不评论Issue、不操作根分支。完成即停止，由负责人维护HANDOFF/TEAM/日志、统一验收/运行启用并决定下一任务。
