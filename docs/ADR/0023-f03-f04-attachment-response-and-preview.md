# ADR-0023：F03/F04 附件响应与安全预览

- 状态：已采纳
- 日期：2026-10-20
- 范围：F03/F04 患者记录图片附件列表、关联响应及图片预览授权。

## 背景

ADR-0021 定义了图片附件表和复用同源文件 gateway，但运行时附件响应未提供完整的记录/图集版本和文件状态，客户端也没有以附件关系为授权边界的图片预览入口。直接使用通用 `file_id` 下载授权只验证患者拥有文件，不能证明该文件仍属于未删除的饮食/排便记录附件。

## 决策

1. 列表和关联成功响应统一为 `RecordImageAttachment`：`id, record_id, position, record_version, image_set_version, file_status, created_at`。版本是该响应时记录当前版本；新关联成功时返回递增后的版本。`file_status` 为 `available` 或 `unavailable`，仅 clean 且存储可用的附件可获预览授权。
2. 新增 `POST /api/v1/record-images/{attachment_id}/download-grants`。服务端在认证患者范围内校验附件、父记录、文件、完成的 upload session/purpose、clean/available 状态和健康数据授权，然后写入既有 `health.file_download_grant`，返回现有同源 `/uploads/{capability}` gateway URL 与五分钟到期时间。
3. 每次 gateway 下载均再次验证图片 purpose 对应的活动附件及未删除父记录，并检查文件可用状态。因此附件或记录删除会立即使已签发 grant 不可用。其他文件类型继续使用既有通用授权语义。
4. 客户端以 attachment ID 保存持久关系；capability URL 仅保存在内存，预览前请求新 grant。不得持久化完整 URL、capability、bucket/key 或存储凭据。

## 后果与验收

无需新增表或迁移。实现需同步 OpenAPI、数据字典和 Android API 映射；契约测试检查附件响应必需字段及 grant 路由；PostgreSQL 集成测试覆盖本人预览、跨患者 404、真实 gateway 下载和删除后的拒绝。Android 预览仍需使用本地模拟器完成 UI/真实 API 验收。
