# 个人临时HTTPS入口

本入口用于公司只有浏览器时的个人实测，独立于现有8000开发网页和单个采集worker。配置和测试通过不代表隧道已连接或公司已可访问。身份门禁、邮箱PIN、实际域名和外部验证由负责人处理；未核实认证保护前不要转发本项目。

## 运行资源

新增独立 `config.personal_access`、`config.personal_wsgi`、固定 `127.0.0.1:8003` 的Gunicorn配置和 `scripts/start_personal.py`。根settings/production/requirements均保持原策略；不运行迁移或另启采集worker。复用明确指定的项目本机PostgreSQL配置，只接受回环IP或显式Unix socket，本入口保留现有本机数据库连接方式，不关闭证书校验或覆盖TLS选项；远程生产DB仍用原production的verify-full，不能拿本入口接远端DB。

负责人在项目venv安装根依赖后，可另安装 `requirements-personal.txt`。本轮清单锁定Gunicorn26.2.0、WhiteNoise6.12.0，均Python>=3.10，已从官方[Gunicorn PyPI](https://pypi.org/project/gunicorn/26.2.0/)和[WhiteNoise PyPI](https://pypi.org/project/whitenoise/6.12.0/)核对。未在本地研发阶段安装。Gunicorn提供Unix/macOS WSGI，WhiteNoise在DEBUG=False时提供collectstatic输出，依据[Gunicorn设置说明](https://gunicorn.org/reference/settings/)与[WhiteNoise Django说明](https://whitenoise.readthedocs.io/en/stable/django.html?highlight=manifest_strict)。本轮不新增系统服务或购买。

## 私有运行配置

在项目 `.local` 创建权限0600、当前用户拥有的JSON文件，包含且只包含：

- `SHOPHOT_PERSONAL_ORIGIN`：负责人取得的精确 `https://主机名`，只一个，不含端口、路径、通配、查询、IP或登录信息。临时URL每次更换须更新此值并重启独立网页，不能使用星号回退。
- `SHOPHOT_PERSONAL_SECRET_KEY`：独立安全随机密钥，至少50字符；不复制开发密钥、不输出聊天或日志。
- `SHOPHOT_PERSONAL_DB_CONFIG`：已有项目 `.local/database.json` 的明确绝对路径。不复制数据库密码到新JSON；原文件只在启动配置中读取，内容从不打印。

不要把真实配置/邮箱/隧道令牌/密钥提交Git或放入命令行参数。配置缺失/权限开放/远端DB/无效origin均失败封闭。也可以仅在受控进程环境注入同名三变量以验证配置，官方启动脚本仍明确要求私有文件。

配置就绪且身份门禁已实测后，由负责人使用项目venv：

```sh
.venv/bin/python scripts/start_personal.py --config /绝对路径/项目/.local/personal-access.json
```

脚本验证配置与依赖→Django deploy check→collectstatic到独立 `.local/personal-static`→启动前台固定8003 WSGI。不会写业务记录、迁移、备份或启动worker；静态收集仅写项目静态目录。Gunicorn环境命令覆盖清空，固定配置不读取默认同名配置，日志关闭访问URL记录。错误只报告配置字段或一般原因，不回显值。

本机 macOS 已实际出现 Gunicorn 收到 HUP 后，子进程在请求时因 Objective-C fork 安全检查退出。更新个人网页时，先核实并正常终止本次8003的旧 master、确认端口释放，再用上面的启动脚本完整重启；不要用 HUP 更新此运行环境，也不要关闭系统 fork 安全检查。保留已认证保护的原隧道和8000单 worker，重启后重新核验静态资源、登录、CSRF及Host/proto门禁；若使用仅等待旧 master 的项目防休眠进程，按新 master 重新设置该项目进程。

## 代理边界和验证

- 只在本机8003接收代理，独立WSGI边界在Django和静态资源前校验REMOTE_ADDR为127.0.0.1/::1、Host精确匹配、X-Forwarded-Proto精确https；其它请求403，不能通过伪造外网proto绕过。直接启动 `config.wsgi` 或 `manage.py runserver` 不能代替这个受保护入口。
- provider必须保留真实Host、覆盖或清除客户端proto并传https；由负责人在未接业务数据的占位服务验证。额外X-Forwarded-Host/Port均不信任。原8000不启用本入口的代理信任。
- DEBUG=False；secure/HttpOnly会话、secure CSRF、SameSite Lax；独立cookie名避免干扰原网页。CSRF仍同源校验，无通配可信源；有效token同源POST通过、外源拒绝。网页仍要求Django正常登录，邮箱门禁不能代替账号认证。
- WhiteNoise只服务collectstatic输出、不从源finders或开发目录实时找文件；本机DB/JSON/日志不放静态目录。部署后实际验证CSS/JS、认证前拒绝访问、本人PIN→Django登录→报告/利润流程、未知Host/头拒绝，不能用合成测试代替真实外部访问。
- 本机电脑/PG/网络需保持可用。断网或睡眠会中断；临时URL不是长期稳定托管。停止时仅终止这次独立8003 PID和隧道，保留8000与已有worker。
- 公司浏览器的固定127.0.0.1:8000扩展指向公司本机，当前不能采集到家里实例；本轮未改扩展权限/接收地址，不承诺公司端扩展可采集。

## 本轮验证和未完成

`manage.py test config.test_personal_access config.test_production --noinput`：合成配置、缺配置失败、私有JSON权限、loopback数据库、代理门禁覆盖应用与静态路径、真实CSRF中间件及原生产策略专项。无真实DB、网络、服务；未安装新增依赖。实际WhiteNoise文件输出与Gunicorn进程/HTTPS认证/公司访问由负责人安装后统一验证。真实origin、邮箱/隧道状态不在本文件，不宣称已连接。


## 负责人集成验证（2026-10-09）

源9cdcdf7，负责人补57819af保留现本机数据库连接默认，不覆盖或关闭TLS策略。20项专项0.864秒及pip check通过，项目venv已按官方PyPI安装两依赖。实际独立Web启动deploy check无未静默告警，146静态文件收集；HTTP本机受控Host/proto验证login200、匿名利润302、CSS200、错误Host/proto403、无CSRF POST403、合法同源带CSRF token的无效账号返回普通登录错误200。没有业务fixture/迁移/新worker。实际Cloudflare QuickTunnel2026.10.0支持邮箱限制，未认证实际进入验证码门禁，已按用户明确邮箱授权发送一次登录码。PIN后远程应用与公司网络仍待用户自行验证，不能把本机HTTP边界检查冒充远端验收。实际临时URL/邮箱/私有运行配置与PID仅本对话及项目.local，禁止提交。原8000与固定本机扩展桥接保持可用；临时试用不等于稳定商业托管。
