# ADR-0004：同步数据库会话与 Celery 异步任务

- 状态：Accepted
- 日期：2026-10-14

## 决策

API 与 Worker 统一使用同步 SQLAlchemy Session；耗时智能分析、文件补偿、通知投递由 Celery 5.6 + Redis Broker 执行。最终任务状态保存在 PostgreSQL，不使用 Celery Result Backend 作为事实来源。

## 理由与后果

统一事务模型降低 API/Worker 双栈复杂度；模型处理本身是异步业务任务，不依赖 async ORM 获益。Celery 消息只携带 `task_id`，不得携带患者正文。
