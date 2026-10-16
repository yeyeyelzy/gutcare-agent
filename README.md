# GutCare Agent

GutCare Agent 是面向已确诊消化道疾病患者的 Android/iOS 健康管理 APP。本仓库根目录固定为 `D:\GutCare_Agent`。

正式开发前先阅读：

1. `docs/README.md`：文档索引、权威性与冻结规则。
2. `AGENTS.md`：编码 Agent 的强制执行约束。
3. `docs/详细功能设计.md`：F01–F13 行为与验收。
4. `docs/技术方案.md`、`docs/数据库设计方案.md`：实现与数据约束。
5. `contracts/`：机器可读接口契约。

当前状态：文档基线 V1.1，尚未进入生产开发。真实医学规则在专业审核完成前不得启用。

## 本地基础环境

项目脚本默认使用仓库 `.runtime/` 下的 Python 3.13、uv 0.13.1、Node 22，以及由 APP `package.json` 固定的 pnpm 10.28.0。若宿主机已手动安装 uv，可在项目根目录执行以下命令运行后端依赖同步和完整门禁：

```powershell
$env:GUTCARE_UV = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
& '.\scripts\backend-verify.ps1'
```

`backend-verify.ps1` 使用仓库 Python 3.13，按 `backend/uv.lock` 执行 locked sync，再依次运行 Ruff 格式检查、Ruff 静态检查、mypy 和 pytest；任一步失败都会中止且不会输出通过提示。完整前后端工作区仍使用 `./scripts/install-app.ps1`、`./scripts/lint.ps1` 和 `./scripts/test.ps1`；APP 依赖通过根目录 `pnpm-lock.yaml` 锁定。

Compose 配置要求 Docker Compose v2。先人工创建本地 `.env`，使用互不相同的唯一随机密码，并填入审核过的 MinIO 源码 commit 与本地构建镜像摘要。`.env.example` 只列字段，不含可运行凭据。`./scripts/bootstrap.ps1` 仅校验配置与本地 MinIO 镜像，不拉取、构建或启动镜像；`./scripts/dev-up.ps1` 才会启动本地依赖，`./scripts/dev-down.ps1` 停止服务但保留卷。

Docker 不可用时，基础设施校验会明确报告环境阻塞；不得将该状态记为 Compose 或服务启动通过。不要用未审核的镜像替代 MinIO 源码构建基线。

当前 Compose 仅定义本地数据/网关依赖；API、Worker、Beat 与 agent-mock 容器尚未纳入，因为仓库目前没有对应可构建服务镜像。Caddy 的 `/api` 上游因此要等 API 服务加入 Compose 后才能连通；现阶段不能视为完整 B00 启动拓扑。
