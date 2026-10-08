# 本轮浏览器采集交付契约（负责人，2026-10-08）

基线：main `6b922eba220a6b08e24e12859510023cb8f944c8`。额度已恢复。先读现有AGENTS/HANDOFF/DEVELOPMENT_GUIDE/DATA_ACQUISITION_PLAN；本文件限定本轮交付。两队独立目录，保留现有模型，高级high、本地medium；都提交准确分支/commit给负责人，不推送/合并/改负责人文档、不启动worker。独立SQLite专项，负责人只跑一轮最终PostgreSQL全套。

## B2 高级队：浏览器扩展与真实DOM

只拥有 `extensions/shophot-capture/`、扩展测试与该目录README/证据清单。复用browser_capture.py协议字段，别改后端模型/服务/路由/模板/迁移。Chrome MV3点击activeTab+scripting获取当前顶层正常商品页，有限公开DOM，不读cookies/账号存储/私有接口，不发网络采集，不自动开外站，不绕过验证。速卖通优先，既有历史链接验证受阻不重复绕过；没有正常页时用已有可见OTTO验证公共桥接并明确速卖通未验收。两商品、一商品两规格才声明平台实站通过，无样本则清晰区分框架/夹具与实站。

固定本地地址 `http://127.0.0.1:8000/browser/capture/`，localhost同端口可作为可选地址。只在用户点击时开本地页；内部runtime消息+严格sender扩展/本地origin/tab检查，数据放扩展session受控存储、10分钟TTL，不暴露任意网页window消息或externally_connectable。不要将完整payload/凭据/令牌放URL。收到预览不显示成已保存。需可见的验证页/错误规格/含糊金额/未登录/服务离线/扩展失效提示。

桥接初始GET页面有 `#browser-capture-form`，普通同源POST字段 `target_url` 与 `capture`（UTF-8 JSON文本）及CSRF；标志 `data-browser-capture-bridge="ready"`。仅初始页自动填表并requestSubmit一次。签名预览确认页没有此标志，不能再次自动发送。目标URL从正常页提取、清理跟踪参数但保留sku_id/variationId，完整JSON按B1契约，未知null，价格十进制字符串，quote_type=current。正常浏览器页面可见报价和明确身份才发送，验证页/推荐区/含糊报价拒绝。不从语言推国家，不用折扣最低价替代普通当前报价。

## B3 本地队：登录、预览、确认与对应报告

独立 `browser_capture_views.py`/必要forms/templates/static，使用已有parse_capture/sign_preview/load_preview；不得把传入owner/product_pk作为认证。集中market/urls.py路由；GET不创建Product或Snapshot。桥接GET只读，POST完整校验后事务建立/复用Product、从数据库目标URL签名预览（不创建Snapshot），显示原URL/规格/金额/币种/国家未知/条件/原观测时间/可见证据。明确客户端声明不证明真实性，用户核对确认后POST保存。

本轮负责人批准以下Snapshot扩展与隔离方式（不另建商品库）：
- Source增加browser（浏览器主动观测）；新增owner nullable FK账号、capture_id nullable UUID、capture_data JSON default={}，旧历史不补造条件。
- 默认Snapshot.objects和Product.snapshots只读历史公共来源（排除browser）；另提供Snapshot.all_objects无过滤供此模块显式读写。已有列表/CSV/对比/利润/评论保持公共历史查询，浏览器数据只在本模块按当前owner读。CSV导入拒绝保留的browser来源，不能伪造私有观测。
- 原unique_observation改为条件约束仅公共来源；新增(owner,capture_id)的browser唯一约束；数据Check：browser必须owner/capture_id非空，公共来源两者必须空。仅新增0012迁移，不改旧迁移。
- 确认事务锁Product，用当前URL/platform复核签名；来源browser，原观测时间不改。capture_data完整保存规范capture，context仅展示摘要，不能用截断context做条件判断。相同账号capture_id重复幂等；同capture_id不同内容/商品拒绝，失败不覆盖；另账号相同UUID独立保存。
- 对应报告 `/products/<pk>/browser/`，仅当前owner的browser观测，与旧公共报告互链。每条明示国家/规格/报价条件/来源/时间，按币种与完整条件签名隔离分组；首版只列记录，不跨条件连线或计算涨跌，未知条件不声称可比较。确认成功直接到对应报告，不要求用户去侧栏寻找。
- 浏览器UI普通模板自动转义证据/标题，不展示签名令牌，POST保留CSRF。入口表单body设有限大小（capture解码UTF-8≤16KiB，form总正文合理上限），重复参数/错Content-Type/无JSON/过期/改商品/另账号显示具体失败。GET/失败不新增观测。

有意义回归：登录/CSRF、GET不写、预览不保存、签名错账号/商品/规格/过期、重复/冲突/并发原子、不同账号隔离、同时间多账号、browser来源CSV拒绝、旧报告/导出/对比/利润不混私有数据、错误保留历史、未知值。本轮不接评论/店铺/自动定时采集。桌面/390px与最终服务由负责人集成后统一验证，两队不要启动服务争端口。
