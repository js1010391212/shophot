# TIME-QUOTE 历史报价展示时间

独立 clone `.local/time-quote-20261022` / branch `codex/time-quote-20261022`，准确基线13a529472bc40714186f5474b16dd733a21252bd。

## 范围与精度

catalog_coverage.py新增独立只读展示解析 helper，接受带明确时区ISO（含原aware datetime），另严格支持历史 `YYYY-MM-DD HH:MM UTC`（ASCII数字、明确UTC、合法日期）。返回时刻及来源精度，不修改原字符串。research.html按精度转换北京时间：旧12:47 UTC显示20:47，不虚构20:47:00；ISO有秒保持到秒，无秒到分钟。naive、缺时区、非法日期、未知缩写或扩展格式继续显示未知，无当前时间补值。未更改其他页面。

原moment逐字功能/AST不变，继续只用于既有任务时窗等逻辑；in_window、任务状态分支、freshness、有效报价金额/SKU、观测归属与统计均不变。只新增展示字段quote_seen_precision并使用独立展示parser赋quote_seen_at，无数据库写入或旧数据迁移。

## 验证

新3项含多组边界案例，加原coverage/research共32项，显式独立clone内SQLite隔离库，0.649秒无skip。测试原历史分钟串/带偏移ISO/秒/naive/非法/注入文本，实际Django报告分钟和秒格式、未知恰一条；旧分钟attempt仍不能参与in_window，不被错误标成明确失败；GET前后原目录内容完全一致，job数不变且0报价观测写入。独立配置不导入config.settings，不读真实数据库配置或凭据。check、迁移一致性、diff check通过，原moment/quote_values/_planned_indices/coverage_message AST核同。

无HTTP、真实库/凭据/浏览器/服务操作，无旧650重跑。负责人仍需精确审查、必要最终回归、真实原六报价报告验收和上传；本队完成冻结后停止。

## P2 关闭：北京时间转换越界

High准确b3审查所报上界UTC分钟格式及下界带offset可使真实research.html抛OverflowError。新增2项实际模板渲染测试先复现（5子例均OverflowError，.local/time-quote-p2-repro.log保留）。显示helper所有返回路径统一先核astimezone(ZoneInfo('Asia/Shanghai'))；捕获OverflowError/ValueError后未知，不夹日期、不补当前时间。legacy/ISO/aware上下界5子例均未知，合法上界9999-12-31 12:00 UTC仍按20:00显示、普通分钟精度保持。原moment/任务时窗等逻辑不变。

只跑本文件5项隔离专项，0.084秒无skip；check/迁移/diff清，无32或650重跑/HTTP/真实库凭据/浏览器服务操作。.local/time-quote-p2-tests.log保留；负责人准确增量复核和原六报价实页验收待完成。本轮完成停止。

## 负责人准确候选验收

修前集成业务29ed5d92b04a1de29ac47cb7679590252961a5ae随机隔离PG653项109.301秒无skip、库清理；这是时区边界保护前的全套，不能称修后全套。High准确只读找到极端年份转Asia/Shanghai溢出P2，Medium已在7c7ea699993e385c8d609554b48fbfda59567849增加全部路径统一保护及实际模板边界回归。负责人修后集成2739b3f32b58915434e3726199f49b4503f06bbf隔离PG34项2.264秒无skip、库清理、check/diff通过，覆盖时间/原coverage/research。High独立增量关闭P2仍待恢复，未远端合并/未启用main。原六条真实保存数据的桌面/390手机已实际确认五历史分钟时间与一当前真实秒时间正确、无整页横溢，截图保留；边界保护没有改变这些正常分支。没有为本次展示修复重取外部数据或修改旧观测/任务/成本。

## 2026-10-23 最终关闭与本机启用

High对7c最终源与集成三文件逐字核同，7个无库实际模板边界通过，原P2关闭，无新的可复现P1/P2。负责人核验既有修后PG34、正常六观测两布局与CI39784174464成功，不重复测试。PR32按准确1d6ef2de合并main f754e775891d0288742da92943b1cc18f36c3246，整tree6b632f20db1f67863fcbc64071a45279024d0dab与本地review b866aa一致。根正常合并保留全部历史，标准冷启和只读全表前后指纹一致、登录/身份保护烟测通过；准确运行收据.local/time-quote-release-20261023/RUNTIME_RECEIPT.json，后续PID维护前重核。无新商品请求/主库QA/原账号或凭据操作。下一转第二独立合法来源与可重复监测，不再围绕本店扩功能。
