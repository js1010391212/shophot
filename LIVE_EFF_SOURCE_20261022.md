# 本轮真实来源交付：EFF 45条商品目录，详情报价限流

**实际取得本轮新数据：EFF正式商店45条公开商品目录。单商品HTML请求429，未取得价格或规格报价。** 这是现有安全采集服务的真实网络结果，不是旧历史、demo或合成数据；完整“输入→报告”里程碑仍由负责人用同一正式网址独立Web验收。本文件不将目录成功夸大为商品详情/价格成功。

2026-10-22，北京时间；以下UTC。源码基线 `89d59f97a09dfa3571744c772b8b54b171c27305`，专属克隆 `.local/milestone-live-source-20261022`。原两来源冻结 `a0994b0bcba7eb89256648da7f06add7d8d2f4b5`及旧分支完整保留；本追加在 `codex/milestone-live-source-permissions-20261022`。没有商品解析代码缺口，不改源码/数据库/账号/服务。

## 来源身份及适用许可

负责人明确追加Arduino/EFF两条官方许可线索，未擅自无限扩店。原LILYGO与Beardbrand的429资源没有再次请求，前轮具体失败见MILESTONE_LIVE_SOURCE_20261022.md。

- Arduino官方terms/trademark均真实200。主站条款1.2/8.4包含个人使用及单设备下载边界，也限制镜像/其他网站使用；商标页CC BY-SA只明确覆盖编辑材料。商店首页未提供同域条款链接，不能把主站编辑许可直接当成商品数据转入另一Web报告的许可。本轮没有取得足够针对该链路的依据，未读其商品；不是宣称私人下载绝对禁止。
- [EFF官方版权政策](https://www.eff.org/copyright)本轮真实200：原创材料按CC BY4.0授权，其他权利人的材料可能另需许可，另有具体标注除外。未把主站许可自动外推到商店。
- EFF版权页自身“Shop”链接为`https://shop.eff.org`；该官方子域robots返回301，Location解析主机为`shopeff.org`，原请求停止且未自动跟随。负责人明确认可可核正式规范域名，随后将 **[https://shopeff.org](https://shopeff.org)** 作为新的明确商店输入，独立取得该域robots与首页200。不是myshopify镜像、代理或换域重取被拒商品。
- 规范商店首页标题为“Electronic Frontier Foundation - EFF Shop”，canonical为`https://shopeff.org/`。**该商店自己的页脚**明确写“Copyright (CC BY)”并链接`https://eff.org/copyright`，同时显示EFF身份与Powered by Shopify。这个商店自身的引用，而非仅共同域名，构成本轮原创材料许可适用依据。未找到另外同域Terms/Legal链接，也未看到冲突的自动化禁止声明；没有访问cart或未获准路径。

当前使用限定一台本机私人研究，保留EFF署名、原始网址与[CC BY4.0链接](https://creativecommons.org/licenses/by/4.0/)，标明分析由ShopHot生成、不是EFF认可或合作。该明确许可对EFF原创材料提供复用依据，但不证明所有第三方图案、商标或产品图片均可商业利用；未下载任何图片二进制、未对外发布或售卖数据。preflight旧purpose字符串中的“commercial redistribution not licensed”是本轮任务未授权对外发布的限制，不能解读为否认官方CC对原创材料的授权。

### 正式前置证据

| 资源 | UTC取得区间 | 状态/字节 | 正文SHA256 |
| --- | --- | --- | --- |
| EFF官方版权`/copyright` | 01:51:11.830510–01:51:13.011486 | 200 / 33945 | `6db5b00adeff1da4314ea7326832923ec3f078a3458f39564a0e6704beeb0330` |
| 规范商店robots | 01:52:40.722308–01:52:42.249805 | 200 / 3633 | `97e0987b4c2533e7ced4bbae77f57211ef6558ae22bfb1467d1fc862890c630b` |
| 规范商店自身首页/页脚 | 01:52:43.254978–01:52:43.618161 | 200 / 161861 | `8e7fc79fc6ce148d874ee0e647c8ad373c678fa6d2ab7066c70af79b102c956c` |

## 实际目录与单商品读取

通过前置后，`collect_eff_once.py`调用**当前原实现**`discover`→`collect_catalog_prices`，同一PublicProductTransport客户端、trust_env=False、HTTPS/IP/TLS校验、无自动重定向，2MiB响应上限，至多8个应用请求、1件商品。本轮实际5个应用GET；transport内仍有原Fake-IP可信解析处理，不声称全流程仅5个网络请求。没有config.settings、ORM或主库连接，显式配置DATABASES={}仅供时间工具使用。

| 阶段/资源 | UTC开始→结束 | 状态 / 解码后字节 | SHA256 |
| --- | --- | --- | --- |
| discovery robots | 01:55:03.638114→01:55:04.851797 | 200 / 3633 | `97e0987b4c2533e7ced4bbae77f57211ef6558ae22bfb1467d1fc862890c630b` |
| `/sitemap.xml` | 01:55:05.856505→01:55:06.157251 | 200 / 854 | `1a54a7b96b1a9d31b7e0c57b0db63f22902551a48832d7d4ea954992acf9599d` |
| `/sitemap_products_1.xml?from=7050314350771&to=8739164324019` | 01:55:07.160339→01:55:07.461225 | 200 / 19638 | `035bb40f81c1521d97e374934027a11a3bd0b7f29e7b9d78544085a7ff9d0181` |
| HTML阶段robots | 01:55:07.470020→01:55:07.734288 | 200 / 3633 | 同上robots哈希 |
| `/products/eff30-multisticker-sheet` | 01:55:08.735530→01:55:08.944378 | **429 / 未读取正文** | null；没有空正文伪哈希 |

服务对sitemap/商品业务请求保留至少1秒等待；两个服务边界的robots读取紧接前次地图完成，准确间隔见收据，不虚称所有HTTP请求均间隔1秒。没有Retry-After/全站限额的已验证解释，不将429归咎某个确定原因；收到429后停止，未重取同商品、另一商品或alternate域名，也未改UA/cookie/代理/TLS/DNS。

429可核元数据：请求UTC `2026-10-22T01:55:08.735530+00:00`，结束`01:55:08.944378+00:00`，Server Date为`Thu, 22 Oct 2026 01:55:08 GMT`，Content-Type为`text/plain`。**Retry-After头没有被本次审计包装保存，值是“未记录”，不是已经确认不存在。** 同样未保存挑战/认证提示头，采集器在非200即停、未读正文，不能排除或认定挑战/身份限制。已存记录没有可验证冷却条件，不能猜等待时长后自动重试；补说明只读已存收据，无新请求。

`LIVE_CATALOG_RESULT.json`含45条真实URL、标题及原sitemap lastmod，`limited=false`仅表示本次未触100链接/3商品子图的程序截断上限，不表示库存45件或全店/全平台完整覆盖。

| 真实新目录样本 | 原URL |
| --- | --- |
| EFF Logo T-Shirt | `https://shopeff.org/products/eff-logo-t-shirt` |
| Barlow Frontier T-Shirt | `https://shopeff.org/products/barlow-frontier-t-shirt` |
| Digital Freedom Analog Postcards | `https://shopeff.org/products/digital-freedom-analog-postcards` |

三个样本原lastmod均为`2026-10-21T18:55:07-07:00`；这是站点声明修改时间，不是上架时间、采集时间或报价时间。实际采集时间使用上述本轮UTC和原响应收据。

字段限制：本轮SKU、规格范围、币种、价格、收货国家、库存、销量、评论均未知；不得补0、计算价格分布/毛利/销量趋势或借旧样本填补。可用的报告内容是这45条真实目录及有分母的标题词/商品链接研究；须显示成功目录与429详情失败、无新报价及版权归属。不能把“有效报价0条”写成“价格0”或“无商品”。

## 给负责人/Medium的实际数据接口

原始目录结果保持现有服务返回格式：`{products:[{url,title,lastmod},...],limited:false}`，可直接交现有目录报告使用，禁止先转换成假的Product/Snapshot或补造价格。

本克隆私有数据路径：`.local/live-source-evidence/eff-live-20261022T015503559815Z/`：

- `LIVE_CATALOG_RESULT.json`：本轮实际45条目录，非fixture或历史备份。
- `01.body`–`04.body`：实际robots/地图正文；哈希和原URL逐项在`LIVE_RUN_RECEIPT.json`。
- `SOURCE_USE_DECISION.json`：业务读取前已记录的商店自身许可依据和私人使用/第三方素材边界。
- `LIVE_RUN_RECEIPT.json`：本轮源站请求与429、实际选定商品、上限、无config.settings/数据库的证据。原outcome为stopped，原因在详情429；不能忽略已成功目录，也不能反称整轮全部成功。
- `HANDOFF_DATA_INDEX.json`：目录成功/详情失败的明确数据索引，已离线校验保存正文长度/哈希。
- `LIMIT_STATUS_NOTE.json`：429准确UTC、已存Content-Type/Server Date、Retry-After未记录及挑战/身份限制未知；不伪报“无”，不据此生成冷却重试安排。

`collect_eff_once.py`是精确执行脚本，只用原服务加私有审计包装保存解码正文，未替换transport或另建采集系统。身份/许可脚本与Arduino/EFF原前置响应也仅在`.local/live-source-evidence/`保存；目录0700、文件0600。不要立即重跑已被拒的商品；本轮无后续网络请求。负责人可使用允许的规范店铺输入独立验证目录报告，任何被拒资源仍须遵守停止边界。

原两店文件及本补充是文档/证据交付，生产源码未改，未重复应用/PG/浏览器全套。验证为真实保存响应和45条结果一致性、脚本语法/私有权限、`git diff --check`；报告、截图和整个里程碑的独立Web验收尚属负责人，不在此虚报。准确分支/提交/文件哈希由本克隆`.local/DELIVERY_EFF_RECEIPT.json`固定；不推送、不评论Issue、不动账号或主服务。
