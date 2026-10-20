# GutCare Agent

GutCare 是面向已确诊消化道疾病患者的健康管理项目。患者端当前**仅为原生 Android APP**：唯一开发与验收环境是 Android Studio。`android/` 是唯一客户端入口；历史 `app/` 目录只读归档，不参与构建、演示或验收。当前不开发 iOS、患者 H5 或 Web 替代端。

先阅读 [docs/README.md](docs/README.md) 和 [AGENTS.md](AGENTS.md)。已采纳 ADR、OpenAPI 与数据字典优先于既有代码。APP 只调用业务 API，绝不直连 Agent、数据库、对象存储或 MinIO 管理端。

## 当前可演示范围

本地证据覆盖 Android 原生认证 Repository 的注册、邮箱验证、登录、资料读取、refresh、退出，以及饮食、排便、症状、心情的手工 CRUD、分页、症状状态历史、409 与登出后 401；F02 档案页面已接入 store-only 上传，并通过隔离 phone-demo 的真实 ClamAV clean、档案查询和授权下载 E2E。F02 证据不包含 analyze、Agent 候选产生或 Agent 回调。其余分析/建议、风险、趋势、用药、活动、通知、隐私中心等仍按 [Android 页面—功能—API—测试映射](docs/Android页面-功能-API-测试映射.md) 的逐项状态执行。

视觉验收目标为与指定原型**至少 80% 一致且无明显错误**；每页仍须有可追溯截图比较证据。模拟器是开发验收环境；发布前真机证据另行要求。

## 评委快速开始（Windows）

前置条件：Docker Desktop（含 Compose v2）、Android Studio（JDK 17、Android SDK Platform/Build Tools 36）和可用 Android 模拟器。使用全新合成账号与演示数据；不要输入真实患者数据或提交本地 `phone-demo.env`。

在仓库根目录启动隔离的 phone-demo 后端：

```powershell
.\scripts\phone-demo-up.ps1
Invoke-WebRequest http://127.0.0.1:8000/health/live
```

然后在 Android Studio 选择 **Open** 并打开 `<clone-directory>\android`；等待 Gradle Sync 后启动一个模拟器，并以 Debug 运行 `app`。Debug 默认 API 是 `http://10.0.2.2:8000/api/v1/`，它从模拟器访问上一步的本机 phone-demo。详细的演示步骤、可复制命令和排障见 [android/README.md](android/README.md)。

演示结束后：

```powershell
.\scripts\phone-demo-down.ps1
```

该环境仅用于 local/test/demo，不是生产部署。它包含隔离的 PostgreSQL、Redis、Mailpit、私有 MinIO 与 ClamAV；MinIO root 凭据仅用于一次性初始化容器，API 使用 `phone-demo.env` 中独立随机生成的应用凭据，权限仅覆盖演示 bucket 的对象读写/删除和版本列表。MinIO 初始化镜像使用 `.downloads/phone-demo-minio-init-context` 独立最小构建上下文，不会将仓库根目录、`phone-demo.env` 或运行时缓存发送给 Docker daemon。启动脚本在本机生成被忽略的密钥文件，并在 MinIO 健康后初始化演示 bucket 与最小权限用户。只有 ClamAV 扫描 clean 的对象才会被标为可用。F02 的原生档案 UI 与 `store_only` 上传已实现；隔离 phone-demo E2E 覆盖真实 ClamAV clean、档案元数据和授权下载，不覆盖 analyze、候选生成或 Agent 回调。不要把真实病历用于演示。`phone-demo-down.ps1` 保留项目数据卷；仅在确认要清除本项目演示数据时使用 `-PurgeData`，该操作也会删除演示文件对象。
