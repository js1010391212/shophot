# 本机候选安装前置保护

准确业务基线仍PR23/main9ce4c556bd569fbea9620b7371a6a096fa63a182；三份候选说明源4d96a47d2c73e3712f04e5682cc1a8e7d5bc2607已冻结。最终普通账号1280/390闭环及当前21表主PG隔离恢复已通过，但源码候选包尚未认可可安装交付。

## 真实触发与范围

现README要求Python3.12+，本机默认python3为3.11.17。原setup直接python3 -m venv .venv，既有3.12环境上可能重写pyvenv.cfg却保留旧3.12 symlink。负责人一次安装命令cwd错误执行到根，已明确用可信3.12.15重新生成根虚拟环境配置，依赖仍Django5.2.18等原固定版本，主PG和服务原PID未写/未重启。旧root备用SQLite在该误操作中补了0004–0013迁移，当前状态私有保留，未回退；不会称为正确隔离安装。具体纠正收据仅.local/mvp-final-flow-20261013/SETUP_SCOPE_CORRECTION.json，不复制数据库或私有配置进源码包。

正确隔离clone的默认3.11安装曾报告anyio4.15.1不可得；官方PyPI页面及JSON证该版本存在，另以明确3.12的新venv和官方https://pypi.org/simple实际完成全部14项固定依赖安装。不同解释器/包源组合尚不可单凭这个结果推断原失败唯一原因；不降级requirements、不修改全局pip/pyenv/PATH，不关闭TLS或绕平台策略。

## 有界修复合同

- setup支持SHOPHOT_PYTHON显式可信可执行文件，版本探测和创建环境使用同一个解释器；最低版本与README3.12+一致。
- 在任何创建/修改.venv、安装依赖、迁移或check之前，先检测所选Python；不足/不可用给可见错误。
- 已有.venv的实际Python major/minor与所选不同，或环境损坏时，明确拒绝且不覆盖/清空/改库。不根据目录名或旧pyvenv.cfg字符串假装实际版本一致。
- 新环境继续按当前requirements固定版本安装，再migrate/check；不创建默认账号、密码或演示资料。官方包源例子仅命令范围，不改变全局配置/认证/网络保护。
- 只修改scripts/setup.sh、必要config/test_setup.py和README安装小段，其余三份说明保持冻结，不改应用/迁移/worker/计算/签名/数据。

本地medium新独立clone .local/mvp-install-guard-20261013 / codex/mvp-install-guard从4d96实现与无网络副作用回归；高级high独立clone只读合同和最终准确源码；负责人最终新隔离目录的真实安装/启动/登录基础烟测、精确发布和包内容核对。旧克隆/全部历史/私有文件保留，不在根环境再次试安装，不重复旧利润/预算470全套。只有固定依赖或共享业务实际变化才扩大相应回归。
