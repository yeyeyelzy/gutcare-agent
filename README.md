# GutCare 竞赛交付源码

GutCare 是面向已确诊消化道疾病患者的健康管理系统。患者端为原生 Android APP，业务后端为 FastAPI 模块化单体，智能体作为独立服务运行。客户端只访问业务 API，不直连数据库、对象存储或智能体服务。

## 可运行程序包

竞赛第 4 项可运行程序包位于 [`dist/GutCare-Competition-20261023.zip`](dist/GutCare-Competition-20261023.zip)，校验值见同目录 `.sha256` 文件。ZIP 内含 Android Studio 工程、Debug APK、后端与智能体源码、Compose 编排、一键启动/停止/校验脚本及部署说明。

Windows 10/11 安装并启动 Docker Desktop 后，解压 ZIP，在包根目录运行：

```powershell
.\Verify-GutCarePackage.ps1
.\Start-GutCareDemo.ps1
```

2026-10-23 的本机验收结果为：Compose 22/22 启动完成，API、Agent 和三个 dispatcher 健康，`GET /health/live` 返回 HTTP 200，Agent 运行模式为 `mock`。详细前置条件、Android 安装方式、停止与排障说明见[可运行程序包、部署与环境配置说明](docs/可运行程序包、部署与环境配置说明.md)。

## 源码结构

- `android/`：原生 Android 客户端；唯一客户端开发与验收环境为 Android Studio。
- `backend/`：FastAPI 业务后端、Alembic 迁移及后台任务。
- `agent/`：独立智能体服务、提示词、适配器与测试。
- `contracts/`：OpenAPI、Agent 回调及授权告知等冻结契约。
- `infra/`、`compose.phone-demo.yaml`：本地隔离演示环境。
- `scripts/`：检查、测试、启动和演示脚本。
- `docs/`：系统设计、部署、合规边界及竞赛提交说明。

CI 在 push 和 pull request 时执行 Python 格式/类型检查、单元与契约测试、Android Debug 构建/单元测试/lint、授权告知校验和 PowerShell 语法检查。

## 使用边界

本项目仅用于竞赛评审与本地隔离演示，使用合成测试资料；不得导入真实患者数据，也不构成诊断、处方或生产医疗服务。模型候选必须经过用户逐项确认后才能成为记录事实。组件、第三方模型、数据来源及 Agent 发布授权边界见[开源组件、第三方模型与数据使用说明](docs/开源组件、第三方模型与数据使用说明.md)和 [`agent/PROVENANCE.md`](agent/PROVENANCE.md)。
