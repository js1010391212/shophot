# 竞品数据路线与验证

2026-10-07。当前不开发自己店铺的订单、上下架或官方卖家 API。

## 已实现并取得真实数据

Shopify 公开 robots.txt 与 sitemap 商品发现：后台排队，遵守 robots，限定同域 HTTPS、公网连接、单响应 2 MB、最多 3 个商品子地图和 100 个商品链接。每次结果保留独立时间、商品名称、链接和 sitemap lastmod。lastmod 是站点声明的修改时间，不是上架时间或实际销售时间。

LILYGO 店铺 https://lilygo.cc 的实际目录请求成功，保存 100 个商品链接，包括 T-Display、T-Zigbee。随后在浏览器提交 https://tem-laser.com，实际 worker 同样保存 100 个商品链接。扫描已标记截取；不能据此声称全店只有 100 件商品，或把未返回的商品认定为下架。目录结果不自动产生价格快照，也不虚构销量。

[Shopify 官方 sitemap 说明](https://help.shopify.com/en/manual/promoting-marketing/seo/find-site-map)确认公开 sitemap 包括商品等链接。价格采集另用商品公开 Ajax 接口；此前限流记录继续保留。

## 候选补充数据服务

- [Bright Data AliExpress 商品数据服务](https://brightdata.com/products/web-scraper/aliexpress)声称提供价格、规格、卖家、评价等字段，以及可购买的数据集。尚未注册、订购、调用或验证覆盖率。网页宣传和成功率不代表本项目实测。
- [Oxylabs 官方 Web Scraper API 仓库](https://github.com/oxylabs/web-scraper-api)列出 AliExpress 等专用来源。尚未取得授权数据样本，不能保证能分析指定店铺。
- [Similarweb 数据方法](https://support.similarweb.com/hc/en-us/articles/360001631538-Similarweb-Data-Methodology)说明其流量来自直接测量、匿名网络、合作和公开数据，经过建模估算。用于对外产品还需核实数据展示/再分发许可。

供应商评估应先取得获准使用的样本或历史数据集，检查目标店铺覆盖、更新时间、规格/国家/币种、重复与缺失、以及对外展示授权；不因页面访问验证就调用代理服务绕过安全拦截。当前没有集成这些服务，亦未产生费用。

## 继续积累

先通过公开目录发现商品，再观察确定规格的价格；后续增加目录差异、新品候选和长期调度。销量/营收若来自模型应标注估算、假设与范围，不作为真实订单。持续目录扫描的截断和请求失败必须排除在“下架”判断之外。

### Millys 评价来源验证（2026-10-07）

Cologne 与 Blueberry and Plum Shampoo 的商品结构化数据未提供明确 aggregateRating/review。Cologne 页面 REVIEWS.io 轮播配置包含公司和商品评价、SKU 为空；页面营销星星与“8,000+ happy customers”不作为当前商品的评分或评价数。后续只接受可归属目标商品的结构化评价或明确商品专属的公开来源，评分人数、评价数和采集样本数独立保存。

### Beardbrand 商品专属评价验证（2026-10-07 23:13）

[Beard Comb](https://www.beardbrand.com/products/beard-combs)、[Fox Hunt](https://www.beardbrand.com/products/fox-hunt-mens-cologne)、[Short Game](https://www.beardbrand.com/products/short-game-mens-cologne) 均遵守公开 robots 后返回 HTTP 200。目标 Product JSON-LD 提供五分制评分与 reviewCount；页面内嵌 Judge.me 评论有明确 data-product-url，可归属商品。每件取得 7 条页面公开样本，样本数不代表总评价数，未调用私有 API 或翻页收集全量评论。数据已通过正常采集队列保存到 PostgreSQL，并在商品报告显示来源与观测时间。此验证不代表其他所有店铺均能取得评价。
