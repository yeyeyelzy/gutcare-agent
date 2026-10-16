# ADR-0018：F02 已确认检验结果的保守冲突管理

- 状态：已采纳
- 日期：2026-10-16
- 范围：F02 A07 后端事实版本、患者冲突审阅 API、F08 快照投影；不包含 OCR/Agent 自动判断、不包含诊断/处方/用药相互作用推断。

## 背景

A07 要求新报告与既有处方信息冲突时提示患者核对，不得自动决定新旧谁更优。当前解析候选经患者确认后形成独立事实，但缺少跨报告冲突实体和快照中的待核对语义。文档日期与采样日期不能混为一谈，不同日期的同项检验值是历史趋势，不是冲突。

## 决策

1. 自动冲突候选仅覆盖同一患者已确认的 `test_item` 与 `test_result`。仅当每份来源报告内两字段均已形成 active confirmed fact，且满足以下条件，才生成或更新一条 open conflict：至少两个不同来源文档；规范化 test item 相同；单位规范化值相同；有效采样日期相同；规范化 result 不同。有效采样日期优先取 `test_result.value.sampled_on`，缺失时使用来源医疗文档的 `document_date`；任一侧仍无日期时不自动比较。不同日期永远不构成此类冲突。
2. 规范化只做保守文本标准化：Unicode NFKC、首尾去空白、内部连续空白折叠、大小写折叠；result 数值按有限 Decimal tuple 手工规范化，禁止 context 舍入和指数展开，使用系数/指数形式比较；非数值文本按同一文本规则。候选字符串最大 200 字符；NaN/Infinity 拒绝。单位仅做文本规范化，不转换单位、不应用医学阈值或生物等效判断。缺失单位只与另一侧同样缺失单位时比较。仅相等/不等比较，不推断严重程度、临床显著性或因果。
3. `test_result.value` 允许新增可选 ISO 日期 `sampled_on` 与可选受控 `unit`；缺失采样日期回退 `document_date`，两者皆缺则不比较。候选的现有 `unit` 字段继续兼容；规范化后以 `test_result.value.unit` 优先、外层候选/事实 unit 回退。此字段来自患者逐字段确认/更正的候选值，缺失不推导。诊断、recommendation、medication 文本语义/同义、用药有效性或相互作用不自动比较；保留事实与来源，交由患者/专业人员核对。
4. Alembic 0022 新增患者级冲突与成员表，0023 在患者内对非 invalidated 的 `group_hash` 建唯一约束，并用迁移 guard 拒绝存量重复活动分组。冲突保存不可逆 group hash、受控状态 `open/resolved/invalidated`、`record_version` 与时间；成员通过复合患者外键关联 `confirmed_medical_fact` 和 `medical_document`，标明 `test_item/test_result` 角色及来源。不得复制原始报告正文/完整候选摘录/完整事实值。两表 FORCE RLS；APP 只读读取，解析服务在患者授权栅栏内维护，Agent 无冲突表直写权限。
5. 对每个 conflict group 仅保留一个稳定冲突实体，重新计算按 group hash 幂等。已 resolved group 出现新的不同来源/成员时扩展同一实体、递增 `record_version`、清除 resolution 审计并重开为 open，不新增第二行；成员未变化的重放不改变状态/版本。患者可通过带 `expected record_version` 和 `Idempotency-Key` 的显式 API 选择 `keep_both`；该操作只将状态改为 resolved 并追加一次性审计字段，不删除/修改/择优任何成员或事实。暂不提供 `select_member`，因此不引入自动 supersede 规则。相同 key 和摘要重放返回原结果；摘要不同或过期版本返回 RFC 9457 409。不同患者返回常量 404。
6. 患者接受/更正相关事实、源文档删除或 `document_date` 单字段变更时，在同一患者级 advisory 锁/事务内重新计算受影响 group。单独更正文档日期保留既有已确认事实/候选来源，按新的 fallback 日期重算冲突；旧分组不再成立时 invalidated，新日期形成的分组按需创建。日期与其他元数据一起修改仍按既有元数据变更流程失效解析候选。冲突状态变化递增 `record_version`，通过 group hash 和成员 fingerprint 幂等去重。来源文档删除事务先将关联 open/resolved conflict 标记 invalidated、清空 resolution 字段，记录低敏原因码与来源版本，再仅清理实际成功转为 invalidated 的成员并把对应事实按既有来源删除策略标记 `source_deleted`；invalidated conflict 保留不含正文/完整值的去标识审计。其他事实变化导致旧 open/resolved conflict 不再成立时标记 invalidated。所有患者决定与状态变化在 conflict 行受控审计字段留痕。
7. F08 冻结快照中，open conflict 的 member facts 不得再作为普通 `confirmed_medical_fact` 重复投影；改为 `medical_fact_conflict` 记录，含 `conflict_status=open`、`review_required=true`、成员受控 test item/result/unit/采样日期、事实与文档来源 ID/版本。此 envelope 仅表示存在相互不一致的患者确认信息，仅供待核对；Agent 不得选择、融合、升格为单一事实或据此生成诊断/处方建议。resolved `keep_both` 冲突不作 unresolved envelope，成员可按来源继续投影为各自 confirmed fact，但附 `reviewed_conflict_ids`，不得暗示择优。invalidated 冲突不进入快照。
8. 冲突列表、详情、解决 API 和 Agent 快照 schema 同步 OpenAPI、权限/错误响应、数据字典、部署/测试追踪。迁移可逆，不修改历史 facts/candidates；RLS/FORCE RLS、患者复合外键和最小授权必须实测。

## 后果与验收

覆盖同日不同结果创建唯一 open、数值十进制等价 (`5`/`5.0`/`"5.00"`) 不冲突、NaN/Infinity 拒绝、单位 NFKC/casefold/空白规范化且缺失单位仅与缺失单位比较、不同日期/日期变更不误报、resolved group 新来源重开同一实体、删除/resolve 并发不留 resolved 空成员、回调重放/患者决定幂等、跨患者隐藏、乐观锁冲突、keep_both 保留全部成员、来源删除 invalidated、事实更正后 reconcile，以及 F08 快照用 unresolved envelope 替代普通成员 facts。真实 PostgreSQL 18/MinIO 集成、迁移 round-trip 与备份恢复通过后仍须独立验收；不得将本 ADR 状态视作 A07 已验收。
