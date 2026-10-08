# 本地 PostgreSQL 存储

选择 PostgreSQL 17：用于商品关系、采集任务、历史价格与 JSON 目录结果。SQLite 保留为零配置回退和原始备份，不继续作为本机实际运行主库。

通过 Homebrew 安装 `postgresql@17`，驱动 psycopg 3.2.13。项目采用独立数据库集群，数据与随机凭据保存在 Git 忽略的 `.local/`；权限限制为当前用户。仅监听 `127.0.0.1:55432`，SCRAM 密码认证，未创建系统开机启动项。

首次初始化（不覆盖既有目录）：

```bash
.venv/bin/python scripts/init_postgres.py
```

常规启动 `bash scripts/start.sh` 会启动此项目数据库，再迁移和启动网页/worker。数据库独立于网页进程，网页停止后仍保存数据。手动停止：

```bash
/usr/local/opt/postgresql@17/bin/pg_ctl -D "$PWD/.local/postgres" -w stop
```

`config/settings.py` 读取 `.local/database.json`；部署时 `SHOPHOT_DB_ENGINE/NAME/USER/PASSWORD/HOST/PORT` 环境变量覆盖配置。应用角色不是超级用户；本机测试需要 CREATEDB，用于临时测试数据库。部署角色可取消 CREATEDB。

迁移保留原 `db.sqlite3` 和 `.local` 内受限权限的备份及 Django 数据导出。备份包含账户和会话，不能上传 GitHub。该方案是本地开发数据库，尚未配置异地备份、灾备与生产部署。

首次切换时暂停网页/worker 后，运行 `.venv/bin/python scripts/migrate_to_postgres.py`：分别导出 SQLite 和导入后的 PostgreSQL 数据，逐项校验。目标业务表非空则停止，防止重复导入覆盖。恢复旧库可设置 `SHOPHOT_DB_ENGINE=sqlite`；新库配置与原库都保留。

本机执行结果：PostgreSQL 17.11 已初始化并运行于 127.0.0.1:55432，数据逐项迁移校验一致。78 项测试在 PostgreSQL 上通过；浏览器原登录会话和两家目录页面正常。原 SQLite 库及受限权限导出保留。
