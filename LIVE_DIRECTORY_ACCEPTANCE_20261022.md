# 真实店铺输入到目录分析报告：实际验收

本轮已用真实店铺完成目录范围的产品路径，不再仅交研究文档。**商品详情、价格、SKU/规格、币种和销量未取得；不能据此宣布完整数据/报价里程碑或商业可用完成。**

## 可操作路径与真实范围

普通账号登录本机首页，展开平台/范围选项，选择“仅目录分析，不请求商品详情”，输入 `https://shopeff.org` → 开始分析 → 原进度页 → 原worker目录服务实际联网 → 自动打开竞品店铺报告。原默认“目录与公开报价”保持；已保存目录可通过明确完整范围POST升级，新任务不覆盖旧报告。报告页刷新保留本次目录范围，GET不采集。

负责人在全新隔离SQLite/一个普通非staff非superuser账号上实际操作：首页输入产生scan1，原 `run_store_discovery` 使用原安全transport读取真实robots与sitemap，2026-10-22 02:07:19 UTC前后完成45条商品目录，无截断；未请求任何商品HTML/cart。并非把High样本导入库、旧历史回放或合成响应。目录实际完成时间以私有LIVE_WEB_DIRECTORY_RECEIPT为准；页面显示北京时间10:07:19。新增45条目录保存在StoreDiscovery.products，未创建Product/Snapshot/价格job/报价观测或管理员。

报告真实展示45商品来源链接和125标题词条；sticker筛选12件，占本目录26.7%，关系树SVG实际生成。该比例是标题词覆盖，不是销量、官方类目或市场趋势。桌面1280/手机390整页宽度均与视口相同，850宽表仅容器横向滚动；空筛选仍保留45目录分母，未知价格不填0。普通登录、手机菜单、退出、关tab与viewport恢复通过，QA8006已核cwd/命令TERM停止，库/普通QA凭据/截图均私有保留。

## 来源、署名和失败边界

EFF官方版权页 https://www.eff.org/copyright 和正式商店自身“Copyright (CC BY)”页脚相互对应；原店链接和正常迁移证明规范域名身份。报告明确署名Electronic Frontier Foundation并链接CC BY4.0，原作品/第三方和商标例外保留，不假定广泛商业再分发授权。High准确来源73fe10d533dccc7657dd3c879942a398f9a3f674，前置、各源停止和完整限制见LIVE_EFF_SOURCE_20261022.md及MILESTONE_LIVE_SOURCE_20261022.md。

High在01:55:08 UTC读取单商品HTML遇到429后停止；Retry-After和挑战信息未记录，不能写成不存在或声称已验证冷却。负责人不重试该HTML/另一商品、不切身份/工具/代理/DNS/TLS，也不从其他页面提取被拒报价；另一次独立Web仅目录获取使用未被拒robots/sitemap。未来持续可用性、商品字段及完整报价链路仍须验证，不以目录45条代替。

## 准确源码与质量

- Medium覆盖源5bb617990fa6dbfa586b980131bba4ac8187d964，53受影响回归通过；负责人该源隔离PG597项110.399秒无skip。
- 负责人目录模式初源5afec5d309e81437c714574700ec621feb79c856，36受影响回归及PG604项110.503秒无skip。上述实际浏览器/联网是在该业务源，后续仅修范围切换兼容，目录行为保持。
- Medium独立发现已完成纯目录无法升级P2；52da799初修虽静态关闭，但负责人35专项与PG606项均发现旧POST省略scope缓存复用回归，失败日志完整保留，未启用失败源。
- 最终业务d702e5328d2ce6abdb7422b3a5f0675313ad0b36区分scope显式True/False与旧None，修复升级并保留旧调用兼容。Medium该准确增量只读复核关闭P2/默认兼容，无剩余可复现P1/P2。最终独立随机隔离PG607项108.690秒无skip，测试库已销毁，Node/PG并发执行；check/迁移/diff通过。无模型、迁移、路由、依赖、worker/transport或利润数学变化。

私有证据位于 `.local/milestone-live-review-20261022/.local/`：live-web-source/LIVE_WEB_DIRECTORY_RECEIPT.json与原始响应、ui/BROWSER_ACCEPTANCE.json及真实截图、EXPLICIT_SCOPE_FINAL_FULL_PG_RECEIPT.json及日志、此前所有失败日志、MAIN_PRE_READONLY/MAIN_POST_READONLY；0700/0600。原主账号/凭据/44b99b5及全部旧成果保留。集成/运行/远端状态只以最新HANDOFF和私有DELIVERY_RECEIPT为准，本文不提前声明远端已合并或本机已重启。

## 本机启用回执

业务集成0c7fe9b于本轮已标准冷启动启用，session1733/主管3010/web3021/唯一worker3025；维护前重新核PID/cwd/命令。迁移无新/check清，登录200CSRF、匿名guide/正确研究比较302；主库21表268行前后强制只读指纹相同。QA8006已停。远端PR/CI/新main合并尚未进行，后续按最新交接发布；不把本机启用等同远端合并。
