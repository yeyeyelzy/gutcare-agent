# 本机 phone-demo F08 Agent（默认 mock）

来源：Agent 快照来自 [caoyimiao0625-alt/gutcare-agents](https://github.com/caoyimiao0625-alt/gutcare-agents)，导入 commit `40ec9f434632da587a66f4b10bf0e5e72693aa78`，详见 `../agent/PROVENANCE.md`。该来源未附 LICENSE，授权与素材使用状态待用户选择。

本指南为 `compose.phone-demo.yaml` 增加的可选 `agent` profile，验证 F08 的本地协议路径：业务 API 创建冻结任务，唯一 analysis dispatcher claim 并派发，独立 Agent 读取快照并回调，患者查询任务终态。没有 `.env.agent.local` 时默认 `mock`，不调用模型且不需要模型密钥。仓库提供可跟踪模板 `.env.agent.example` 和被 Git 忽略的本机文件 `.env.agent.local`；本机模板显式设为 `live`，API Key 为空，启动脚本会在启动服务前拒绝缺少 key、base URL 或模型名的配置。真实模型验证只使用本地合成 F08 数据，不构成医学输出或真实 Agent 质量验收。当前只有 F08 具备完整主仓本机 Agent 路径证据；F03/F04 图像候选回调、F09 独立建议回调尚未完成，不纳入完成范围。

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

启动脚本沿用现有 `phone-demo.env`，首次启动时随机生成并保存两枚不同的本地 token，且不打印它们。`AGENT_INTERNAL_TOKEN` 仅供 dispatcher 调 Agent 入站接口；`AGENT_SERVICE_TOKEN` 仅供 Agent/dispatcher 访问业务内部 API，必须与业务 API 的 `AGENT_SERVICE_TOKEN` 相同。两者都不能复用生产凭据。

`api` 使用单独的 `ANALYSIS_WORKER_DATABASE_URL` 接入既有最小权限 analysis worker PostgreSQL role。dispatcher 本身没有数据库 URL 或数据库凭据，且只接入 `agent_internal` 网络；Agent 与 dispatcher 也只接入该网络，API 另接入 `agent_internal` 供其提供 HTTP 服务。PostgreSQL、Redis、MinIO 和其他基础服务均不在这个网络上。Agent 只获得两个内部 HTTP token，使用独立的 `phone_demo_agent_sqlite` 卷保存其本机任务 journal；它不获得业务数据库凭据。dispatcher 由业务 `/claim` API 唯一领取任务，并将最小派发 envelope 发到 Agent；Agent 再按 task ID 读取冻结快照并回调。

E2E 脚本创建随机合成邮箱、完成 Mailpit 邮箱验证，记录 `third_party_ai` 测试授权，新增一条结构化症状记录并发起综合分析。脚本仅输出阶段、HTTP 状态、task ID 和任务状态，不输出邮箱、密码、患者访问令牌、内部 token、记录正文或 Agent 原始结果。脱敏摘要写入 `.demo-output/f08-agent/<时间戳>/summary.json`。如果某次运行已成功创建账户/授权但在创建任务前中断，可用 `-ResumeExisting` 仅恢复唯一匹配的合成账户并从后续步骤继续；若存在多个匹配账户，脚本拒绝继续。

## 停止与查看日志

```powershell
.\scripts\phone-demo-agent-logs.ps1 -Service analysis-dispatcher -Follow
.\scripts\phone-demo-agent-logs.ps1 -Service agent -Follow
.\scripts\phone-demo-agent-down.ps1
```

停止 profile 会保留数据库、Agent SQLite 与其余 phone-demo 数据卷。完整 phone-demo 服务和数据生命周期仍由 `phone-demo-down.ps1` 管理；`-PurgeData` 会清除项目卷。

该拓扑仅适用于本机隔离 demo。不要发布 Agent 端口、使用真实患者数据或把此 profile 当作正式部署模板。F08 PostgreSQL 权限、锁与迁移验收仍以 T66–T71 及独立门禁为准；本地 mock E2E 单独记录，不能替代生产 Agent 验收。

本机执行证据（2026-10-21）：E2E 为 `passed`，Agent mock 返回 `partial` 且患者查询读回 `result_present=true`。可提交脱敏摘要见 `evidence/F08-phone-demo-mock-E2E-20261021.md`。原始 `.demo-output/f08-agent/20261021-005531/summary.json` 被 `.gitignore` 排除，仅为本机证据。由于 Docker Hub 当时不可达，Agent 容器使用本机已缓存的 Python 3.13 基础镜像构建；合成 F08 输入不含 PDF，因此跳过了仅供 PDF 处理的 pypdf/Poppler 安装。这验证了当前 Agent 的 F08 mock 路径，不验证标准 Python 3.12 镜像构建或 PDF 输入路径。来源仓库未提供 LICENSE，授权确认前公开推送阻塞。
