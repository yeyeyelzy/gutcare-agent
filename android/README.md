# GutCare Android

`android/` 是当前唯一的患者端工程，使用 Kotlin、Jetpack Compose、Material 3 和 Navigation Compose。请用 **Android Studio** 打开本目录并进行开发、运行与验收；旧 `../app/` 是只读归档。APP 仅通过业务 API 访问数据，绝不连接 Agent、数据库或对象存储。

## 评委演示：从 clone 到运行

仅使用合成演示账号与数据。前置条件：Windows、Docker Desktop/Compose v2、Android Studio（内置 JDK 17 或 JDK 17）、Android SDK Platform 36、Build Tools 36.0.0，及一个可运行的 Android 模拟器。

1. 在仓库根目录启动隔离后端：

   ```powershell
   .\scripts\phone-demo-up.ps1
   Invoke-WebRequest http://127.0.0.1:8000/health/live
   ```

   成功响应表示 phone-demo API 已存活。该脚本生成被 Git 忽略的本机 `phone-demo.env`，不会打印任何密钥；首次启动还会准备固定版本的本地 MinIO 测试镜像和 MinIO Client，并等待 MinIO、ClamAV 健康及演示 bucket/应用用户初始化完成。MinIO root 凭据只用于一次性初始化容器；API 使用随机应用凭据，且只对演示 bucket 拥有必要的对象读写/删除与版本列表权限。对象存储与扫描器仅在 phone-demo 内网可见。

   如需独立验收 F02 文件服务，可在仓库根目录执行 `.\scripts\phone-demo-f02-e2e.ps1`。脚本会注册全新合成账号，从本机 Mailpit 读取验证令牌（不输出令牌），生成内存中的 2×2 合成 JPEG，并验证授权、上传、真实 ClamAV clean 状态、`store_only` 档案查询及授权下载。该脚本验证业务 API 文件链路，不代表 Android 客户端上传、analyze 或 Agent 候选 E2E。数据保留在 phone-demo 卷中；确认要删除本项目所有演示数据时执行 `.\scripts\phone-demo-down.ps1 -PurgeData`。

   如需本机覆盖 P1 非智能体 API 链路，可执行 `.\scripts\phone-demo-p1-e2e.ps1`。该脚本只创建随机合成邮箱账号，并验证用药计划/今日打卡/历史/409、`test_only` 风险规则与跨账号权限、趋势授权态与历史分页、分析任务 preview/create/status/cancel/retry、建议空态、授权授予/撤回及隔离账号注销状态。脚本不启动智能体、不伪造分析或建议结果，不打印账号、令牌、请求正文或 URL/query；测试数据会留在演示数据库中。风险提示明确标记为“演示测试规则（非临床）”，仅在 `compose.phone-demo.yaml` 显式 opt-in；正式 `compose.yaml` 不启用或种入此规则。

   2. 打开 Android Studio，选择 **Open**，定位到 `<clone-directory>\android`。完成 Gradle Sync 后，从 Device Manager 启动模拟器，选择 `app` Debug 变体并点击 Run。Debug 默认连接 `http://10.0.2.2:8000/api/v1/`；`10.0.2.2` 是 Android 模拟器访问 Windows 宿主机 loopback 的专用地址。

3. 在 APP 中演示：注册新的演示邮箱和密码 → 在 Mailpit 读取该账号验证邮件中的 token → 回到 APP 验证、登录并完成资料读取 → 从“记录”进入健康档案演示 store-only 存档，再新增、查看、编辑和删除饮食、排便、症状、心情记录 → 退出登录。F02 解析/候选 UI 已实现，但真实候选依赖 Agent 服务；本演示不触发 analyze 或 Agent 候选，不展示未验收的 Agent 分析/回调或医疗结论。

4. F02 的档案、解析/候选交互和逐字段决定已有原生实现；本演示只使用 store-only 流程，尚无真实 Agent 候选产出和 Android 上传 E2E 最终证据。真实 phone-demo E2E 验证的是业务 API 上传、ClamAV clean、档案查询及授权下载，不是 Agent 联调。运行环境的 MinIO/ClamAV 仅供隔离演示，API 需先获得 `health_data_processing` 授权。停止服务保留数据库、对象和邮件数据；`-PurgeData` 会永久删除该 phone-demo 项目的所有数据卷。

5. 结束后在仓库根目录停止演示服务：

   ```powershell
   .\scripts\phone-demo-down.ps1
   ```

   如明确需要删除**本项目**的演示卷，才使用 `-PurgeData`；它不可恢复。

## 验收与故障排查

- Gradle Sync 或 SDK 报错：在 Android Studio SDK Manager 安装 Android 36 platform 和 Build Tools 36.0.0，并确认 Gradle JDK 为 17。
- APP 显示网络错误：确认 Docker Desktop 正在运行，执行 `Invoke-WebRequest http://127.0.0.1:8000/health/live`；模拟器必须使用默认 `10.0.2.2`，不能配置为 `localhost`。
- 看不到验证邮件：确认 Mailpit 为 `http://127.0.0.1:8025`，检查所注册的演示邮箱；不要把 token 写入日志、截图或提交。
- 启动脚本失败：先运行 `.\scripts\phone-demo-up.ps1 -ConfigOnly`；再用 `docker compose -f compose.phone-demo.yaml --env-file phone-demo.env -p gutcare-phone-demo logs` 检查本项目日志。
- 避免同时运行多个 Gradle 验证。需要命令行校验时，在本目录执行 `.\verify.ps1`；它使用临时 ASCII 路径以规避 Windows 非 ASCII 工作目录问题。

当前映射、测试证据与未交付范围以 [../docs/Android页面-功能-API-测试映射.md](../docs/Android页面-功能-API-测试映射.md) 为准。视觉验收门槛为至少 80% 原型一致且无明显错误；本 README 不声称未归档的视觉或真机验收已完成。

截至 2026-10-20，可追溯历史验证为 backend 208 项通过、30 项条件跳过，Android JVM 112 项和模拟器 46 项通过；当前最终门禁复验尚未完成，数字待最终门禁回填。认证最新复验为两项中 1 通过、1 失败（注册提交 `VALIDATION_ERROR`）。F02 解析/候选原生流程和 F03/F04 附件 UI 已有实现；Agent 真实解析结果与 Android 附件上传 E2E 尚待各自证据。P1 phone-demo API 摘要位于 `build/emulator-evidence/phone-demo-p1-20261020/summary.md`，不包含 Agent 执行。历史探索性分数不构成视觉验收；逐页均须达到至少 80% 且无明显视觉错误。
