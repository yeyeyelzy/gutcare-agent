# GutCare 移动端

uni-app + Vue 3 + TypeScript strict + Pinia 的 Android/iOS 客户端基础工程。患者端交付目标是原生 APP；不提供 H5 发布脚本。页面内容目前是路由占位，不能作为最终 UI 验收。

## 命令

- `pnpm typecheck`：Vue / TypeScript 静态检查
- `pnpm test`：API 基础单元测试
- `pnpm build:android`：生成 Android 平台的 HBuilderX 导入工程
- `pnpm build:ios`：生成 iOS 平台的 HBuilderX 导入工程
- `pnpm dev:app`：使用 uni-app App 运行目标启动调试

构建环境基线为 Node.js 22 LTS 和 pnpm 10.28.0。先复制 `.env.example` 为 `.env` 并设置 `VITE_API_BASE_URL`。配置必须是 HTTPS 地址，路径可以省略或为 `/api/v1`，最终会规范化为 `/api/v1`；仅开发服务器允许 `http://localhost`、`127.0.0.1` 或 `[::1]`。空值、`example.invalid`、凭据、查询参数和其他路径会在启动/构建时被拒绝，错误不会回显配置内容。依赖以根目录 workspace `pnpm-lock.yaml` 锁定。

## 安全存储实现源码

`uni_modules/gutcare-secure-store` 提供生产适配源码，用于持久化 Refresh Token；当前尚未完成原生编译、签名、安装或真机验收，未通过发布门禁前不能视为已验证的生产能力。不使用 `uni.setStorage` 或 Pinia 持久化。

- Android：随机 IV 的 AES-256/GCM/NoPadding 加密；不可导出的密钥由 Android Keystore 管理。版本化密文 envelope 仅写入 `Context.noBackupFilesDir`，并通过同目录临时文件、同步写入和原子替换更新。`noBackupFilesDir` 的内容由 Android Auto Backup 排除。应用卸载后私有文件和 Keystore key 均由系统移除。
- iOS：Keychain generic-password 项，固定 service/account，`kSecAttrAccessibleWhenUnlockedThisDeviceOnly` 且 `kSecAttrSynchronizable=false`。仅存储 Keychain 值，不复制到普通文件。Application Support 内有不含凭据的安装标记，并设置为备份排除；标记丢失时删除可能遗留的同 service/account Keychain 项。Keychain 值仅在设备解锁后可访问，不迁移到其他设备。
- 两端统一 `DEVICE_LOCKED`、`CORRUPT_DATA`、`KEY_INVALIDATED`、`UNSUPPORTED_PLATFORM`、`INVALID_VALUE`、`SECURE_STORAGE_FAILED` 错误码。锁定错误保留持久令牌且清除进程内 access 状态；密文/密钥不可恢复或其他存储错误会清理本地会话并要求重新登录。Refresh Token 轮换必须先持久化成功，之后才发布新 Access Token。退出登录会尝试本地删除并始终清除内存会话，也会尝试服务端注销；若本地安全存储删除失败，`logout()` 会传播稳定存储错误，但不能保证持久令牌已删除，调用方必须将本次登出显示为未完全完成并触发后续重新认证处理。
- Web 与其他未实现平台一律返回 `UNSUPPORTED_PLATFORM`；不会降级到普通 storage。`MemorySecureTokenStore` 仅由单元测试显式注入。

## 原生构建与真机门禁

UTS 插件需由 DCloud 支持的 HBuilderX 原生构建链处理；DCloud 文档明确指出 uni-app UTS 插件目前不支持 CLI 创建/使用。为现有 Vite CLI 路径显式锁定匹配版本 `@dcloudio/uni-uts-v1@3.0.0-4060620250520001`，只能让 CLI 执行其可用的预处理/导出流程，不能改变该路径非官方支持的状态。`scripts/app-build.ps1` 检查 UTS/模块编译诊断和预期 HBuilderX 导入文件，但 CLI 输出 `dist/build/app` 及 UTS 描述文件不等同于 APK/IPA、Android/iOS 原生 UTS 编译、签名或设备验证。uni CLI 可能在出现 UTS 语法错误时仍返回 0，脚本因此也扫描完整输出。Android 需在 HBuilderX 中构建包含此 UTS 插件的自定义基座并在真机验证；iOS 原生编译和运行需 macOS + Xcode，设备安装还需 Apple 开发者签名证书及 provisioning profile。当前仓库未提供签名材料，也未记录 Android 或 iOS 真机证据，不得据 CLI 导出结果宣称原生安全存储已经验收。

自动化测试覆盖了 Keychain 写入状态决策（duplicate→update→not-found→retry-add→duplicate→retry-update）、未找到不能假成功及删除幂等规则；该纯逻辑测试不调用 iOS Security 原生 API。发布前还必须真机验证：原生插件可编译且未记录令牌；set/get/has/remove 持久化和退出清理（包括 Keychain 更新竞态及同步性/可访问属性）；iOS 锁屏后返回 `DEVICE_LOCKED` 且解锁后仍可读取；密文损坏/Keystore key 丢失后清理并要求重新登录；Android 云备份与设备迁移不携带令牌文件；iOS 卸载重装清除遗留 Keychain 值、恢复到另一设备不迁移 Keychain；Web/unsupported target fail-closed。

## 范围

基础设施包含启动/登录/首页路由壳、唯一 `RequestClient` 装配、Problem Details 错误映射、401 refresh 单飞协调及 `SessionService`。页面不直接发起网络请求。最终页面和视觉令牌取值等待 UI 交付；认证流程接入与原生安全存储双端验证也尚未完成。
