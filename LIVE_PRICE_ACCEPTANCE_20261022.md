# Adafruit 店铺到真实商品报价和竞品报告：验收与发布记录

本轮仅复用已有输入→进度→目录/报价worker→竞品报告、商品详情、候选及历史。PR30已合并；价格能力仍在PR31，最终CI/合并与主服务启用以文末准确发布回执为准。本文件覆盖旧候选“网络尚未执行”的停止记录，原始失败日志与各阶段提交保留。

## 实际产品路径与来源

负责人在全新隔离SQLite、普通非staff非superuser账号，从首页默认目录与报价输入 https://www.adafruit.com，原worker通过原PublicProductTransport实际读取允许的robots/sitemap与默认首批10个商品页面，自动进入竞品报告；没有导入High样本、强插4864、重排目录或伪造Snapshot。13指保存审计的应用GET，transport内部可能的DNS查询另计。目录与报价按原100/10上限、至少12.1秒间隔、2MB限制、TLS/身份校验、robots、不跟随重定向与非200停止执行。

真实首批结果为100条有限目录、2条有效报价、8条明确拒绝、90条未安排；不存在全店/全部在售/销量保证。两条成功为SKU9 High-strength 'rare earth' magnet（2.50 USD）及SKU16 Altoids Gum sized tin（2.00 USD），观测为2026-10-22 07:47 UTC，页面标注InStock；订单可执行性、数量/地域/税运/优惠未知。报告自动展示有效覆盖2/100、失败8、本批新2/历史沿用0、独立USD价格分布与9个标题词；单次观测不生成趋势/销量，站点地图时间不当上架时间。

实际GET原始body是gzip传输容器，01–13长度与SHA256全部核同；有界解压后的robots310字节、sitemap1204160字节与High早前Phase A完全一致。旧样本是iter_bytes解码正文，不以压缩体积差异判断来源真伪。原头未保存Content-Encoding，不补造。逐条传输/解码哈希及代码路径审计在私有收据；本轮诊断无新HTTP，不把保存响应重放当新采集。

仅个人本机最少商品事实研究；不保存/热链图片、描述或评论。官方 /products_api 文档可用，但robots禁止/api/，API请求为0；不绕登录/robots/限流/工具限制，不称商业再分发许可、法律保证或所有平台支持。实际前置及限定见LIVE_PRICE_SOURCE_20261022.md。

## 恢复后的具体修复与复验

High PRICE-HTML-C：从候选586ed523独立离线核保存的8个拒绝。名称只在主/移动H1、schema基础名、固定格式title、OG/Twitter全部一致时接受已验证修订或型号后缀，保留完整可见版本名。明确schema Discontinued与DOM No longer stocked配对才保留停止供应状态，不变成有货。原目标PID/SKU/Offer/主价格USD/所选版本检查保留。准确源618fe96cb63a5bff63d4fd41ed99889617bbb373，24专项通过。

保存10页离线复演为6接受/4拒绝：5/19含无明确选择且其他PID的part_id规格，30/31 schema OutOfStock与主DOM In stock真正冲突，继续拒绝。新增可解析4页只证明解析修复；原实时2条观测和原始13响应不变，没有回填旧时点或声称新采集6条。完整逐项依据见ADAFRUIT_OFFLINE_DIAGNOSIS_20261022.md。

Medium PRICE-HTML-D：报价失败/尚未报价时也按已知规范来源展示facts_only范围，GET不修改事实或建立任务；隐藏旧图文/评论并修正更新通知，其他来源保留原行为。准确2695af54e56eb69988fe4d41634242a47418246e，22项隔离专项通过。负责人已在真实保存的失败商品和成功SKU9实际桌面1280/手机390复验，未知价格/SKU不造0，仍可保存私有候选，缺报价候选禁用比较且无可引用历史报价。

负责人实际补验：SKU/币种/规格/来源/时点详情、报告价格分布、空筛选仍保留100分母、移动文档宽390/表格局部横滚、菜单退出、候选成功与失败分支。截图为实际本机页面，不是示意图。原有效2条报价未改变，Product/Snapshot/CollectionJob仍0。QA操作中另产生一个queued刷新scan2，未运行worker/新HTTP，源scan1/观测保持，保留记录不掩盖；原UI截图误名和辅助脚本失败已在UI_RESUME_RECEIPT说明。

## 测试与发布准确性

上一候选586ed523最终随机隔离PG634项107.202秒、无skip通过，含Node/并发，随机库已清理。首次634的3个错误来自QA独立cookie名与旧测试默认csrftoken不兼容；只在PG测试设置恢复默认cookie，UI隔离cookie未改，失败日志保留。不能把旧634当作本次修订后的全套结果。

Medium E b3a83c2c07279b094b39111a8f20faab2ddb8490以最小三处映射接通Discontinued→停止供应（不宣称厂家停产/库存数量），报告/详情/历史/候选/筛选均有回归。原Medium对C618fe96精确两文件和有界解压收据独立审查，24专项通过；原High对D2695精确两业务文件只读审查及8单点通过，均未复现P1/P2，两队完成停止。

负责人最终业务8c733ad7098dc338022c74f07fc2bbdf195734ed随机隔离PG650项106.322秒、无skip通过（含Node/真并发），随机库已清理。因本轮新增公共状态映射/视图分支，在最终源做此一次必要回归，不重跑未变旧634，不重复网络采集或旧物流/预算/备份。迁移/check/diff清。实际最后UI1280/390的失败facts_only与成功SKU9/候选兼容、停止供应筛选在原真实数据中0条均过，未导入停供夹具到QA库。QA自己的tab退出关闭/viewportreset、8007准确PID29049核cwd/命令后TERM，私有UI_FINAL_RECEIPT及截图保留。没有模型/迁移/新路由/依赖/worker/transport/利润数学变化。

## 私有证据与复演

review克隆.local/live-web-price-source/LIVE_WEB_PRICE_RECEIPT.json、01–13.body、UI_RESUME_RECEIPT.json、.local/ui截图、PRICE_PG_RECEIPT与日志保留0700/0600；High独立clone的SOURCE_BODY_AUDIT/TRANSPORT_PATH_AUDIT/PRICE_HTML_C_REPLAY等同样保留，不提交真实库、凭据、原始图文或私有配置。QA使用既有隔离普通账号，不读原用户凭据/新建管理员。

已保存QA库可按私有独立settings在127.0.0.1:8007显式启动无worker服务，登录普通QA后查看/stores/1/research/和详情/候选；打开保存报告不会联网采集。不要重跑初始0表断言的一次采集helper，不把重放旧HTML记为现在报价。真实新采集只能在当前允许条件下原流程有界执行。

## 发布回执

最终业务集成、独立增量审查、变更后650项及实际UI通过；当前准备更新准确PR31 tree/CI，远端发布收据另存。本地原服务当前仍PR30业务，尚未启用本候选；不提前宣称已合并或GA。44b99b5和所有旧分支/clone/WIP/凭据保留。
