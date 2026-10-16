# ADR-0014：F12 P0 站内通知与事务 outbox

- 状态：已采纳
- 日期：2026-10-16
- 范围：APP 可读取的站内通知、普通通知偏好、领域事务 outbox 与内部 dispatcher；不包含外部 push、供应商 SDK 或系统通知。

## 决策

1. F12 通知由 F08 任务终态（succeeded/partial/failed）、F09 新建议、F10 新风险提示和 F06 新建 pending 打卡提醒驱动。领域状态与 outbox 事件同事务提交；outbox 不改变领域状态。F06 物化器对每个 schedule/local_date 创建打卡实例时同时写入 reminder 事件。
2. `health.notification_outbox` 使用独立 `gutcare_notification_worker` 角色处理。dispatcher 使用 `FOR UPDATE SKIP LOCKED` claim、lease、超时恢复、指数退避、有界最大重试和 dead-letter。每个事件只可派发一次逻辑通知；`(patient_id,deduplication_key)` 唯一。
3. outbox payload 是严格白名单对象，只含 `event_type`、`patient_id`、受控 `target_type/target_id`、`occurred_at`、`priority`、`deduplication_key`。不含正文、药名/剂量/医嘱、报告/建议内容、locator/URL、prompt 或模型原始输出；DB CHECK 与服务 DTO 双重拒绝未知键。
4. 患者 API 提供通知稳定 cursor 列表、category/unread 过滤、详情、未读计数、单条已读和批量已读。target 仅投影受控资源类型与 ID；来源不存在时返回 `target_unavailable=true` 并清空 target，不泄露来源详情。统一跨患者 404。
5. 普通 F06 提醒可由 in-app category 偏好关闭；quiet hours 仅影响普通提醒派发时机。风险事件总是生成，不受偏好/静默时段影响，且不会改变 F10 `risk_alert.status`。账号冻结或健康数据处理授权撤回阻止新普通通知；风险仍在 F10 业务内生成，但冻结账号不能通过 API 读取。注销后的通知由 F13 清理。
6. 所有患者表启用并强制 RLS，使用患者复合 FK；API 与独立 notification worker 使用分开的最小权限角色。worker 只读取白名单事件和必要的 target 存活状态，不读取通知正文或医疗内容。

## 验收与后果

新增 Alembic 迁移、OpenAPI、字典、数据库、隐私、部署、测试和追踪同步。测试从 T80 起；真实 PostgreSQL 18 覆盖四类事件映射、敏感 payload DB/服务拒绝、去重、并发 claim/lease/retry/dead-letter、risk 偏好豁免、未读/read 并发、RLS/404、target 删除、worker 权限及 restore。追踪状态为 `implemented`，独立验收后改为 `verified`。发布需通过标准代码门禁及独立通知/Pg18 门禁。
