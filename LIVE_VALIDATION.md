# 真实网站验证（2026-10-07）

## Shopify

店铺：https://lilygo.cc/
商品：https://lilygo.cc/products/display-accessories?variant=44121135120565

独立真实公开接口测试已返回 Display Accessories，规格 T5 e-Paper / Basic Screen，variant 44121135120565，价格 21.43 USD；销量、评分和评价数均未提供。这一结果不是测试夹具。

本地首页提交分析后创建 product=2，job=2；实际后台接口限流，尊重 Retry-After 等待 60 秒并重试一次后仍失败，没有保存快照。随后修正接口请求参数：variant 只用于返回数据中的规格选择，不发送给 cart.js 或商品目录 JSON，currency/country 仍保留。job=3 用修正后的实际任务执行路径继续验证。任务最终结果见下方补记。

Kith 公开商品接口也出现 HTTP 429；LILYGO 全店 products.json 目录请求同样限流。因此不能把单商品接口的成功读取宣称为稳定的全店分析。网站店铺研究仅汇总用户跟踪样本。

## AliExpress

TEM Laser 官网 https://tem-laser.com/pages/contact 链接至卖家 https://temlaser01.aliexpress.com/store/709547 。只读请求返回 HTTP 302，没有跟随跳转，未获得商品数据。

商品 https://www.aliexpress.com/item/32922106384.html 返回访问验证 HTML，没有公开商品数据；浏览器安全策略禁止进入验证页，未绕过。该旧商品链接是否仍在售无法确认，也不能归到 TEM Laser 店铺。已加入验证页检测，失败不写入快照。官方接口仍需申请，见 ALIEXPRESS_API.md。

## 功能验证

71 项 Django 测试覆盖利润计算、币种与汇率、平台工作流、规格与商品身份、DNS/私网防护、Cookie、错误处理等。Django check 与迁移一致性检查通过。

浏览器验证利润工具：销售 USD 100，折扣 10%，1 USD = 7 CNY，采购 200、运费 30、广告 20、其他 10、固定支付费 2 CNY，平台费 5%、支付费 3%。净利润 317.60 CNY（45.37 USD），利润率 50.41%，ROI 101.66%，保本成交价 40.69 USD，目标利润率 20% 的成交价 51.99 USD。切换币种会清空跨币种汇率并提示旧结果待更新，同币种汇率固定为 1。

## 最终补记

job=3 于 19:04:52 结束，仍返回 HTTP 429；实际数据库没有该商品快照。本次 Shopify 商品解析有真实成功证据，但当前完整后台采集受到限流，未跑通稳定入库。未更换身份、绕过验证或填入伪造数据。

## 后续目录发现验证

19:14 LILYGO 的公开 robots/sitemap 请求成功，保存 100 个商品链接。19:18 浏览器在店铺研究页提交 TEM Laser 首页，真实 worker 完成 robots/sitemap 发现并保存 100 个商品链接。两次目录均标记截取，价格快照不受影响；这些数据不是夹具。

TEM 第一个目录商品公开价格 JSON 请求仍限流，尊重等待后失败，未建立虚假价格记录。目录成功不能代替价格或销量验证。

本机执行结果：PostgreSQL 17.11 已初始化并运行于 127.0.0.1:55432，数据逐项迁移校验一致。78 项测试在 PostgreSQL 上通过；浏览器原登录会话和两家目录页面正常。原 SQLite 库及受限权限导出保留。

## Millys 首页识别修复

工作台新增自动识别链接：Shopify 店铺首页进入目录发现，商品详情进入价格采集；原先仅接受商品 /products/ 路径导致首页被拒绝。实测 https://millys.co.uk/ 的 robots/sitemap 返回 47 个商品链接，本次未触发 100 件截取。81 项 PostgreSQL 测试通过，涵盖首页自动/手动平台路由、去重、规格保留和本地地址拒绝。目录发现仍不等于价格/销量采集。

## 2026-10-07：第一步，小批量真实公开价格

用户要求分步开发。目录页新增前 10 件公开报价采集，遵守 robots 和请求间隔，支持 ProductGroup 多规格价格区间；HTTP 拒绝/限流停止批次并保留已取得的数据。

Millys 前 10 件真实商品已全部取得 GBP 报价并保存到 PostgreSQL。Facial Wash 为 GBP 12.00–38.00；Non-Drip Pump 为 GBP 6.00；四款 Cologne 为 GBP 9.00 且标注缺货。其余 37 件价格尚未采集。网页价格不代表成交价、完整库存或销量。

全套 PostgreSQL 测试 88 项通过，系统检查与迁移一致性通过。浏览器确认 `/stores/` 报价表与任务成功进度。续接日志：DEVELOPMENT_LOG.md；截图：`.local/validation-prices-step1.png`。

## 2026-10-07：价格续采完成

Millys 剩余 37 件均成功取得公开报价，目录累计价格覆盖 **47 / 47**，采集问题 0。新增 37 条独立历史报价，已通过浏览器验证覆盖率和最近历史列表。UI 支持下一批、连续续采、问题重试和重新观测，所有报价仍为原币种的公开报价范围。

本轮全套 PostgreSQL 测试 91 项通过。截图 `.local/validation-prices-complete.png`。下一阶段为真实商品词条统计与分类树；评论和销量尚未取得。

## 2026-10-07：标题词条与关系树

Millys 47 件真实商品标题统计为 75 个词条；shampoo 覆盖 18 件（38.3%），cologne 覆盖 12 件（25.5%）。页面提供词条/币种筛选，以及每件商品出现一次的“店铺→标题词条→商品”SVG 关系树。分组是标题频率规则，不是官方分类或市场搜索量。

浏览器点击 cologne 树节点筛出 12 件；点击 Baby Powder Cologne 商品节点高亮 GBP 9.00 的报价记录。95 项 PostgreSQL 测试全部通过，检查与迁移一致性通过。截图保存为 `.local/validation-keywords-tree.png`。

## 2026-10-07：商品评价基础检查点

真实读取 Millys Shampoo 公开页面并复查 Cologne HTML：没有商品 aggregateRating/review，REVIEWS.io 轮播为 SKU 为空的公司/商品混合评价，不能归属当前商品。新增商品结构化评价解析，区分评分、评分人数、评价数和最多 10 条评论样本，保护未知值并排除明确其他商品/店铺评论。已接入后续价格采集；尚未取得 Millys 的明确商品评论、未完成评价 UI 或主题分析。

全套 PostgreSQL 回归 **100 项通过**，系统和迁移一致性通过。续接步骤已保存到 DEVELOPMENT_LOG.md，额度恢复后先找明确商品专属评价样本。

## 2026-10-07：商品详情报告

浏览器从词条研究列表进入 Blueberry and Vanilla Cologne 详情，显示 GBP 9.00、缺货、报价观测时间与来源；评分、评价数和评分人数均为“尚未取得”，评论样本为 0。标题词条 blueberry/cologne/vanilla 可返回研究筛选，历史记录显示已有真实公开报价。尚无真实商品评论，不生成评价主题。

相关 PostgreSQL 测试 11 项通过；截图 `.local/validation-product-report.png`。商品图片、描述和规格尚待下一步接入。

## 2026-10-07 23:13–23:18：公开商品内容与商品专属评价

通过正常页面提交和 worker，Beardbrand 3 件验证样本全部成功保存。Beard Comb 为 USD 19–21、2 条规格、4.72/5、805 条评价、7 条可归属评论样本；Fox Hunt 为 USD 50、4.81/5、26 条评价、7 条样本；Short Game 为 USD 50、4.74/5、35 条评价、7 条样本。汇总是目标商品 JSON-LD，样本来自公开商品页内嵌 Judge.me，每条评论必须匹配商品 URL。评分人数没有提供，保持未知；样本不是全量评论。

Millys Blueberry and Plum Shampoo 单件更新成功，500ml GBP 15、5L GBP 50，图片放在 ProductGroup 规格节点，兼容后已取得两张图片。Millys 商品评价仍未取得。未将被重定向到品类页的旧商品链接当作可采集商品；Death Wish 的 robots 403，未继续请求商品。

全套 PostgreSQL 测试 108 项通过，商品组图片兼容随后 4 项针对测试通过。浏览器验收图片、原描述、规格链接、评价样本与单件更新。截图 `.local/validation-product-rich.png`、`.local/validation-product-reviews.png`、`.local/validation-millys-rich.png`。

## 2026-10-08：筛选分布与随机三店六商品

随机种子 20261008，从已有目录抽到 Millys、Beardbrand、Occam，各两件。Millys GBP 9 / 15–50；Beardbrand USD 50 / 19–21；Occam GBP 60 / 90。六件最终全部取得真实公开报价、图片、描述及公开规格，分别保存独立报价历史。Beardbrand 两件各有 7 条明确商品评论，评分 4.81/4.72、评价数 26/806；其他四件商品评价保持未知。

Occam 首次两件失败，发现 Product 身份缺失而 Offer 含链接，已增加唯一匹配 canonical 加全部报价 URL 校验的回退；通过网站重试后 2/2 成功。不能用规范链接覆盖显式不匹配的商品身份。六个详情页逐件核对标题与报价。

浏览器评分阈值 4.8 留下 Fox Hunt；Millys cologne、GBP 上限 10 留下 9 件（GBP 7.80 一件、GBP 9 八件），分布图一致；Occam GBP 下限 70 留下 GBP 90 商品。最终全套 PostgreSQL 114 项测试通过，迁移无变化。截图 `.local/validation-research-filters.png`、`.local/validation-random-stores.png`。抽样不代表全店或全平台数据覆盖。

## 2026-10-08：跨店研究与公开报价比较

5 家样本店铺的最新目录共 314 件商品，其中 52 件有有效公开报价，商品研究支持跨店筛选、排序和每页 50 件分页。浏览器验证同页勾选：USD Beard Comb 与 GBP Occam Jumper 被禁止直接比较；GBP Occam Jumper（60）与 Millys Shampoo（15–50）生成正确上下限图、库存与来源表。此组合只作功能验证，不作为相似产品或市场结论。未知评分/评价数明确保留。全套 PostgreSQL 119 项通过，无新迁移。截图 `.local/validation-catalog-comparison.png`。


## 2026-10-08：评论样本分析验证

Beard Comb scan 6/index 0 的 7 条明确商品评论均为 5 分，love/pull 各覆盖 2 条（28.6%）。本地规则仍提取到 1 条尺寸偏小与效果不足，并保留原评论证据；正面表述含品质肯定 1、使用顺滑 2、便携 1。浏览器词条展开及原评论锚点定位通过；Millys scan 4/index 9 无样本时不生成分析。全套 123 项通过，否定语句补充后 4 项专项通过。最多 10 条的小样本统计，不代表全部评价或完整质量判断。截图 `.local/validation-review-analysis.png`。


## 2026-10-08：库存、评论覆盖与导出

浏览器「有货 + 有有效评论样本」筛出 Beardbrand 3 件，各 7 条样本；真实下载 CSV 共 3 行，标题、库存与样本覆盖逐项一致。「缺货 + 无有效评论样本」共 18 件，包括 Occam 两件 GBP 60/90 与 Millys 16 件。仅验证已保存数据，无新的外站请求。全套 PostgreSQL 125 项通过，无新迁移。截图 `.local/validation-research-coverage.png`。


## 2026-10-08：候选清单实际验证

浏览器从 Beard Comb 报告加入收藏，保存重点关注状态和功能验证备注，移出后恢复仍完整保留。再从商品研究加入 Fox Hunt，候选清单勾选对比正确得到 USD 19–21 / 50、库存和公开评价来源。仅验证流程，未推断商品相似性。浏览器旧 CSS 缓存通过资源版本标记修复并视觉确认。131 项 PostgreSQL 回归通过，迁移 0006 已应用。截图 `.local/validation-candidate-list.png`。当前 admin 清单中保留这两件验证收藏，可正常移出。


## 2026-10-08：新版界面与首页到报告

实际浏览器：首页输入 Millys 首页后直接进入该店铺报告；Beard Comb 链接直接进入已保存商品报告。高级评论覆盖筛选返回 3 件，非法价格条件显示币种错误；价格分布导航展开折叠分析区且真实 GBP 47 件 SVG 图正常。已有 LILYGO 失败任务展示限流原因，未重试外站。手机 390×844 菜单展开与首页验证，修复文字对比度，随后恢复默认视口。新店铺自动首批 10 件流程用测试数据库/mock 验证，未新增真实抓取。全套 136 项通过，末次 20 项专项通过。截图 `.local/validation-ui-home.png`、`.local/validation-ui-mobile.png`。


## 2026-10-08：报价历史模块真实验证

Beard Comb 正常刷新两次，job #11/#12 成功，独立观测 #49/#50 都为 USD 19–21，并保存相同两条公开规格身份。历史共 4 次观测，只有新两次可比较，边界变化 0.00；旧观测因缺少规格依据仅画点。没有模拟真实店铺涨跌。Occam scan 5/index 0 无记录时显示空状态。手机 390×844 页面不溢出，记录表内部可横向滚动，恢复默认视口。全套 141 项通过，末次专项 5 项通过。迁移 0008 已应用。截图 `.local/validation-price-history.png`、`.local/validation-price-history-mobile.png`。

## 2026-10-08 定时价格监测实站验证

浏览器从 /stores/6/products/0/ 创建 Beard Comb 每日计划 #1，后台自动任务 #13 保存观测 #51（10:11:51 CST，USD 19.00–21.00），并非手动更新商品。暂停显示已暂停且无下次执行；恢复任务 #14 保存 #52（10:12:20 CST，同报价）。计划最终启用，下次 2026-10-09 10:12 CST。新记录带实际规格范围，旧记录保留。桌面/手机截图 /tmp/shophot-price-monitoring{,-mobile}.png，全套 147 项通过。尚未等待一天验证真实长周期第二轮；本地采集进程停止期间不会采集。

## 2026-10-08 样本市场看板

从跨店商品研究点击“样本市场分析”进入 /research/market/，实库读取 5 家最新目录/314 个去重商品，52 个报价（GBP49/USD3），3 个具有评价数和公开评论样本的商品；报价均在近 24 小时（兼容旧 UTC 时间格式）。USD 19–25.20 链接筛出 Beard Comb，Millys 店铺筛选 47 件/47 个报价，品牌 Milly's 筛出 3 件；无匹配结果提示正确。页面不排队、不采集，本轮未对外部店铺新增请求。手机390×844页面宽390、图宽312，桌面图表SVG正常、控制台无错误。全套152项通过，末次6项金额边界/时间/联动专项通过。截图 /tmp/shophot-sample-market.png 和 /tmp/shophot-sample-market-mobile.png，.local 同名验证副本。

## 2026-10-08 非Shopify平台验收

7条实际样本HTTP与浏览器测试见CROSS_PLATFORM_VALIDATION.md：OTTO两卖家单品浏览器可见公开价格，HTTP400尚未进入报告；SHEIN两入口人工验证；Ozon两店铺平台连接错误；速卖通店铺验证，当前无店铺目录支持。没有新增非Shopify成功观测。修复平台误识别后首页实测未接入提示，156项测试通过。
