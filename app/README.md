# GutCare 移动端

uni-app + Vue 3 + TypeScript strict + Pinia 的 Android/iOS 客户端基础工程。患者端交付目标是原生 APP；不提供 H5 发布脚本。页面内容目前是路由占位，不能作为最终 UI 验收。

## 命令

- `pnpm typecheck`：Vue / TypeScript 静态检查
- `pnpm test`：API 基础单元测试
- `pnpm build:android`：uni-app Android 原生构建
- `pnpm build:ios`：uni-app iOS 原生构建
- `pnpm dev:app`：使用 uni-app App 运行目标启动调试

构建环境基线为 Node.js 22 LTS 和 pnpm 10.28.0。先复制 `.env.example` 为 `.env` 并设置 `VITE_API_BASE_URL`。配置必须是 HTTPS 地址，路径可以省略或为 `/api/v1`，最终会规范化为 `/api/v1`；仅开发服务器允许 `http://localhost`、`127.0.0.1` 或 `[::1]`。空值、`example.invalid`、凭据、查询参数和其他路径会在启动/构建时被拒绝，错误不会回显配置内容。依赖以根目录 workspace `pnpm-lock.yaml` 锁定。

## 安全存储状态

`NativeSecureTokenStoreUnavailable` 是当前生产适配占位：所有操作均拒绝执行，因此冷启动会话恢复保持关闭，且登录令牌不能被持久化。集成自有 `gutcare-secure-store` UTS 插件（iOS Keychain、Android Keystore 保护的应用私有密文）后，才能启用 Refresh Token 恢复。Refresh Token 不得写入 `uni.setStorage`、Pinia 持久化插件或日志。Access Token 仅进入 Pinia 内存态。`MemorySecureTokenStore` 仅用于单元测试。

## 范围

基础设施包含启动/登录/首页路由壳、唯一 `RequestClient` 装配、Problem Details 错误映射、401 refresh 单飞协调及 `SessionService`。页面不直接发起网络请求。最终页面、视觉令牌取值和认证交互等待 UI 交付及安全存储原生插件。
