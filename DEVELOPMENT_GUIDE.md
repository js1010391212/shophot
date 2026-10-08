# ShopHot 按模块开发指南

当前架构为 Django + PostgreSQL、服务端模板、少量原生 JavaScript 与 ECharts。先逐模块完善现有流程，避免同时更换框架、采集方式和界面。

## 模块地图

| 模块 | 服务 / 数据 | 页面与交互 | 主要验证 |
| --- | --- | --- | --- |
| 商品页面文件导入 | `page_import.py` / `structured_page.py` / `page_import_forms.py`；复用 Product / Snapshot；`otto.py` 保留链接规范化 | `page_import_views.py` / `page_import{,_start}.html`；首页、失败页、商品报告入口；旧 OTTO URL/表单兼容 | `test_page_import.py` / `test_otto.py`；身份/规格/未知值、签名归属与过期、CSRF、历史保护；真实文件兼容性待验收 |
| 平台识别与验收 | `platforms.py`；`AnalyzeForm`；只读 `scripts/validate_platform_samples.py` | 首页与现有分析表单明确提示未接入平台 | `test_platforms.py`，真实域名/边界、兼容、不误排队；实站见 CROSS_PLATFORM_VALIDATION.md |
| 分析流程 | `workflows.py`、`jobs.py`；StoreDiscovery / CollectionJob | `workflow_views.py`、`workflow.html`、`workflow.js` | `test_workflows.py`，输入到报告、空目录、失败、重试、重复任务 |
| 店铺发现与公开采集 | `discovery.py`、`network.py`、`shopify.py`、`collectors.py`、`catalog_prices.py`、`catalog_content.py`、`reviews.py` | 采集任务与商品报告 | 对应 discovery/shopify/catalog/reviews 测试，来源归属与请求边界 |
| 商品研究 | `research.py`、`catalog_research.py` | `research.html`、`catalog_market.html`、`catalog_compare.html`、相关图表 JS | 筛选、排序、原商品身份、币种、导出 |
| 样本市场分析 | `sample_market.py`，复用最新目录与商品研究行 | `sample_market_views.py`、`sample_market_forms.py`、`sample_market.html`、`sample_market.js` | `test_sample_market.py`，币种隔离、去重、价格段联动、覆盖分母与新鲜度 |
| 目录报价历史分析 | `price_history.py`；CatalogPriceObservation / quote_scope | `price_history_views.py`、`price_history_forms.py`、`price_history.html`、`price_history.js` | `test_price_history.py`，跨目录、币种、规格条件、零基准、旧记录与失败 |
| 定时价格监测 | `price_monitoring.py`；PriceMonitor / StorePriceJob，现有 worker 调度 | `price_monitoring_views.py`、`price_monitoring_forms.py`、监测清单/设置模板 | `test_price_monitoring.py`，到期、共享队列、目录重排、归属、暂停恢复、失败退避与历史保留 |
| 评论分析与观测历史 | `review_analysis.py` / `product_reviews.py` / ProductReviewBatch；复用 Snapshot 与已有目录样本 | `product_review_forms.py` / `product_review_views.py` / `product_reviews.html`；导入预览与商品报告入口；复用 review_analysis 图表 | `test_product_reviews.py` / `test_review_analysis.py` / `test_reviews.py`；归属/去重/历史/证据/未知/否定/目录复用 |
| 候选清单 | `candidates.py`；CatalogCandidate | 清单/编辑模板；现有候选视图下一次修改时可迁出 `views.py` | `test_candidates.py`，归属、重复、恢复、跨目录关联 |
| 利润工具 | `profit.py`、ProfitForm | `profit.html`、`profit.js` | `test_profit.py`，币种与手动汇率、费用和保本 |
| 公共界面 | `ui.css`、`ui.js`、`base.html`、`partials/navigation.html`、`partials/research_filters.html` | 导航、布局、表单层级、手机菜单 | 浏览器桌面/移动及键盘验证 |
| 跟踪价格历史与导入 | Product / Snapshot、`importing.py`、现有视图 | 商品跟踪报告、导入、历史对比 | `tests.py`，快照顺序、导入原子性、CSV 安全 |

所有 Python 路径相对 `market/`，模板相对 `market/templates/market/`，资源相对 `market/static/market/`。模型暂时集中在 `models.py`，路由集中在 `urls.py`，迁移集中在 `migrations/`。

## 新模块的落地步骤

1. 写清用户入口、主要结果、数据来源、失败与空状态，明确本次范围。
2. 检查是否已有同类模型和服务。明确模块如何调用其他模块，保留商品链接与币种等稳定身份。
3. 先实现服务，再接视图与路由；新增模块使用 `<module>.py` 与 `<module>_views.py`，避免扩大历史 `views.py`。较大模块再提升为包，不预先拆空目录。
4. 模板复用公共导航、筛选组件和 UI 样式。领域规则留在服务中，JavaScript 负责交互，不重复实现统计规则。
5. 测试需要保护的行为：正确路径、未知值、非法输入、权限/CSRF、重复或重试及与现有数据兼容。不要仅断言模板长得像代码。
6. 实际浏览器确认结果、失败状态和手机布局；适当保存截图。模型变化检查迁移，公共逻辑变化跑全套。
7. 更新开发日志、用户文档与续接入口，说明已完成与仍有限制的部分。功能完成后再提交或交付，遵循用户授权。

## 主流程约定

首页优先一个网址输入框，默认自动识别。已保存报告可直接打开，但明确保存时间与更新入口；新店铺发现目录后采集首批最多 10 件，进度页轮询只读接口，完成后进入该店铺报告。其他商品显示采集进度，成功进入报告，失败显示原因与重试。

报告先让用户看到商品和报价，再提供高级筛选、词条树和价格分布。候选清单用于记录研究判断；数据管理入口为辅助，不要求用户在侧栏完成每一步。尚未接入的数据或缺失评价直接说明，不能通过 UI 填入假结论。

## 本地验证

```sh
bash scripts/start.sh
.venv/bin/python manage.py test market.test_workflows --noinput
.venv/bin/python manage.py test --noinput
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
git diff --check
```

服务为 `127.0.0.1:8000`，PostgreSQL 配置及启动见 `DATABASE.md`。测试使用单独测试数据库。开发进程采用 `--noreload`，更改 Python 或缓存模板后需重启；不要启动多个 worker。更新静态资源时更改相应版本标记，避免界面仍使用旧缓存。
