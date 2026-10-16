# ADR-0016：F13 隐私导出、注销清理与恢复重放

- 状态：已采纳
- 日期：2026-10-16
- 范围：F13 患者数据导出、全量账户清理、审计保留和备份恢复后的清理重放；不改变 Agent 推理。

## 决策

1. `privacy.deletion_operation` 独立于账户/患者外键，使用 UUID operation id、患者标识哈希、一次性高熵 receipt 的 SHA-256、状态、请求/完成/到期时间、lease 与受限错误码。删除请求与同账户并发请求通过账户锁及唯一活动操作约束收敛为一个 operation。receipt 明文只在创建响应返回；状态接口用 operation id 与 receipt 验证，不要求有效账户会话。未知 operation、错误 receipt、限流统一返回常量 404。
2. 删除提交事务立即停用账户、撤销全部 refresh session 和全部当前 consent、取消分析/解析任务及待发通知，并写入 30 天 SLA `due_at`。worker `gutcare_privacy_worker` 使用独立凭证、lease、持久步骤账本、指数退避和 dead-letter；逾期操作标记 overdue 并告警。每次请求/claim 建立 MinIO inventory，包含登记文件、未完成上传、孤儿对象和导出产物；先撤销 download grants、upload capabilities、导出能力和回调接收资格，再删除对象。
3. 对象确认删除前 inventory 保留 bucket/key；完成后将 key 置空，仅保留加密摘要。数据库按依赖次序清理 F12、F09、F08、F02 candidates/documents/files、F03-F07/F10、consents/profile/account。全局 `safety.risk_rule` 不属于患者数据，不删除。墓碑及备份轮转覆盖至少 35 天；恢复到 readiness 前，必须重放所有 pending deletion 和对象 inventory。worker 只操作业务 API 数据及私有对象，不接触 `gutcare_knowledge`。
4. 清理完成后 operation 的 patient id 置空；仅保留 account hash、operation/status/timestamps、步骤摘要和受限错误码。去标识 security audit 保留 180 天，不写正文、对象 key、完整 locator、token、prompt 或模型原始输出。
5. 导出使用患者 API `create/preview/list/status/confirm/cancel` 与异步隐私 worker，类别采用服务端白名单。产物为规范 JSON 与 manifest ZIP。只允许患者确认后创建，注销立即取消并使下载能力失效。支持同源 gateway 一次性、5 分钟下载能力，服务端流式读取 MinIO；禁止直连 MinIO。
6. 固定使用应用层 AES-GCM：每个导出随机生成 256-bit DEK 加密 ZIP；DEK 另用部署密钥 `EXPORT_KEK` 包装，数据库仅存 `wrapped_dek`，下载 gateway 用 KEK 解封后解密，不将 DEK 明文写库或日志。缺少有效 KEK 时导出不可用，不降级为未加密或 SSE-only。MinIO 对象始终私有且仅 gateway 可读。导出文件仅允许当前患者、`available` 且 `scan_status=clean` 的文件；ZIP entry 使用安全 basename、单项/总量设限，生成后扫描 entry 路径和 JSON 禁止字段。不得导出密码、token、callback、幂等键、内部 locator、prompt、模型原始输出或知识库正文。
7. 所有患者表使用 RLS/FORCE RLS、最小角色和复合患者归属约束。请求与审计日志不写导出正文。迁移仅通过 Alembic；导出短期对象同样进入 inventory 和过期清理。

## 验证门禁

真实 PostgreSQL 18 与 MinIO 必须覆盖并发请求/receipt、worker 崩溃恢复及步骤顺序、F02-F12 全量清理、多对象和失败重试、迟到 callback、SLA/180 天留存、导出隔离/内容扫描/一次性下载/过期/注销失效、restore replay 与权限隔离。两套门禁分别为 backend 静态/单测和 PG18/MinIO 集成+恢复演练。实现阶段测试先标 `implemented`，验收证据齐全后才标 `verified`。

## 兼容与恢复

新状态查询不依赖登录，不泄漏 operation 是否存在；旧 `/patients/me/account-deletion` 保留为请求入口并在响应中增加 receipt。新 migration forward-only，不允许 downgrade 伪造已清理的数据。备份恢复后先运行 `gutcare-privacy-worker replay`，确认 pending deletion、对象 inventory 和墓碑均覆盖后才开放 readiness。
