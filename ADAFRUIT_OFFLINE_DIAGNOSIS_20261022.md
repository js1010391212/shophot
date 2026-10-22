# PRICE-HTML-C：Adafruit保存响应离线诊断

基线`586ed523d65cbabc3b7d1c8bb1eef264d2bfc2b7`；独立克隆`.local/adafruit-diagnostics-20261022`，分支`codex/adafruit-offline-diagnostics-20261022`。只改专用解析器、其专项测试和本说明，不改公共接线/UI/model/worker。没有新HTTP、重新采集、API、代理/UA变更、数据库访问或凭据操作；原两条观测和原始收据不回写。PR31仍为负责人待验收草稿。

## 正文和传输核证

只读核对负责人review克隆`.local/live-web-price-source/LIVE_WEB_PRICE_RECEIPT.json`与`01–13.body`：13份传输字节长度和SHA256全部匹配，均为可有界解压的gzip容器。解压后robots310字节，SHA256 `d48c3bfae49688bf2c504f8596d62ad036a3f31ebc028d1a64f3c42adcbaf7f7`；sitemap1204160字节，SHA256 `38594f85fda00675f0b1c32ab602186ca14b6352a902fbfd766d113f4c3fa5a0`。两者与Phase A解码正文逐字一致，目录仍6396个URL。

产品原容器15473–19347字节，解压后59656–84848字节，均有唯一主Product及既有页面结构。旧Phase A保存`response.iter_bytes()`解码后正文；负责人脚本包装`response.stream`、原样yield传输字节，HTTPX随后在`iter_bytes()`解码。原保存头未记录Content-Encoding，此处gzip判断来自容器魔数和实际有界解压，不补造未存响应头。

静态核对`.local/run_live_price_once.py`：Audit继承原PublicProductTransport，将原request交给`super().handle_request`；Body不替换内容，完整流结束后记录哈希。network.py逐字匹配候选基线，默认HTTPTransport、公网IP固定连接及TLS/SNI保留。QA settings顶层仅os/Path导入、赋值和断言；优先.local下没有httpx/market/socket/django/sitecustomize影子模块。未发现夹具替换证据；保存记录与检查的代码路径一致，但静态文件不是新TLS连接证明，本轮始终为离线重放。13仅指审计覆盖的应用GET，transport可能的内部DoH不在该计数内。

逐份传输/解码哈希、形状和原解析结果见本克隆`.local/SOURCE_BODY_AUDIT.json`；传输核证见`.local/TRANSPORT_PATH_AUDIT.json`。原始文件不移动、改写或提交。原脚本SHA256为`0425eeefff5ac6a8b261b1e6f6fd7b93bb890382648d644e7843e9b8cccc7764`，原收据SHA256为`481920543a681307a68b1fca82297c97f79f33a909cdac9dad767b48c05e8c9a`。

## 最小修复与边界

六页schema/OG/Twitter均给基础名，桌面/移动H1为`基础名 - 版本`，HTML title独立为`基础名 [版本] : 固定商家后缀`。新增匹配要求全部证据、唯一移动H1、已验证v/V数字修订形式或确切型号FT232RL。任意共同前缀/后缀或元数据缺失/冲突仍拒绝；返回完整可见名称，不删版本。原目标PID、显式SKU、规范域名、Offer、所选规格、主价格和USD检查保留。

五页明确schema `Discontinued`，主DOM为`No longer stocked`，新增此精确配对；DTO及单规格availability保留`Discontinued`。存在选择控件时，所选状态也必须明确一致。它不是InStock、OutOfStock、库存数量或可购买承诺；金额只是停产页面公开显示值，价格更新时间和是否接受订单未知。其他状态或冲突仍拒绝。

## 逐条离线结果

以下全部是保存响应重放，未新增采集或数据库观测，金额为USD主要货币单位。

| PID / 文件 | 原结果 | 本次离线结果及根因 |
| --- | --- | --- |
| 1 / 04.body | 名称拒绝 | 通过12.50，Discontinued；完整名MiniPOV 2 Kit - V 2.1a |
| 5 / 05.body | 名称拒绝 | 名称核对后仍拒绝：part_id下拉需选LED颜色，533/534/535为其他PID，无明确selected；默认提示不是选中SKU |
| 9 / 06.body | 通过2.50 | 保持2.50，InStock，SKU9 |
| 14 / 07.body | 名称拒绝 | 通过19.50，Discontinued；完整名MintyBoost Kit - v3.0 |
| 16 / 08.body | 通过2.00 | 保持2.00，InStock，SKU16 |
| 18 / 09.body | 名称拒绝 | 通过17.50，InStock；完整名USB/Serial Converter - FT232RL |
| 19 / 10.body | 名称拒绝 | 名称核对后仍拒绝：LED颜色/端口下拉540/541/542为其他PID，无明确选择，不混133.00选项价 |
| 20 / 11.body | 名称拒绝 | 通过17.50，Discontinued；完整名MiniPOV 3 Kit - V 3.0 |
| 30 / 12.body | 库存拒绝 | 继续拒绝：schema OutOfStock、主DOM In stock，不能任选一边 |
| 31 / 13.body | 库存拒绝 | 继续拒绝：schema OutOfStock、主DOM In stock，不能任选一边 |

候选离线6通过/4拒绝，新增可解析4页；本轮未改写原两条观测，不能称新采集6条或10/10。旧4864保存正文亦通过：4.00 USD、Pico without Headers、OutOfStock。facts_only保持，图文不返回，未知数量/税运/市场/优惠不填0。

## 验证与交接

24项专用测试全部通过（原15+新增9），涵盖名称证据缺失/冲突、任意后缀、完整版本标题、PID/SKU/外域/USD/价格不放松、未选part_id、选中SKU冲突、停产主/所选状态及库存真冲突。新增正向样本先复现旧解析器名称拒绝，修复后通过。最小独立Django配置`DATABASES={}`，跳过数据库，最小check和diff check通过。不重跑634 PG、主设置、迁移、浏览器或整链路。

本克隆`.local/PRICE_HTML_C_TESTS.log`、`PRICE_HTML_C_REPLAY.json`及复演脚本保存精确结果；socket阻断下离线复演，并核原收据未变。最终SHA/文件哈希见`.local/PRICE_HTML_C_DELIVERY_RECEIPT.json`。负责人按准确提交验收，剩余四页及未来未知型号/格式保持明确拒绝；本轮完成即停，不为覆盖率泛化。

### 集成门槛与独立D审查补充

C业务准确提交`618fe96cb63a5bff63d4fd41ed99889617bbb373`。负责人另确认既有research库存标签、availability模板及ResearchFilterForm尚无Discontinued接线，当前公开展示会降为未知；这是合入/验收前需由负责人和Medium补齐的集成缺口，本队不扩大公共文件。离线可解析6页不等于现有两条观测改变，也不等于该展示门槛已通过。

按负责人追加授权，只读审查Medium D准确`2695af54e56eb69988fe4d41634242a47418246e`相对586ed523的views.py与catalog_detail.html增量，并读取对应专项作为证据。来源scope由明确facts_only或严格规范根/商品路径决定，未报价/失败也不承诺图文评论，旧其他来源仍按原路径。事实范围优先隐藏陈旧图文评论；登录、POST、事务锁及任务约束未改。提取准确helper和三段实际模板做8个只读单点核验全部通过，覆盖未报价、失败、显式策略、其他源、别名、查询、外域及旧内容抑制；未复现P1/P2，不修改D文件，不重复其22项或634全套，无HTTP/DB。证据`.local/PRICE_HTML_D_REVIEW_RECEIPT.json`；完整页面和移动端仍由负责人验收。C与D汇总精确SHA/文件哈希见`.local/PRICE_HTML_CD_FINAL_RECEIPT.json`。
