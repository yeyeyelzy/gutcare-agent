# ADR-0015：F07 活动记录与 F11 历史趋势

- 状态：Accepted（2026-10-16）
- 范围：F07 活动记录，F11 混合历史时间线与确定性趋势；不生成智能摘要。

## 决策

1. `health.activity_record` 保存患者手动活动记录。类型为 `walking/jogging/cycling/other`，`other` 必须填写 1–160 字描述；强度为 `low/moderate/high`；主观感受为 `better/same/worse`；时长 1–1440 分钟；`occurred_at` 表示活动开始时间。记录严格 DTO、本人 CRUD、时间半开筛选、稳定分页、乐观锁与立即不可见软删除；RLS 强制按患者隔离。
2. `/history/timeline` 使用 UNION ALL 查询饮食、排便、症状、服药打卡、活动及建议。游标按 `(occurred_at DESC, type ASC, id ASC)` 排序，HMAC 使用现有 JWT signing key；游标无效返回 RFC 9457 `INVALID_CURSOR`。事件只返回受控源类型、时间和详情跳转 target，不复制正文。
3. `/trends` 输入带时区 `from/to`，使用 UTC 半开区间 `[from,to)`。日/周桶在 PostgreSQL 中按 `patient_profile.timezone` 转换和聚合；支持排便次数及 Bristol confirmed/unknown、症状自评严重度及 ongoing/relieved、已确认饮食类别、服药打卡各状态、活动次数/时长。服药统计基于已物化打卡的 `scheduled_for`（其发生时间）；计划结束/停用不删除历史打卡，因此仍计入历史。未来待打卡的物化策略属于 F06，不由 F11 补建。仅输出有样本的桶，并显式 `has_data`；无数据为空且 `has_data=false`，不以 0 代表缺失。
4. 趋势全部通过 SQLAlchemy Core 在数据库聚合，不拉取全量记录到 Python、不物化。现阶段不输出饮食与症状的邻近事件或因果推断。
5. 周期总结沿用 F08 periodic_summary 任务闭环；本次不新增文本生成端点或摘要实体。Agent 不可用不影响历史/趋势查询。

## 验收映射

- T87：活动 DTO、CRUD、other/时长/timezone 校验、版本冲突、软删除及 PG18 RLS/跨患者隔离。
- T88：多源时间线类别过滤、签名游标、相同时间排序无遗漏/重复、target 跳转与 Agent 不可用独立性。
- T89：PG18 趋势区间边界、患者 IANA 时区/DST、日周 bucket、缺失与零区分、各项状态/类别统计。
- T90：PG18 查询计划与 `(patient_id, occurred_at)` 索引合理性、SQL 聚合执行及权限隔离。
- T91：迁移前滚/回滚和真实 PostgreSQL 18 备份恢复后活动记录及历史引用可用性。

6. 游标签名载荷绑定规范化 `since/until`（UTC ISO-8601）及类别集合（排序去重）；患者范围来自认证上下文，不进入游标。历史 `target.type` 使用稳定资源枚举 `diet_record/stool_record/symptom_record/medication_checkin/activity_record/advice`。

## 后果

活动记录是新增患者健康数据，须遵循现有健康数据授权、患者 RLS、单记录 7 天清除及账户注销清理策略。索引不保证查询计划一定选择索引，T90 需在代表性数据量上验收。
