# Pololu 精确标题兼容及真实增量验收

原源对5359误拒的根因：schema名称、H1、HTMLtitle精确相同，但HTMLtitle没有额外“Pololu - ”前缀。5359的名称本身以Pololu开头，不能删去品牌词、模糊匹配或忽略名称来制造成功。

## 代码与独立审查

High基线`b7f885c4189977a34eed01b8aa6960bea491f17c`，精确提交`7fcbab89b0061083b267a67d46a476bb75d0dc31`，负责人review纳入`a4632de`。仅`pololu_catalog.py`一个谓词：HTMLtitle必须精确等于规范化schema/H1名称，或精确“Pololu - ”加同名称。反向替换该谓词后源文件与发布基线逐字相同，目录/网络/保存/历史/监测等调用点不变。

唯一Product、显式SKU/URL PID、H1、DOM编号、主form ID、Offer URL、默认数量1、USD主价格与第一数量档一致、Active and Preferred/InStock、限供拒绝全部保留；无新model/迁移/route/worker/依赖/数学/UI、公共identity或transport变化。

3项新增无库专项0.077秒通过，覆盖两种精确标题、相似/错名/重复title、错H1、SKU/form/Offer/数量/价格/币种/库存/限供反证。Medium只读独立审查精确源及保存真实5359正文，并用该正文独立核5项身份/数量/主价格/限供反证，均拒绝，未发现可复现P1/P2。未重复旧10/6/36/650/653或原专项；离线接受没有写新观测。

## 真正新增的单件业务结果

普通隔离QA保留原库及6条观测，从原商品详情“更新当前商品”POST排队，经原`run_store_prices`一次处理。只新请求规范robots和5359 HTML，2应用GET均200；不重取目录/其它商品/API，不启动总worker。原PublicProductTransport、UA、TLS、IP校验、2MB、有界解码、无重定向/非200即停及robots检查保持；两请求完成到下次开始间隔12.112306秒。用途仍为个人本机最少数值事实研究，不宣称商业许可/持续可用/可下单。

- robots开始UTC2026-10-22 23:13:25.127572，HTTP200，378字节，SHA256 `12f966e37e27a1bf457915ca8995ce6ab18f79c98be3680651ff2d9e5f104bb9`。
- [5359规范来源](https://www.pololu.com/product/5359)开始23:13:38.724564，完成23:13:39.991506，HTTP200。wire20988字节/hash `4aacd233d8e4a84f3a9ff21880cb2b2914912179d857f43024d9085b2eb46dc5`；解码76406字节/hash `aeebd4aadcdf9dfc04bf6289cd3a8973358c243c55dc26f347a114a8bb2fc89b`。
- 新独立观测7，job3，观测时点23:13:40.077374UTC，显式SKU5359、USD7.95、固定数量1、InStock为来源声明；不是保证库存数量/履约。未采集图片描述评论，国家、税运、优惠和销量未知。
- 旧6条观测、旧2个job、暂停监测全字段指纹不变。原首批10仍是当时5成功5拒；跨本轮单件更新，原不同10目标累计6取得有效价/SKU、4仍不支持。不能改写为原单轮60%。有限首页报告实际6/12，本批新1、沿用5；不是全店覆盖。
- 749为Service契约不支持；3728为OutOfStock不支持；5793/5784为Rationed限供条件不支持。四项未重取且继续拒绝，不能称网站缺字段或补为在售；另2目录候选未安排。

实际1280/390详情可见5359/7.95/新时间，原竞品报告6/12正确且未知保留，整页宽度分别1280/390无溢出。未重复24小时监测或旧闭环；原5745两次同价/变化0的实证保持，其它未观测变化不推断。

## 保存与运行边界

High私有审查及3专项日志：其`.local/source2-title-20261023/`；Medium精确审查`.local/SOURCE2_D_REVIEW_RECEIPT.json`。负责人review `.local/source2-title-live/`保存新wire/decoded、时间hash/必要响应头、STATE、LIVE/UI/STOP收据，`.local/ui/source2-title-*`是真实截图，均0600；旧证据未覆盖。QA8008已核cwd/命令TERM退出、普通账号退出、自己tab关闭和viewport reset；不留常驻QAworker，库/普通QA凭据保留。

主库/原账号/会话/权限/私人凭据未操作，发布前主源仍PR33。最终准确发布/CI/主服务启用与只读前后核对由负责人另记收据；未完成前不称已启用。保留44b99b5及所有旧成果，不reset/stash/强推。本有界兼容问题完成后停止，后续依具体使用/监测反馈，不无限逐店打磨或增加无关功能。
