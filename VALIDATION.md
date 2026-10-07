# 第一版验证记录

验证日期：2026-10-07。运行环境：Python 3.12、SQLite、Linux；浏览器为无头 Chromium。

## 已通过

- `bash scripts/setup.sh`：固定版本依赖安装、迁移、系统检查；重复执行无额外迁移。
- `python manage.py test`：25 项业务测试实际执行并全部通过，包括导入事务、幂等性、权限、CSRF、币种隔离、任务执行与恢复、利润计算。
- `makemigrations --check --dry-run`：模型与迁移一致。
- `pip check`：依赖无冲突。
- 安装后真实 HTTP 登录、商品详情、导入页面、利润工具、CSV 导出和本地静态资源响应正确。
- 浏览器验证：登录、7 点 ECharts 图表、实际 worker 的任务失败反馈与自动刷新、HTMX 利润计算及错误提示、CSV 上传和下载。
- 浏览器手机宽度 390px 检查：页面无横向溢出，表格在容器内横向滚动；上述流程无 JavaScript 页面错误。
- `seed_demo` 重复执行保持 3 个示例商品 / 21 条示例快照（另行导入 CSV 样例会增加标记为 demo 的商品）。
- ECharts 与 HTMX 静态资源已按 npm 注册表 integrity 校验，资源和许可证纳入仓库。

## 未通过或未验证的范围

- 实际速卖通网站访问：当前代理返回 403，表现为 HTTPX `ProxyError`；已经保存所需网络域名到环境配置草稿，保存草稿不代表运行网络已生效。
- 有效速卖通商品的真实价格采集：未验证。JSON-LD 解析与下载流程已用受控 HTTP 响应测试，不等同于实站成功。
- 生产部署：未执行。开发配置运行 `check --deploy` 会产生 DEBUG、开发密钥、HTTPS Cookie 等预期警告；README 已说明正式部署要求。
- Windows：已提供对应命令，未在 Windows 上执行。
- GitHub Actions：已添加自动检查工作流，本记录仅证明本机检查结果，远程结果以 GitHub 实际运行记录为准。
