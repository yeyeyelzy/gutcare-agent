# ADR-0011：F02 医疗文档字段候选与患者逐项确认

- 状态：已采纳
- 日期：2026-10-15
- 范围：F02 `analyze` 文档的持久解析请求、受限 Agent 输入/候选回调、逐字段确认及来源删除失效；不包含 OCR/模型推理、F08 分析和账户注销。

## 决策

1. `store_only` 文档保持 `parse_status=not_requested`，不创建解析请求或可派发任务，仅要求现有 `health_data_processing` 授权。`analyze` 文档要求当前同时授予 `health_data_processing` 与 `third_party_ai`，仅在文件 available 时创建关联文档 ID、患者 ID、文件 ID、文件版本的解析请求。业务 Worker 唯一领取，Agent 不 claim。claim、冻结输入读取、候选提交及失败回调每次重新检查两项当前授权。
2. Agent 通过服务间 Bearer 认证调用任务级内部端点；只能读取此请求冻结的单文档文件内容，不能按患者 ID 查询记录、读取历史或使用业务数据库凭证。回调只接受与请求、患者、文档、当前文件版本完全匹配的严格类型化候选；迟到、删除、撤回或文件不可用请求被拒绝或失效。
3. 候选字段代码来自白名单。字段类型决定值结构和单位；日期严格 ISO 日期；数值不允许隐式字符串转换。置信度与不确定性分别保存。来源定位至少有页码、半开字符区间、归一化 bbox 之一，excerpt 有长度上限。诊断候选保留明确/疑似/待排语义，任何疑似候选不得映射为确诊事实。
4. 患者逐字段 accept/correct/reject，决定端点返回 `204 No Content`，所有写入要求当前版本和 `Idempotency-Key`。相同 key 与相同决定摘要的重放仍返回 204，且不新增审计或事实；同 key 不同摘要返回 409。每个新决定追加审计历史；确认事实存于独立表，只能由患者决定服务写入，Agent 角色无权写入。禁止整包确认。
5. 删除/撤回/文件不可用时立即禁止新读取并清除候选 excerpt、locator 和冻结文件访问能力。撤回任一 `health_data_processing` 或 `third_party_ai` 授权时，在同一事务中 invalidates 所有非终态解析请求并清除相关候选 excerpt/locator；迟到候选与失败回调均拒绝，不生成事实。依赖结果按隐私生命周期标记 `basis_updated` 并脱敏。与 F06 来源墓碑兼容。
6. 通过 Alembic 增量迁移、患者 RLS/FORCE RLS、复合患者外键、独立最小 Agent 数据库角色和安全内部 HTTP 完成隔离。Agent 凭据不得写入日志。
7. 授权撤回与 analyze 创建、parse claim/input/callback、患者决定及源文档删除，先获取患者授权栅栏，再按 `medical_parse_request → medical_field_candidate` 取行锁。栅栏由事务级 PostgreSQL advisory lock 提供：固定命名空间 `gutcare.patient-consent-fence:` 与患者 UUID 拼接后以 `hashtextextended(..., 0)` 得到稳定 64 位 key；操作路径使用 `pg_advisory_xact_lock_shared`，授权变更与源删除使用 `pg_advisory_xact_lock`。锁一直持有至事务提交，随后在锁内复验授权。Agent input 持共享栅栏直至 MinIO 对象读取完成。无需给 worker 增加 patient_profile UPDATE 权限。
8. 患者决定的重放收据独立于决定审计，记录患者、候选、Idempotency-Key、规范化 `{action, corrected_value}` 摘要哈希及固定 `204` 状态。相同键和摘要在候选状态变化或来源脱敏后仍返回 `204`、不新增审计/事实；相同键的摘要或候选不符返回 `409`。通过 Alembic 0012 增量建表，不改写 0011。

## 后果与验收

新增解析请求、字段候选、字段决定历史、确认事实及独立幂等账本表；新增患者候选查看/逐项决定 API 和内部任务输入/结果/失败 API。测试至少覆盖 T60 起编号，并映射 T03-T06、A04-A07。真实 PostgreSQL 18 与 MinIO 集成必须覆盖跨患者、版本/定位校验、逐字段决定、并发/幂等、授权撤回锁竞争、store_only、删除脱敏及迟到回调。追踪状态保持 `implemented`，直至独立验收。
