# PRICE-HTML-E 交付与 C 独立审查

E base2695af54e56eb69988fe4d41634242a47418246e，独立分支 codex/price-html-d-ui-20261022。

## E 范围

只改 research.AVAILABILITY、ResearchFilterForm 与 availability.html，增加 Discontinued → 停止供应。原所有状态和未知逻辑保持；不改parser/transport/model/路由/数学，不回写原真实两条观测。新受控专项创建显式隔离测试夹具、历史和普通私有候选，验证报告/详情/历史/候选显示一致；筛选选择可用且未观测商品仍未知；GET前后全观测数据、任务数和目录内容不变。所有已知状态模板与表单一并回归。

26项专项0.724秒无skip，独立clone内显式SQLite；check/迁移/diff清。初夹具遗漏历史job_id产生2错，修夹具后通过，初日志保留。未重全套。

## C 独立只读审查

精确 C618fe96cb63a5bff63d4fd41ed99889617bbb373、base586ed523；已核工作文件匹配Git blob。审查两文件增量及完整相关路径、来源说明、私有原正文审计/复演收据。版本suffix限已核v/V数字修订或FT232RL，必须独立HTML title、移动H1、OG及Twitter一致；返回完整版本名。原PID/显式SKU/Offer/规范域名/单主报价/USD/2MB界限未放松。未选part_id选择器、选中SKU不一致仍拒绝。Discontinued必须schema与主DOM No longer stocked相符，存在所选widget时也必须一致；OutOfStock和In stock真冲突仍拒绝。

独立最小Django无DB且socket连接/DNS阻断，24项专用测试0.423秒通过，无skip。第一次harness提前替换socket类触发ssl导入错误，改阻断连接方法后通过，原失败日志保留。未修改C源或运行其回写证据脚本。独立读取13份原容器，限定2MB解压，长度和解码SHA256与High审计逐一一致，原来源收据SHA256一致。未HTTP或访问业务DB/凭据。

审查未见可复现P1/P2。离线6接受/4拒绝仅保存响应可解析性，原实时仍2条；未知型号/库存冲突继续拒绝，不能声称全店或实站新6条。负责人最终合并C/E后回归与真实UI验收待完成。本队冻结停止。

私有日志：.local/discontinued-tests.log、c-independent-review-tests.log、c-evidence-independent-check.json（0600）；初失败日志同目录保留。未操作用户main tab、QA服务或新建持久账号。
