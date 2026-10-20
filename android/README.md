# GutCare Android

`android/` 是当前唯一的患者端工程，使用 Kotlin、Jetpack Compose、Material 3 和 Navigation Compose。请用 **Android Studio** 打开本目录并进行开发、运行与验收；旧 `../app/` 是只读归档。APP 仅通过业务 API 访问数据，绝不连接 Agent、数据库或对象存储。

## 评委演示：从 clone 到运行

仅使用合成演示账号与数据。前置条件：Windows、Docker Desktop/Compose v2、Android Studio（内置 JDK 17 或 JDK 17）、Android SDK Platform 36、Build Tools 36.0.0，及一个可运行的 Android 模拟器。

1. 在仓库根目录启动隔离后端：

   ```powershell
   .\scripts\phone-demo-up.ps1
   Invoke-WebRequest http://127.0.0.1:8000/health/live
   ```

   成功响应表示 phone-demo API 已存活。该脚本生成被 Git 忽略的本机 `phone-demo.env`，不会打印任何密钥。

2. 打开 Android Studio，选择 **Open**，定位到 `<clone-directory>\android`。完成 Gradle Sync 后，从 Device Manager 启动模拟器，选择 `app` Debug 变体并点击 Run。Debug 默认连接 `http://10.0.2.2:8000/api/v1/`；`10.0.2.2` 是 Android 模拟器访问 Windows 宿主机 loopback 的专用地址。

3. 在 APP 中演示：注册一个新的演示邮箱和密码 → 在浏览器打开 `http://127.0.0.1:8025` 的 Mailpit，复制该账号验证邮件中的 token → 回到 APP 验证、登录并完成资料读取 → 从“记录”新增、查看、编辑和删除饮食、排便、症状、心情记录 → 退出登录。此流程只演示已验收的手工记录切片；不演示未验收的文件档案、图片识别、Agent 分析或医疗结论。

4. 结束后在仓库根目录停止演示服务：

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
