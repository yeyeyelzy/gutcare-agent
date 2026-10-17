# GutCare 移动端

uni-app + Vue 3 + TypeScript strict + Pinia 的 Android/iOS 客户端基础工程。患者端交付目标是原生 APP；不提供 H5 发布脚本。页面内容目前是路由占位，不能作为最终 UI 验收。

## 命令

- `pnpm typecheck`：Vue / TypeScript 静态检查
- `pnpm openapi:generate`：从冻结 OpenAPI auth/profile operation 生成 TypeScript 类型
- `pnpm openapi:check`：重新过滤并生成后与受检入库类型逐字节比对；`pnpm check` 和仓库 lint 门禁执行此检查
- `pnpm test`：API、会话、注册草稿、邮箱验证、导航与启动状态单元测试
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

## B01-1 认证和导航基础

- `openapi-typescript@7.13.0` 与 `yaml@2.9.1` 均精确锁定。生成器只从权威 OpenAPI `operationId` 过滤 `register`、`verifyEmail`、`login`、`refreshSession`、`logout`、密码重置及 `getMyProfile`/`updateMyProfile`，并断言必需 operationId 集合各出现一次；schema/DTO 不手写。`AuthApi` 登录/注销委托 B00b `SessionService`，不会重复实现 refresh。
- `AuthApi`、`ProfileApi` 使用生成的请求/响应类型。注册请求在运行时也拒绝额外键。
- 第 22 页仅以内存 Pinia store 保存邮箱、密码、确认密码和隐私选择；第 17 页进入后只有明确同意健康数据处理才会开放出生年份字段；单独切换撤销同意只清出生年份，顶部/系统返回回第 22 页并保留草稿以供编辑。选择“暂不同意并退出注册”会清除整个草稿并回到登录；离开注册流程时路由层也清除草稿。提交请求显式构造 OpenAPI 六字段，成功受理后清除密码并进入邮箱验证页。验证令牌只由用户输入、只保存在页面内存、不放 URL/持久化；验证 204 后清草稿并回到登录。测试告知来自唯一 JSON 制品；当前开发/测试制品在 production mode 下 fail closed。
- 路由注册表有 public/authenticated 元数据；仅允许白名单的命名路由 `today` 作为进程内 `returnTo`。导航拦截器与首页 `v-if` 双重阻止认证/资料尚未完成时显示受保护页面。启动/登录恢复固定执行 session restore → `GET /patients/me`：200 才进入今日；401 清会话返回登录；404 清会话进入不可继续的资料一致性错误态并展示 `request_id`；不会伪造资料或进入 `/onboarding/profile`。
- Access Token 和患者资料仅保存在 Pinia 内存；原生 Refresh Token 继续由 B00b SecureTokenStore 管理。登出调用 `POST /auth/logout` 后清除 returnTo，并用 `reLaunch(login)` 清空页面栈。
- RFC 9457 `ProblemDetails` 从生成的 OpenAPI `components.schemas.Problem` 派生；客户端稳定错误类型只封装 kind/status/code/requestId，不另行复制契约字段。
- 单元测试覆盖 API operation 路径与请求体、注册隐私/健康同意与六字段边界、返回保留草稿、取消/离开流程时清理、邮箱验证成功/失败、未认证深链阻断、状态机 200/401/404/暂时网络失败和注销清栈语义。此处为基础流程而非最终高保真注册/认证 UI 或业务首页。

生成器按当前 B01-1 要求筛选 auth/profile operation；完整 OpenAPI 另有 `GET /symptom-records/{record_id}/status-history` 的 200 `application/json: null`，会使全量 openapi-typescript 生成失败。该非本切片契约技术债登记在前端联调计划中；本任务不修改冻结契约。

## B01-2 公开认证页面

已实现的公开认证入口：欢迎页、邮箱登录、注册账户（22）、健康处理同意/出生年份（17）、邮箱验证、找回密码、密码重置和资料一致性错误页。共用 `AuthScaffold`、`GcButton`、`GcField`、`NoticeCard` 与 `InlineProblem`；表单字段有关联标签、错误描述、稳定 `data-testid`，交互控件满足至少 44px 触控尺寸。认证失败文案按状态安全呈现，401 不区分账户/密码/验证，429/5xx/离线错误可见 request_id。

注册仍按第 22 页到第 17 页执行：前者只保存内存草稿且不发请求；隐私政策与健康处理告知分别显示，只有后者明确同意时才显示出生年份输入，并最终调用单次注册 API。找回密码 request 提示不透露账户是否存在；reset token 只能手动输入，不接受 URL/query 参数，不写入持久化；成功后清除敏感表单并返回登录。未实现手机号/SMS、姓名/性别/报告字段或业务/AI页面。欢迎和邮件图形由 CSS/code-native 图形绘制，没有使用来源/授权未确认的原型图片。

公开认证页面采用 430px 原型宽度基准、安全区可滚动布局、48px/16px 圆角主按钮、邮箱/密码图标输入行与无外层大表单卡片；欢迎页以内联 SVG 和三条 feature 文案替代隔离原型图像，并以横排注册/登录作为入口。启动/资料加载安全错误保留 transport kind、status、code 与 request_id；一致性错误支持说明入口只指导用户经官方渠道手动联系，不自动发送数据。router 对任何路径上的 token/access_token/refresh_token/password/new_password query 先清空注册草稿再返回登录。

## B01-3 本人资料与会话安全

`/pages/profile/index` 是认证路由，资料读取和编辑只使用 `/patients/me`；PATCH 以当前 `profile_version` 为准，仅提交患者改动过的 `nickname`、`birth_year`、`timezone` 字段，清空昵称发送 `null`。409 不自动覆盖，先重新 GET 并向患者展示最新值/拟改值，由患者确认后再重试。资料 404 会清会话、保留 request_id 并跳转资料一致性错误页。

退出有二次确认和防重复调用。刷新令牌删除和服务端 logout 都会尝试；Access Token 与 profile 内存态始终清除，受保护页面栈及 `returnTo` 被清空后 reLaunch 到登录页。若本机安全存储拒绝删除，登录页显示原生安全存储错误码，不把 token 放入 UI 状态或日志。无效 refresh 对过期/冻结账户统一按认证失败处理，不恢复旧 returnTo。双患者资料隔离和 profile 乐观锁由后端 T49/PG18 集成证据覆盖；客户端不提交 patient id。

当前组件状态映射、表单/服务流程和页面约束测试、类型检查与 Android/iOS CLI 导出可自动验证；这不构成真机视觉签收。当前未生成或签收 430×880 像素基线；Android/iOS 真机截图、键盘/安全区/动态字号检查、逐页像素对比 SSIM ≥0.95，以及经法律批准的生产注册告知，仍是发布门禁。无患者 Web/H5 发布目标。
