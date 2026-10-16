# ADR-0017：F02 解析结果 outcome 与疾病专属建议适用性

- 状态：已采纳
- 日期：2026-10-16
- 范围：A03–A06 的业务后端持久化、结果契约和验收；不包含 OCR/模型推理、不包含 A07 跨报告冲突判断。

## 背景

现有 F02 回调只接收候选数组，空数组会被解释为解析成功，不能区分“没有可支持事实”和“扫描质量不足”。F08 快照会保留被患者接受的诊断候选 certainty。F01/A03 与 F08/A26 要求无已确认医疗背景时仍允许生活记录和一般摘要，但不得产生疾病专属建议。

## 决策

1. Agent 回调增加受控 `parse_outcome`：`extracted`、`no_supported_facts`、`insufficient_quality`。`extracted` 必须至少含一个候选；其余两种必须候选数为零。技术执行失败继续使用现有 failure 回调和 `failed` 状态。`reason_code` 为有限枚举且不得带自由文本；仅非 `extracted` 时可用。
2. Outcome 是结果分类，不新增或改变既有 request/document 生命周期状态。它持久化到解析请求及医疗文档只读 DTO：`extracted` 进入 `needs_confirmation`；零候选结果以终态 `succeeded` 记录，文档仍保持既有 `needs_confirmation` 状态，由 outcome 区分原因。现有旧回调在兼容期将非空候选推导为 `extracted`；空候选拒绝，要求调用方显式给出零候选 outcome。
3. 仅内部服务认证 Agent 回调可写 outcome；APP 只读。outcome 回调必须满足当前授权、请求未终态、文档与版本仍匹配。相同 callback_id/摘要幂等；不同摘要冲突；迟到/重复终态回调拒绝或按已登记幂等响应处理。不得在 outcome/reason 中保存报告正文或模型自由文本。
4. 解析候选只有患者逐字段 accept/correct 后才成为确认事实。`suspected`、`rule_out`、`history` certainty 必须原样保留在事实、API DTO 和 F08 快照；仅 `certainty=explicit` 计为明确确认诊断。
5. 无 `certainty=explicit` 确认诊断的任务仍可包含一般生活记录摘要，且可接受 `applicability.scope=general` 建议；拒绝 `condition_specific` 建议并整笔回滚该 callback，返回 RFC 9457 409，不创建 advice、callback receipt 或部分数据。`ADVICE_NOT_APPLICABLE` 是永久性业务拒绝；Agent 即使收到 HTTP 409 也不得自动重试该 callback。疑似、待排、既往史均不满足明确诊断条件。
6. 新增字段使用 Alembic 增量迁移并沿用现有表 FORCE RLS、患者复合归属、worker/API/Agent 角色最小权限；downgrade 仅移除新增字段/约束，不改写既有解析数据。

## 后果与验收

同步数据字典、Agent/OpenAPI、错误示例、测试方案及追踪矩阵。测试覆盖三类 outcome cardinality、授权/版本/重放/迟到回调、零候选事实隔离、A03 general 与 condition-specific 适用性、A05 更正值进入后续新快照且旧候选/决定审计保留，以及 A06 certainty 端到端不升格。真实 PostgreSQL 18/MinIO 集成和备份恢复通过后仍须独立验收；本 ADR 不覆盖 A07。
