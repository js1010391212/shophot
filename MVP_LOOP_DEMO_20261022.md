# 第二轮：目录报价到私有利润记录的隔离演示

本轮基线 `db71186f848bb69f8cee2f24eb484d28de9e4e38`，分支 `codex/round2-mvp-loop-20261022`；只在负责人指定的 `.local/round2-mvp-20261022` 独立克隆开发。源码提交 SHA 由交付回复和私有 `DELIVERY_RECEIPT.json` 固定，本文不写循环依赖自身的提交号。

## 已接通的范围

复用原首页、workflow、目录/历史、候选、物流/利润账本和私有记录，不增路由、数据模型或迁移，不改采集/worker、利润或预算计算公式。

- 新 `market/catalog_profit_references.py`：目录来源使用独立 `catalog=<CatalogPriceObservation.pk>`，可带 `candidate=<本账号候选.pk>`。不转换或伪造 Product/Snapshot；不与 observation/product/study 混用，不接收重复或非法编号。
- 只接受上下限相等、单个明确规格、可重建签名的完整 `quote_scope`。签名须与原采集服务重新生成结果完全一致，规格范围、多规格同价、无规格身份、市场参数冲突、旧无 scope 报价均拒绝。拒绝后可明确重建手填假设，不取范围最低价。
- 目录商品最近报价列表逐条给出可引用入口；候选使用最新一条历史观测，入口固定具体 id。最新观测不适合引用时不给旧报价自动替代，用户可从历史记录选择明确观测。候选归属/商品 URL/店铺不匹配拒绝。
- 来源事实只读展示：目录观测 id、原商品/规格 URL、币种/金额/观测时间、规格签名、SKU、候选 id。售价/采购/物流等依然为可修改的用户假设；收货国家、优惠和税运条件继续未知，不推断承运资格。
- Catalog 研究记录使用显式 version 2，source 保存完整 quote_scope、目录/job/candidate id、原报价和条件；无 snapshot_id。原手填/public product/browser observation 仍产生原 version 1，旧 v1 读取/继续/比较契约保留。
- 保存时同一事务锁账号、目录观测、对应目录和 job、必要的私有候选；重新解析并核对来源、物流和账本，不一致拒绝。记录不可变，重复 nonce 幂等；继续固定到原观测，之后新报价不替换旧引用。原观测被改动或删除时历史仍可读，继续/重新保存要求重选来源。
- 比较支持有效 v1 与 catalog v2，仍比较用户历史假设；原币种/汇率/数量和未知费用边界不变。来源 label 明确为目录公开页面历史观测。

## 数据与隔离边界

只读输入为负责人导出的 `PUBLIC_HISTORY_FIXTURE.json`，SHA256：

`c7cc6696981fde767a81c93ba565fea0de9f350350e04b7b3bba68654f3ae9ca`

副本导入本克隆 `.local/qa.sqlite3`，显式 QA settings 在任何 ORM 前断言当前目录、源码目录、SQLite 后端和数据库绝对路径，测试使用另一个 `.local/test-qa.sqlite3`。无主 PG 访问、无管理员、无平台 HTTP、无 worker；只建两个非 staff/non-superuser 普通 QA 用户。

Fixture 为 **1 个店铺目录（pk=6）、22 个报价任务、17 条观测**。Beardbrand 目录仅 3 个商品且 limited=True，不能称全店覆盖。Fox Hunt 观测 74/76/79/80 符合单规格条件，均 50 USD；39/45 无 scope，不能精确引用。Beard Comb 19–21 USD 范围应被拒绝。

推荐演示观测 **#80**，原观测北京时间 **2026-10-20 22:23:21.569448**；不是本轮新采集。规格 SKU `32836920`，原 URL 与 scope 以记录只读事实为准。既有报告、词条、评价和历史仅来自该历史样本，不代表新平台访问或真实销量。

采购、物流、汇率/手续费均为演示假设。尤其香水承运限制未验证，本演示使用手填物流成本，**不声称某个普通物流线路可承运香水，也不代表卖家合同成本或保证收益**。

## 负责人浏览器验收步骤

浏览器由负责人操作。本地普通 QA 凭据仅在本克隆 `.local/qa-credentials.txt`（0600），不把内容复制到 Git/Issue/交付消息。不要使用 root、生产配置或旧账号。

如 QA 服务未运行，必须在本克隆执行以下命令；不运行 start.sh 或 worker：

```sh
cd /Users/qianpengfei/Documents/ChatGPT/shophot/.local/round2-mvp-20261022
env PYTHONPATH="$PWD:$PWD/.local" DJANGO_SETTINGS_MODULE=qa_settings /Users/qianpengfei/Documents/ChatGPT/shophot/.venv/bin/python manage.py runserver 127.0.0.1:8005 --noreload
```

1. 打开 `http://127.0.0.1:8005/accounts/login/`，使用本次普通 QA 用户登录。首页输入 `https://www.beardbrand.com`，应复用保存的目录进度/报告；不要点击“更新”或创建采集任务，本 QA 无 worker。
2. 店铺报告说明历史/有限目录，从 Fox Hunt 进入 `/stores/6/products/1/`；打开 `…/history/` 看原观测。当前客户端已存一个普通 QA 候选，可通过报告“已加入候选”进入清单。
3. 候选点击“用明确历史报价测算成本”，应进入 `…/tools/profit/?catalog=80&candidate=<本账号候选id>`。也可在商品报告最近报价区选择某次精确观测；不要把随后的新报价自动等同原选择。
4. 核对原价 50 USD、观测 id/时间、规格 URL/SKU、未知国家/税运及候选上下文。下方假设填写：售价/成本币种都 USD，售价 50，减价 0，采购 20，手填物流 5，广告 2，其他 1，平台费率 10%，支付费率 3%，固定支付费 0.50。目标 20%。同币种实际汇率 1，不涉及实时汇率。
5. 点击计算，单件收入 50，成本项合计 28，平台费 5，支付费 2，净利 **15.00 USD**。预算可关闭；如启用沿用原必填验证与账本。确认演示假设与原报价分开，保存新的浏览器验收研究记录。
6. 打开保存记录，核对 v2 来源观测 #80 和不可变原价、用户输入；“继续测算”应固定原观测。修改成本、重新计算保存另一份，不改变第一份记录。两份同口径情景可用原比较页对比。
7. 失败路径：直接打开利润 `?catalog=53`（Beard Comb 范围）应显示具体错误且没有旧利润/保存按钮；恢复时明确进入无来源场景或重新选择有效观测。其他用户不能打开本账号 study/candidate 引用；CSRF 失败不写记录。
8. 负责人分别在桌面和 390 宽验收候选/利润/历史详情、主路径、失败与空状态并保存实际截图。本轮开发者未连接浏览器，不能把测试客户端的 HTML 校验当浏览器验收。

已有客户端 QA 私有记录名含“历史Fox Hunt · 假设成本QA”，仅证明隔离客户端流程；负责人浏览器须保存自己的新记录，不能用已有记录冒充浏览器验收。

## 已运行验证与待验收

显式隔离 SQLite 下：

- 新 catalog 来源专项 20 项；结合旧 reference/studies/comparison、预算流程、判断流程、候选和详情，最终 **119 项、13.543 秒全部通过，无跳过**。测试命令与输出在本克隆 `.local/targeted-tests-final.log`。
- 覆盖重复/冲突参数、范围/等价多规格/坏 scope、候选账号/URL/店铺隔离、整数撞号、精确币种和显式汇率、v2 签名/过期/保存/重新核验/继续/幂等、来源变更/删除、v1 兼容和 v1/v2 比较、CSRF 与旧流程。
- 真实历史 fixture 的测试客户端主路径使用普通账号和真实 CSRF，从首页输入保存店铺到 v2 保存/继续通过；socket.connect 被 mock 拒绝，确保不调用平台。前后观测 17、job 22、Product/Snapshot/CollectionJob 均 0，未伪造 Snapshot 或新增采集。
- Django check、迁移一致性、git diff --check 通过。没有新迁移，没有重复旧全套；最终隔离 PostgreSQL 全套和锁竞争验证由负责人安排，SQLite 不证明 PG 行锁效果。
- 私有收据：本克隆 `.local/QA_PREPARATION_RECEIPT.json`、`.local/HISTORY_LOOP_RECEIPT.json`、`.local/DELIVERY_RECEIPT.json`。不提交 QA 数据库、账号或配置。

待验收/缺口：负责人桌面/390 浏览器与截图、最终隔离 PG/并发；新来源实站可用性仍由 High 负责。暂不支持范围内人工选规格报价（旧 scope 不含逐 SKU 金额，不能推算）、全店差异/新增下架、来源保留的物流管理/导入往返；自有报价可在原模块先导入，再返回该利润页选择，或明确手填。当前只交付历史数据最小闭环，不称实时竞品服务、香水物流合规或商业版本已验收。


## 负责人最终验收补充（覆盖上方开发交付时的待验收状态）

负责人在准确b842f69源码的独立8005环境完成1280/390实际浏览器操作：店铺输入→保存报告→商品/真实历史→私有候选恢复/空状态→精确目录观测80→明示成本假设→净15保存A（id2）；手机继续A固定80、采购22重算净13保存B（id3），比较差-2、A指纹不变。范围53明确拒绝无save，菜单/退出、两布局无整页横溢出；source17/job22/Product0/Snapshot0/CollectionJob0不变。不是用既有客户端记录1代替UI。截图与BROWSER_ACCEPTANCE_RECEIPT.json在负责人.local/round2-mvp-history-20261022。

负责人补充独立PG v2真实行锁/并发22项2.918秒通过；合并High必要robots安全修复后，准确集成业务源d2b7e00e6c96e4b9d814f9517ad42aeece24ec30在随机唯一隔离PostgreSQL全套576项101.399秒无skip通过，Node脚本均执行，迁移/check/diff清。原High对目录利润/私有研究准确6fb53a0独立审查无可复现P1/P2。主服务已按ROUND2_DELIVERY_20261022.md从准确业务源冷启；源持续合法可用门槛未通过、无新商品报价，前述缺口继续保留。
