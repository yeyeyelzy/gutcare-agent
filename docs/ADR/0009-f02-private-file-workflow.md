# ADR-0009：F02 私有文件上传、医疗档案与删除补偿

- 状态：已采纳
- 日期：2026-10-15
- 范围：业务后端文件存储及医疗文档元数据；不包含智能体抽取、字段候选确认或分析结果写入。

## 决策

1. 原始文件存放于私有 MinIO/S3 bucket。APP 只访问业务 API；不得收到 bucket、object key、对象存储凭据或 MinIO 管理端地址。
2. `POST /api/v1/files/uploads` 接收 purpose、文件名、声明 MIME、预期字节数和 `Idempotency-Key`。服务器生成 `health.upload_session`、bucket/key、15 分钟过期时间和一次性 opaque capability。仅 capability 的 SHA-256 存储在数据库；同一幂等键及相同请求摘要返回原会话，摘要不同返回 409。
3. APP 将原始文件以 `PUT /uploads/{capability}` 上传到同源 HTTPS gateway，使用认证 Bearer token，不执行 S3 预签名直传。最大 PDF 20 MiB，JPEG/PNG 10 MiB，按 purpose/类型进行服务端校验。完成操作按认证用户反查上传会话，核验对象实际大小、MIME、魔数、SHA-256、PDF 可读性/加密状态及图像解码。
4. `MalwareScanner` 为必需的 fail-closed 依赖。生产连接 ClamAV `clamd` 的 INSTREAM 协议；只有扫描 clean 才创建 `health.file_object` 并设为 `available`。感染文件为失败状态并清理对象；扫描器不可用则失败关闭并返回 503。测试可注入 Fake scanner，集成门禁需运行真实 ClamAV 并使用 EICAR 测试样本。
5. 医疗文档使用专用 `/api/v1/medical-documents` CRUD 接口管理元数据：`document_type`、`hospital_name`、`document_date`、`notes`（最多 1000 字）、`processing_mode` (`store_only|analyze`) 和 `parse_status`。旧业务字段 `visit_date` 对应本接口 `document_date`。`analyze` 只记录 `pending`/待后续任务；本阶段不调用智能体，也不伪造抽取候选或患者事实。`confirmed` 仅可由未来逐字段显式确认流程设置。
6. 文件和文档均启用 RLS。复合外键保证关联文件属于同一患者；跨患者访问统一返回 404。健康数据/敏感图像处理需相应 consent。
7. `POST /api/v1/files/{file_id}/download-grants` 签发 5 分钟、单对象、只读 capability；数据库只存 token hash，不持久化完整 URL，也不得把 capability/token/query 写入日志。删除或不可用文件不签发下载授权。
8. 删除立即软删除文档并将文件标为 `deleting`，从列表、详情和下载中隐藏；写入 7 天延迟删除 job。worker 幂等物理删除对象和数据库记录，失败时退避重试。后续阶段须在此生命周期节点清理关联分析结果的 basis/excerpt/locator。

## API 与状态码

接口包括上传申请/完成、同源上传 gateway、医疗文档列表/创建/详情/更新/删除、文件下载授权和 capability 下载。请求/响应错误统一 RFC 9457。稳定错误包含认证失败 401、资源不存在/跨患者 404、冲突 409、超限 413、不支持类型 415、内容/字段校验失败 422、限流 429、存储或扫描不可用 503。

## 实施/集成依据

镜像源补充决策（2026-10-15）：此前在本文件中记录的 Docker Hub MinIO 镜像已不可拉取。现行集成使用 `quay.io/minio/minio:RELEASE.2025-09-06T17-38-46Z`，依据 MinIO 官方 Compose 示例及 Docker README 固定 Quay 版本：[官方 Compose 示例](https://github.com/minio/minio/blob/master/docs/orchestration/docker-compose/docker-compose.yaml)、[官方 Docker 部署说明](https://github.com/minio/minio/blob/master/docs/docker/README.md)。ClamAV 继续使用 `clamav/clamav:1.5.4-debian13-slim`。生产发布仍需锁定 image digest，并内部隔离 clamd TCP。

- PostgreSQL schema 仅经 Alembic 增量迁移；F02 migration 建立 upload session、file object、medical document、download grant 和 deletion job。
- ClamAV INSTREAM 协议及守护进程网络限制依据[官方协议文档](https://docs.clamav.net/manual/Usage/ClamdProtocol.html)；容器安装依据[官方 Docker 文档](https://docs.clamav.net/manual/Installing/Docker.html)。测试 compose 使用固定版本 `clamav/clamav:1.5.4-debian13-slim` 与 `minio/minio:RELEASE.2025-07-23T15-54-02Z`；标签来源：[ClamAV 官方 Docker 标签说明](https://hub.docker.com/r/clamav/clamav/tags)、[MinIO 镜像标签](https://hub.docker.com/r/minio/minio/tags)。生产发布应再按架构锁定镜像 digest，并内部隔离 clamd TCP。
- 必须通过真实 PostgreSQL 18、MinIO、ClamAV 集成与权限测试；扫描/对象存储故障时不能把文件标记为可用。

## 实施增补（2026-10-15）

- 上传与下载 gateway path 为 origin-root `/uploads/{capability}`，不得拼接全局 `/api/v1` server 前缀；OpenAPI path-item server 已显式指向 gateway origin。
- 同一患者同一 `Idempotency-Key` 与同一请求摘要，无论会话处于 issued、uploaded、completed 或 expired，均返回相同会话资源与确定性 HMAC capability；请求摘要不匹配返回 409。Capability 不续期，过期资源语义不改变；调用方需使用新幂等键创建新会话。
- 新增 Alembic 0006：upload_session 与 file_object 的患者复合外键、available 必须 scan clean 的 DB CHECK、worker lease 字段、orphan cleanup job、过期会话回收策略。`gutcare-file-worker` 每 15 秒扫描并支持五分钟 lease 恢复；数据库凭证必须使用 `gutcare_worker`。
- Capability 位于 URL path，应用启动即禁用 `uvicorn.access` 原始 URL 日志，并仅保留经过 route-template 脱敏的应用请求日志。
- MinIO 官方二进制归档地址现返回 410；测试使用官方 Go 1.24.8 工具链从官方模块固定 tag `github.com/minio/minio@RELEASE.2025-09-07T16-13-09Z` 构建，产物仅留在 ignored runtime 目录。此前尝试的 Quay/Docker Hub 镜像不可用，不作为当前运行方式。生产构建须由 CI 输出 SBOM 并执行扫描、签名和制品留存策略。

## 后续阶段边界

多智能体读取任务冻结快照、医疗文件解析任务、候选逐字段确认、确认事实落库和历史分析结果重算/清理由后续阶段实现，不能由文件服务直接写业务事实。
