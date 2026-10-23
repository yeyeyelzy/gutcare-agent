# 本机 phone-demo F08 Agent（默认 mock）

来源：Agent 快照来自 [caoyimiao0625-alt/gutcare-agents](https://github.com/caoyimiao0625-alt/gutcare-agents)，导入 commit `40ec9f434632da587a66f4b10bf0e5e72693aa78`，详见 `../agent/PROVENANCE.md`。该来源未附 LICENSE，授权与素材使用状态待用户选择。

本指南为 `compose.phone-demo.yaml` 增加的可选 `agent` profile，包含 F08 与 F03/F04 图片任务 dispatcher。F08 路径为业务 API 创建冻结任务、唯一 dispatcher claim 并派发、独立 Agent 读取快照并回调、患者查询终态。F03/F04 使用独立图片 request、outbox dispatcher、一次性图片读取能力和候选 callback，不复用 F08 任务。没有 `.env.agent.local` 时默认 `mock`，不调用模型且不需要模型密钥。仓库提供可跟踪模板 `.env.agent.example` 和被 Git 忽略的本机文件 `.env.agent.local`；本机模板显式设为 `live`，API Key 为空，启动脚本会在启动服务前拒绝缺少 key、base URL 或模型名的配置。

F02 医疗档案解析现已接入受保护的业务端解析请求 claim API 与 `medical_parse_dispatcher`；Agent 同步上游 bridge commit `6662ebb`，Android 对 `pending/processing` 状态自动刷新。T154 本机 live 最小 E2E 已通过，范围和脱敏结果见 `evidence/F02-phone-demo-live-E2E-20261022.md`。该单次链路不证明真实报告识别准确率、临床有效性、完整 Android UI/真机或生产验收；Agent 候选始终是待审内容，患者逐字段确认前不得进入确认事实。F02 其它 mock 示例仍只验证其各自接口/状态流转，不作为真实识别质量证据。

## 启动与运行

在仓库根目录运行：

```powershell
.\scripts\phone-demo-agent-up.ps1
.\scripts\phone-demo-agent-f08-e2e.ps1
```

### 可选：本地真实模型 F08 演示

在仓库根目录将 `.env.agent.example` 复制为 `.env.agent.local`，只在本机文件中填写 API Key。`.env.agent.local` 已被 Git 忽略；不要把密钥填进示例文件、`phone-demo.env`、聊天、命令行或日志。启动脚本会追加读取该文件，并在 live 配置缺少 API Key、地址或任一模型名时安全失败，不打印配置值。具有本机 Docker 管理权限的人可在容器运行期间检查容器环境。也可用当前 PowerShell 进程的同名环境变量覆盖本机文件。

```powershell
Copy-Item .env.agent.example .env.agent.local
# 用编辑器打开 .env.agent.local，仅填入 GCA_API_KEY；不要在终端命令中写密钥。
.\scripts\phone-demo-agent-up.ps1
.\scripts\phone-demo-agent-f08-e2e.ps1
```

之后若要恢复 mock 模式，停止 Agent profile，并在本机文件中将 `GCA_MODE` 改为 `mock`、清空 `GCA_API_KEY`；该文件仍会被 Git 忽略：

```powershell
.\scripts\phone-demo-agent-down.ps1
# 用编辑器将 .env.agent.local 中 GCA_MODE=live 改为 GCA_MODE=mock，并清空 GCA_API_KEY。
```

模型服务可能按调用量计费。此演示只提交随机合成账户与结构化 F08 症状记录；不要在 live 模式使用真实患者资料或图片。`.env.example` 中的模型名称仅作配置参考，实际可用性和账户额度以所选服务商控制台为准。

启动脚本沿用现有 `phone-demo.env`，首次启动时随机生成并保存两枚不同的本地 token，且不打印它们。`AGENT_INTERNAL_TOKEN` 仅供 dispatcher 调 Agent 入站接口；`AGENT_SERVICE_TOKEN` 仅供 Agent 访问业务内部 API，必须与业务 API 的 `AGENT_SERVICE_TOKEN` 相同。两者都不能复用生产凭据。

`api` 使用单独的 `ANALYSIS_WORKER_DATABASE_URL` 接入既有最小权限 analysis worker PostgreSQL role。F08 dispatcher 仅通过业务内部 API claim。F03/F04 `record-image-dispatcher` 先经业务 API 的原子 claim endpoint 领取请求（该操作同时生成 dispatch outbox），再发送 outbox envelope；Worker 轮询持续运行，并使用同一最小权限角色读取/更新专用 outbox。它不自行读取冻结记录或图片，且仅连接 `private` 与 `agent_internal` 网络。Agent 保留 `agent_internal` 用于访问业务 API，并单独连接 `agent-egress` 普通 bridge，仅为 live 模型调用提供 DNS/HTTPS 出网能力；dispatcher、PostgreSQL、Redis 和 MinIO 均不加入该网络。Agent 仅接收 `GCA_INTERNAL_TOKEN` 与业务 API 的 HTTP 地址/服务 token，不获得数据库 URL、数据库密码或其他业务库凭据；Agent 用独立的 `phone_demo_agent_sqlite` 卷保存自身任务 journal。图片 Worker API 托管原子 claim、冻结 input 和一次性 capability；Agent 按 request ID 取输入、每张图片只消费一次 capability，再提交候选或受控失败码。该出网网络仅用于本机 demo/live 冒烟，不代表生产环境的域名白名单或网关策略。

E2E 脚本创建随机合成邮箱、完成 Mailpit 邮箱验证，记录 `third_party_ai` 测试授权，新增一条结构化症状记录并发起综合分析。脚本仅输出阶段、HTTP 状态、task ID 和任务状态，不输出邮箱、密码、患者访问令牌、内部 token、记录正文或 Agent 原始结果。脱敏摘要写入 `.demo-output/f08-agent/<时间戳>/summary.json`。如果某次运行已成功创建账户/授权但在创建任务前中断，可用 `-ResumeExisting` 仅恢复唯一匹配的合成账户并从后续步骤继续；若存在多个匹配账户，脚本拒绝继续。

## F03/F04 mock 候选 E2E

在本机隔离 phone-demo 中运行：

```powershell
.\scripts\phone-demo-record-image-e2e.ps1
```

该脚本默认 `-Mode mock`，仅使用 4×4 合成图和测试候选夹具。需要以真实图片走同一业务上传、授权、识别请求、Agent callback、患者候选确认闭环时，显式指定 `-Mode live` 并提供本机图片文件路径；diet/stool 分开验收可减少无关调用：

```powershell
.\scripts\phone-demo-record-image-e2e.ps1 -Mode live -RecognitionType stool -StoolImagePath 'D:\GutCare_Agent\test-data\synthetic-stool.png'
```

diet 路径使用 `-RecognitionType diet -DietImagePath '<本机合成或已授权图片>'`。`both` 需要分别提供 `-DietImagePath` 与 `-StoolImagePath`，会产生两次视觉调用。live 脚本关闭候选 fixture、将 provider 最大重试设为 0，并要求 Agent profile 配置为 live；摘要仅写模式、任务状态、候选类型/确认结果与耗时，不记录图片路径、图片字节、JWT、告知 token、密钥、prompt 或模型原文。live 结束时脚本会自动将 Agent profile 重启回 mock、清空容器 API Key，并恢复调用方 PowerShell 的环境变量；若重置失败会给出不含密钥的提示。仅使用测试/合成或已获授权的图片。候选若未产生，脚本会失败并保留稳定阶段信息，不会把空候选宣称为通过。Compose 的 retry 映射供演示脚本设为 0，常规启动默认仍为 2 次。

F08 演示同样支持 `-Mode mock|live`，默认 mock。默认 `-RequireAdvice $true` 保持原有 F08→F09 联合验收；要单独验收真实 Agent 的 F08，可显式传 `-RequireAdvice $false`。此模式只要求任务到达现有成功终态且患者查询可读到结果，不轮询 F09，也不将 F09 标为通过；摘要写入 `f09_advice_checked=false` 和实际 `patient_advice_count`（未查询时为 0）。

可选 `-IncludeMood` 会先从 phone-demo 当前启用的告知取得版本并授予 `mood_data_processing`、`mood_ai_sharing`，创建一条无备注的合成心情记录，再创建 F08 综合分析任务。授权告知未启用时会安全失败。脚本检查患者任务 DTO 的冻结摘要 `included_mood_record_count` 必须为 1，只有该检查通过才写入 `f14_mood_snapshot_verified=true`；不会记录心情正文或 Agent 原始输出。可组合两项选项执行 F08+F14、而不验收 F09：

```powershell
.\scripts\phone-demo-agent-f08-e2e.ps1 -Mode live -RequireAdvice $false -IncludeMood
```

live 需新建任务（不能使用 `-ResumeExisting`），并依赖本机 `.env.agent.local` 中配置的模型参数。仅使用合成数据；脱敏摘要不含冻结输入正文或模型原文。省略两个新参数时，脚本仍要求 F09 建议可由患者读取，与原默认断言一致。

如需分别验证单一业务类型，可运行 `-RecognitionType diet` 或 `-RecognitionType stool`；默认 `both` 会顺序执行两者。mock 模式固定的食物名称和 Bristol 类型只验证 dispatch、一次性图片读取、回调、候选状态和患者逐项确认，不代表真实图像识别。脚本通过业务 API 注册并验证合成账号、授予健康处理/敏感图片/第三方 AI 测试授权、取得 purpose-specific 告知、上传并关联图片、创建识别请求，再确认患者候选。摘要只保存 request ID、候选类型和决定状态，不保存邮箱、凭据、图片、候选文字或模型原始输出。

phone-demo API 的 `sensitive_image` 授权通过 `contracts/consent/consent-notices.json` 中独立的 test-only 版本及摘要哈希读取和校验；F03/F04 purpose-specific 告知继续由 `contracts/consent/record-image-recognition-notices.json` 校验。以上配置仅服务本机合成数据，不是生产法律文案或授权。

2026-10-21 本机 mock E2E 分别以单条 Diet 与单条 Stool 请求通过，均经患者 API 确认候选（HTTP 204）；摘要保存在被忽略的 `.demo-output/f03-f04-agent/`。Agent mock fixture 产生的是明确的合成候选，不可用于展示或描述真实识图能力。`-RecognitionType diet|stool` 可单独验证一种类型，默认 `both` 顺序执行两种。

## 停止与查看日志

```powershell
.\scripts\phone-demo-agent-logs.ps1 -Service analysis-dispatcher -Follow
.\scripts\phone-demo-agent-logs.ps1 -Service record-image-dispatcher -Follow
.\scripts\phone-demo-agent-logs.ps1 -Service agent -Follow
.\scripts\phone-demo-agent-down.ps1
```

停止 profile 会保留数据库、Agent SQLite 与其余 phone-demo 数据卷。完整 phone-demo 服务和数据生命周期仍由 `phone-demo-down.ps1` 管理；`-PurgeData` 会清除项目卷。

该拓扑仅适用于本机隔离 demo。不要发布 Agent 端口、使用真实患者数据或把此 profile 当作正式部署模板。F08 PostgreSQL 权限、锁与迁移验收仍以 T66–T71 及独立门禁为准；本地 mock E2E 单独记录，不能替代生产 Agent 验收。

本机集成证据（2026-10-21）：F08 mock task 到达 `partial`，患者任务查询可读回结果；Compose F08→F09 mock 路径已通过一次，患者 `/api/v1/advice` 可读到对应 task 的 1 条建议。空 F08 mock advice 时，Agent 仅在 `GCA_MODE=mock` 下使用基于冻结确认记录的非临床 record-management 测试夹具；live/replay 不启用，仍需患者确认。Diet mock 合成 E2E 通过候选 callback 和患者确认。更早 F04 mock 患者确认（HTTP 204）发生于 ADR-0024 前，保留为历史证据；ADR-0024 后 F04 Bristol 直接展示最小 mock E2E 通过（T153），不调用外部模型，不代表 Android UI/仪器、真实识图或生产验收。首轮视觉 live 诊断发现 Agent 只连接 `internal: true` 网络，容器内 DNS 失败；加入仅 Agent 使用的 `agent-egress` 后，容器内 provider `/models` 返回 200。随后用一张仓库合成餐食图执行一次 F03 live 冒烟，`GCA_MAX_RETRIES=0`，15.49 秒成功返回 3 个候选；诊断模式丢弃模型原始输出，未记录密钥、prompt 或图片内容。该结果只证明 F03 视觉调用与候选映射可用，不代表识别准确率、F04 live 或生产验收。冒烟后应恢复 `GCA_MODE=mock`、`GCA_TEST_IMAGE_CANDIDATES=0`。Docker Hub 不可达时 NoBuild 依赖已有镜像与 demo-only 只读源码挂载。来源仓库未提供 LICENSE，授权确认前公开推送阻塞。
