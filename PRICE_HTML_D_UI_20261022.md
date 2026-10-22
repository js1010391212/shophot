# PRICE-HTML-D：详情失败状态的来源展示范围

基线 `586ed523d65cbabc3b7d1c8bb1eef264d2bfc2b7`，独立 clone `.local/price-html-d-ui-20261022`，分支 `codex/price-html-d-ui-20261022`。本轮无联网、真实库/凭据读取写入、浏览器/服务操作或新依赖。

## 改动

详情视图使用既有 Adafruit exact-root 和 strict-product normalizer，独立计算展示范围。规范来源目录中未尝试/报价失败的条目也显示仅事实范围；显式 facts_only 继续兼容。该布尔值仅模板上下文，绝不回写目录、补 SKU/价格或创建事实数据。其他域名、别名、参数、片段及 API 路径不自动继承来源标记。

图片/描述分支优先遵守展示范围；评价区明确不采集/保存评论，不再显示可通过更新取得公开评论的通用提示。刷新 POST 保持原排队逻辑，只让成功通知匹配来源范围；其他来源原通知不变。未改采集、parser、身份函数、model、迁移、worker 或路由。

## 验证及限制

独立本地 settings 不导入 config.settings，固定显式 clone 内 SQLite 测试库；普通临时用户由 TestCase 回滚，无持久 QA 账号。新 4 项回归（含子案例）覆盖无报价/失败/成功、GET 不改变产品数据和无任务观测、严格来源边界、刷新通知与普通源兼容。连同原 adapter dispatch/content 共 22 项通过，0.375秒，无 skip；Django check、迁移一致性、diff check 通过。私有日志 `.local/targeted-tests.log`。

未重跑未变 634 全套，不联网重取任何页面。负责人在自己的 QA8007 做真实失败项目桌面/手机截图及最终集成；本队未碰用户 main 登录 tab，也未称已部署或实站验收完成。本轮完成冻结后停止。
