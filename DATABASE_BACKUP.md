# 本机 PostgreSQL 备份与隔离恢复验证

本工具仅维护ShopHot现有本机PostgreSQL17，不是生产灾备方案。备份含账号、会话、私有报价等敏感数据，必须保护；归档不提交Git、不上传公共服务。真实备份与隔离恢复必须由负责人执行并记录结果，不能把模拟测试通过当备份演练已完成。

## 使用范围

在项目已启动的本机PG上，由负责人执行：

```sh
.venv/bin/python scripts/backup_database.py
```

不接受DSN、归档路径、恢复库名或额外参数；非法参数只给通用错误，不回显其中的秘密。不安装依赖，使用已有psycopg及固定 `/usr/local/opt/postgresql@17/bin` 的pg_dump/pg_restore。读取本项目 `.local/database.json`，只允许postgresql、127.0.0.1:55432、shophot库和shophot用户以及固定字段；不使用环境回退、远端/其它库、任意options。若父进程存在PG*环境变量则失败，不借此重定向连接。子工具环境单独构造，密码只进内存及受控进程环境，不进argv、报告、stdout/stderr。

`.local`和`.local/backups`必须当前用户所有、0700且非symlink；配置文件须0600普通文件。归档随机唯一、O_EXCL/O_NOFOLLOW创建0600，不能覆盖已存在文件或链接。pg_dump写已打开的文件描述符，pg_restore读同一描述符，避免因重新打开路径读取替换文件。未完成归档仅在当前路径仍是本轮inode时删除，不能误删后来替换的文件；完整归档在恢复失败时保留。

## 在线一致性与检查

源连接只读repeatable-read事务，固定TimeZone UTC、DateStyle ISO/YMD和浮点输出；列public普通表并取得ACCESS SHARE锁，再导出快照。指纹与pg_dump共享该快照，源事务持续到dump完成。这允许普通DML继续，但DDL可能等待或使维护失败；维护时应避免同时变更数据库结构。连接10秒、SQL120秒/锁5秒、各工具300秒、流式指纹阶段有截止时间。长事务会延长旧版本保留，工具不运行定时或常驻任务。

依据[PostgreSQL17快照同步说明](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION)，导出事务结束后快照不能继续导入；依据[pg_dump文档](https://www.postgresql.org/docs/17/app-pgdump.html)，通过--snapshot使用共同视图。归档custom格式/no-owner/no-acl；custom格式中的dump no-owner不能代替restore阶段的no-owner，restore参数必须保留。

逐表使用ONLY排除继承重复读，按to_jsonb(row)::text COLLATE C排序，服务端游标每批256行，流式计算规范化UTF8内容长度分帧SHA256和行数。不输出行内容/表名或会话值，不把全部数据装入Python内存。源和目标使用相同转换、排序及时区口径，比较表集合、每表数量和内容指纹；不因为物理行顺序变化误报。

本轮逐项内容核验范围为public普通表。遇其它业务schema、partition/foreign/materialized/view表或大对象，明确拒绝，不用public比对冒充全部数据库验证。归档结构/约束由pg_restore执行检查；表指纹不证明全局角色、外部程序、配置密钥、TLS环境、外部文件、序列并发状态或跨数据库一致性。官方pg_dump不是集群全局对象备份，本工具也不创建角色/修改源库。

## 隔离恢复与清理

只创建随机 `shophot_restore_verify_<本轮uuid>` 的新库，从template0开始。只有CREATE DATABASE明确成功才获得本轮清理资格；明确重复库返回not_created；若CREATE期间连接断开或超时而无法确认结果，则返回creation_unconfirmed，可能已经留下本轮随机库，须负责人按归档uuid核查，不能将此状态当确认库不存在。没有获得清理资格时绝不尝试DROP同名库。pg_restore仅写该新库，--exit-on-error/--single-transaction/--no-owner/--no-acl，不使用--create或覆盖目标，参数依据[PostgreSQL17 pg_restore文档](https://www.postgresql.org/docs/17/app-pgrestore.html)。验证连接再次只读。

成功或失败后只清理本轮确知新建的库，不drop源库/其它库，不FORCE或终止别人连接。cleanup失败报告status=failed及cleanup=failed，完整archive保留；隔离库残留必须负责人核查，不能把有残留的运行称验收成功。残留名可从本轮归档文件uuid对应上述固定前缀核对，但不要手工猜测或批量删除。工具异常原stderr抑制，JSON只安全阶段/状态、相对归档路径、总表/行数、时间和archive hash；不会列真实数据或密码。

本工具不自动恢复shophot原库、不关闭网页/worker、不迁移业务、不替代备份保留策略/异地副本/生产灾备。恢复原库或异地备份须另行准备明确方案，不能顺手把隔离验证改为覆盖业务库。

## 验证与交付

```sh
SHOPHOT_DB_ENGINE=sqlite .venv/bin/python manage.py test config.test_database_backup --noinput
```

SimpleTestCase mock回归不会连接真实数据库、启动PG或调用真实工具；检查只读快照/明确连接、私密路径/已有文件碰撞、tool超时、create失败不清理、restore失败完整归档保留、内容差异、清理失败、排序/重复行与命令不回显秘密。实际备份、权限和恢复演练由负责人独立完成并记录，不重复应用全套。维护源码与业务模块隔离，没有Web、路由、模型、迁移、worker、定时器或云存储。


## 2026-10-09 负责人实际恢复演练

准确源码d3a3e2c3dedf8d14c0f04f2bc2bb616a4c40096a，负责人独立审查clone8f56375。14项模拟回归0.097秒、Django check、迁移一致性与diff检查通过。以现有本机业务库只读导出快照，实际归档与随机隔离新库恢复在0.863秒内完成：20张普通表、203条记录的逐表数量和规范化内容SHA256完全一致，恢复进程成功退出，验证库清理后实际查到零残留。备份复制到项目根目录.local/backups，文件0600、目录0700，复制前后归档SHA256一致；私有验收收据在.local/database-backup-ui-20261009，不提交数据、配置或归档。网页、单采集worker与受保护个人入口保持原运行，没有源库写操作。

这一次证明当时的数据归档可恢复到隔离库，不代表后续新增记录已经备份，也不代表异地灾备、生产发布或原业务库覆盖恢复通过。高级已对准确冻结源只读审查无实质阻断；最终合并状态以最新HANDOFF与Git为准。
