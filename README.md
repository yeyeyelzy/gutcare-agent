# GutCare Agent

GutCare 是面向已确诊消化道疾病患者的健康管理项目。患者端当前**仅为原生 Android APP**：唯一开发与验收环境是 Android Studio。`android/` 是唯一客户端入口；历史 `app/` 目录只读归档，不参与构建、演示或验收。当前不开发 iOS、患者 H5 或 Web 替代端。

先阅读 [docs/README.md](docs/README.md) 和 [AGENTS.md](AGENTS.md)。已采纳 ADR、OpenAPI 与数据字典优先于既有代码。APP 只调用业务 API，绝不直连 Agent、数据库、对象存储或 MinIO 管理端。

## 当前可演示范围

已归档证据覆盖 Android 原生认证 Repository 的注册、邮箱验证、登录、资料读取、refresh、退出，以及饮食、排便、症状、心情的手工 CRUD、分页、症状状态历史、409 与登出后 401。它不代表全部页面或功能已验收。F02、图片识别、分析/建议、风险、趋势、用药、活动、通知、隐私中心等仍按 [Android 页面—功能—API—测试映射](docs/Android页面-功能-API-测试映射.md) 的逐项状态执行。

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

该环境仅用于 local/test/demo，不是生产部署，也不包含对象存储/病毒扫描、文件上传下载、Agent 或其他未列出的依赖。
