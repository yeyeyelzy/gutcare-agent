# GutCare 移动端

uni-app + Vue 3 + TypeScript strict + Pinia 的 Android/iOS 客户端。患者端交付目标是原生 APP；不提供 H5 发布脚本。认证、本人资料、设置导航枢纽、四个 Tab 根页，以及 F03 饮食、F04 排便、F05 症状、F07 活动、F08 分析任务与结果、F09 建议工作区、F10 风险提示、F11 历史/趋势、F12 站内通知、F13 注销/数据导出、F14 心情记录页面已有实现；F03/F04 图片识别 APP 源码也已完成，Agent 服务与真机/法律签核仍待外部验收。通用占位元数据表 `PLACEHOLDER_META` 为空，没有通用“功能建设中”占位路由注册；具体尚未接入的数据只显示安全状态。“我的”页“设置与隐私”行进入 `/pages/settings/index`；hub 提供独立隐私中心行，路由到 `/pages/privacy/center`。hub 只提供已接通的资料与账户、站内通知偏好、隐私授权、隐私中心、数据导出、账号注销和只读版本入口；退出登录仍由资料页负责。`/pages/privacy/consents` 使用服务端当前授权状态与告知，不在客户端伪造授权版本。设置页应用版本单一来源为 `src/manifest.json` `versionName`；原生数据导出文件保存能力尚未验收。

## 命令

- `pnpm typecheck`：Vue / TypeScript 静态检查
- `pnpm openapi:generate`：从冻结 OpenAPI 的 auth/profile、privacy deletion/export、consent 与 F03–F08/F10–F12/F14 operations 生成 TypeScript 类型
- `pnpm openapi:check`：重新过滤并生成后与受检入库类型逐字节比对；`pnpm check` 和仓库 lint 门禁执行此检查
- `pnpm test`：API、记录/活动/心情/风险/通知组件契约、偏好与状态 helper、会话、注册草稿、邮箱验证、导航与启动状态单元测试
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

UTS 插件需由 DCloud 支持的 HBuilderX 原生构建链处理；DCloud 文档明确指出 uni-app UTS 插件目前不支持 CLI 创建/使用。为现有 Vite CLI 路径显式锁定匹配版本 `@dcloudio/uni-uts-v1@3.0.0-4060620250520001`，只能让 CLI 执行其可用的预处理/导出流程，不能改变该路径非官方支持的状态。`scripts/app-build.ps1` 按原生命令退出码判定失败、将 stdout/stderr 原样保留在控制台，并检查预期 HBuilderX 导入文件；PowerShell 5.1 与 pwsh 7 均兼容，stderr 中的 Sass 弃用警告本身不代表失败。CLI 输出 `dist/build/app` 及 UTS 描述文件不等同于 APK/IPA、Android/iOS 原生 UTS 编译、签名或设备验证。Android 需在 HBuilderX 中构建包含此 UTS 插件的自定义基座并在真机验证；iOS 原生编译和运行需 macOS + Xcode，设备安装还需 Apple 开发者签名证书及 provisioning profile。当前仓库未提供签名材料，也未记录 Android 或 iOS 真机证据，不得据 CLI 导出结果宣称原生安全存储已经验收。脚本 stderr/退出码兼容性可用 `scripts/test-app-build-command.ps1` 在 Windows PowerShell 5.1 和 pwsh 7 验证。

自动化测试覆盖了 Keychain 写入状态决策（duplicate→update→not-found→retry-add→duplicate→retry-update）、未找到不能假成功及删除幂等规则；该纯逻辑测试不调用 iOS Security 原生 API。发布前还必须真机验证：原生插件可编译且未记录令牌；set/get/has/remove 持久化和退出清理（包括 Keychain 更新竞态及同步性/可访问属性）；iOS 锁屏后返回 `DEVICE_LOCKED` 且解锁后仍可读取；密文损坏/Keystore key 丢失后清理并要求重新登录；Android 云备份与设备迁移不携带令牌文件；iOS 卸载重装清除遗留 Keychain 值、恢复到另一设备不迁移 Keychain；Web/unsupported target fail-closed。

## B01-1 认证和导航基础

- `openapi-typescript@7.13.0` 与 `yaml@2.9.1` 均精确锁定。生成器只从权威 OpenAPI `operationId` 过滤 auth/profile、consent、F03–F08/F10/F12/F14 records、F13 deletion operation，并断言必需 operationId 集合各出现一次；schema/DTO 不手写。`AuthApi` 登录/注销委托 B00b `SessionService`，不会重复实现 refresh。
- `AuthApi`、`ProfileApi` 使用生成的请求/响应类型。注册请求在运行时也拒绝额外键。
- 第 22 页仅以内存 Pinia store 保存邮箱、密码、确认密码和隐私选择；第 17 页进入后只有明确同意健康数据处理才会开放出生年份字段；单独切换撤销同意只清出生年份，顶部/系统返回回第 22 页并保留草稿以供编辑。选择“暂不同意并退出注册”会清除整个草稿并回到登录；离开注册流程时路由层也清除草稿。提交请求显式构造 OpenAPI 六字段，成功受理后清除密码并进入邮箱验证页。验证令牌只由用户输入、只保存在页面内存、不放 URL/持久化；验证 204 后清草稿并回到登录。测试告知来自唯一 JSON 制品；当前开发/测试制品在 production mode 下 fail closed。
- 路由注册表有 public/authenticated 元数据；仅允许白名单中标记的受保护命名路由作为进程内 `returnTo`。导航拦截器与根页条件渲染双重阻止认证/资料尚未完成时显示受保护页面。启动/登录恢复固定执行 session restore → `GET /patients/me`：200 才进入今日；401 清会话返回登录；404 清会话进入不可继续的资料一致性错误态并展示 `request_id`；不会伪造资料或进入 `/onboarding/profile`。
- Access Token 和患者资料仅保存在 Pinia 内存；原生 Refresh Token 继续由 B00b SecureTokenStore 管理。登出调用 `POST /auth/logout` 后清除 returnTo，并用 `reLaunch(login)` 清空页面栈。
- RFC 9457 `ProblemDetails` 从生成的 OpenAPI `components.schemas.Problem` 派生；客户端稳定错误类型只封装 kind/status/code/requestId，不另行复制契约字段。
- `RecordsApi`、`MoodApi` 与 `ActivityApi` 复用唯一 RequestClient、RFC 9457 错误映射与既有 refresh 单飞逻辑。F03–F05/F14 创建使用生成 DTO 和幂等键；F07 冻结契约不定义创建幂等键，APP 仅以单飞状态阻止重复点击；PATCH/DELETE 使用服务端 `record_version`，409 不覆盖。F14 P0 总是写空 `emotion_tags` 数组。心情备注仅本人详情/编辑可见；列表不展示，页面不输出分析/日志/埋点。心情新建/修改先读服务端当前授权状态并要求 `health_data_processing` 与 `mood_data_processing` 同意；AI共享两项独立管理。授权管理页仅显示与运行时版本/hash匹配的服务端告知；开发测试文案醒目标记 test-only，生产无获批告知时禁用同意操作。错误/版本冲突保留草稿并要求患者明确操作。

生成器过滤范围包括 auth/profile、consent、F03–F07/F10/F14 记录 CRUD/状态历史、F06 用药与 F10 风险提示端点；每个 F10 operationId 由集合断言唯一覆盖。`RiskApi` 使用同一 `RequestClient` 与 RFC 9457/401 refresh，提供游标分页、未读筛选、详情、独立标记已查看和重新评估动作。

## B05a F10 风险提示

`/pages/risk-alerts/index` 与 `/pages/risk-alerts/detail` 是受保护的风险列表和详情入口；列表支持全部/未查看过滤、游标追加及明确的加载/空/离线/失败/追加重试状态，详情 GET 不隐式标记已查看。详情的“标记已查看”和“标记已重新评估”调用不同端点；状态说明明确二者均不等于风险解除或确认安全。严重级别和状态仅展示后端值，不计算阈值或改写等级；紧急等级用“紧急提示”文字、符号、边框和可见行动建议，不只依赖颜色。原始 evidence 对象及规则内部信息不显示；不声称 test-only 规则经过生产专业审核。

今日页单独加载真实未读风险列表；API 失败会显示可重试错误而非无风险空态。风险列表从详情返回时按当前筛选刷新首屏；首次 onShow 跳过以免和 onLoad 重复请求，刷新失败保留已显示列表/游标并提供重试。详情无需 Agent/通知服务；深链通过全局路由及页面 auth guard，详情栈隐藏底栏并沿所属入口返回。没有发送 `patient_id`、规则内部字段或自由推断内容。自动化契约测试覆盖查询参数、read/reevaluate 分流、紧急行动可见、失败非空态和深链守卫；Android/iOS CLI 导出不替代原生真机与无障碍验收。

## B04 F06 用药管理

`/pages/medications/index` 为受保护的本人用药工作区，包含计划列表/新增/详情/编辑/删除、计划状态操作、日程维护、今日打卡与历史。`MedicationApi` 复用共享 `RequestClient`、RFC 9457 与认证刷新，所有传输 DTO 从 OpenAPI 生成；创建计划、计划状态转换、创建日程按契约附 Idempotency-Key，更新/删除按契约携带 `record_version`，打卡 PATCH 不添加契约未定义的幂等头。APP 不提交 `patient_id`，只以手动来源创建计划；不伪造医疗文档来源、服用事实、设备来源或医学建议。

计划转换按钮由确认状态和生命周期状态计算，仅显示服务端状态机允许的操作；待确认不等于未服用。版本冲突保留编辑草稿，并并列展示最新服务端状态，患者可显式放弃草稿载入最新值或保留草稿、基于最新版本继续确认，不自动覆盖/重提。今日根页仅将今日打卡卡片接入真实 `/medication-checkins/today`，显式区分加载、空和失败；后端未返回药品名称时不臆造名称。页面按 430px、安全区和至少 44px 触控布局；无获准头像/图标素材依赖。

## B01-2 公开认证页面

已实现的公开认证入口：欢迎页、邮箱登录、注册账户（22）、健康处理同意/出生年份（17）、邮箱验证、找回密码、密码重置和资料一致性错误页。共用 `AuthScaffold`、`GcButton`、`GcField`、`NoticeCard` 与 `InlineProblem`；表单字段有关联标签、错误描述、稳定 `data-testid`，交互控件满足至少 44px 触控尺寸。认证失败文案按状态安全呈现，401 不区分账户/密码/验证，429/5xx/离线错误可见 request_id。

注册仍按第 22 页到第 17 页执行：前者只保存内存草稿且不发请求；隐私政策与健康处理告知分别显示，只有后者明确同意时才显示出生年份输入，并最终调用单次注册 API。找回密码 request 提示不透露账户是否存在；reset token 只能手动输入，不接受 URL/query 参数，不写入持久化；成功后清除敏感表单并返回登录。未实现手机号/SMS、姓名/性别/报告字段或自由 AI 对话。欢迎和邮件图形由 CSS/code-native 图形绘制，没有使用来源/授权未确认的原型图片。

公开认证页面采用 430px 原型宽度基准、安全区可滚动布局、48px/16px 圆角主按钮、邮箱/密码图标输入行与无外层大表单卡片；欢迎页以内联 SVG 和三条 feature 文案替代隔离原型图像，并以横排注册/登录作为入口。启动/资料加载安全错误保留 transport kind、status、code 与 request_id；一致性错误支持说明入口只指导用户经官方渠道手动联系，不自动发送数据。router 对任何路径上的 token/access_token/refresh_token/password/new_password query 先清空注册草稿再返回登录。

## B01-3 本人资料与会话安全

`/pages/profile/index` 是认证路由，资料读取和编辑只使用 `/patients/me`；PATCH 以当前 `profile_version` 为准，仅提交患者改动过的 `nickname`、`birth_year`、`timezone` 字段，清空昵称发送 `null`。409 不自动覆盖，先重新 GET 并向患者展示最新值/拟改值，由患者确认后再重试。资料 404 会清会话、保留 request_id 并跳转资料一致性错误页。

退出有二次确认和防重复调用。刷新令牌删除和服务端 logout 都会尝试；Access Token 与 profile 内存态始终清除，受保护页面栈及 `returnTo` 被清空后 reLaunch 到登录页。若本机安全存储拒绝删除，登录页显示原生安全存储错误码，不把 token 放入 UI 状态或日志。无效 refresh 对过期/冻结账户统一按认证失败处理，不恢复旧 returnTo。双患者资料隔离和 profile 乐观锁由后端 canonical T49、补充 T142/PG18 集成证据覆盖；客户端不提交 patient id。

## B02 四根 Tab 导航壳

路由注册名 `today`、`records`、`analysis`、`me` 映射逻辑路径 `/tabs/today`、`/tabs/records`、`/tabs/analysis`、`/tabs/me`；uni-app 页面物理路径位于 `pages/tabs/*/index`。共享 `GcBottomNav` 位于四个根页，底栏切换调用命名路由并以根页 `reLaunch` 避免压入重复页面。二级业务页隐藏底栏并显式绑定 `ownerTab`；通用 placeholder route metadata 为空，未注册功能占位路由。受保护根页与业务页均由登录守卫保护，returnTo 只保存白名单中的命名路由。

今日页包含真实摘要五卡（风险、用药、通知、最近建议、趋势）和快捷记录；未接入的单项服务只显示“未接入”而非假数据。“我的”使用无图片 GcAvatar 呈现头像缺省状态。底栏和页面图形均由组件/CSS/code-native SVG 构成，不引用隔离的原型素材。数据状态组件支持 loading/empty/error/unavailable；Android/iOS CLI 构建不等于真机视觉/可访问性签收。

当前组件状态映射、表单/服务流程和页面约束测试、类型检查与 Android/iOS CLI 导出可自动验证；这不构成真机视觉签收。当前未生成或签收 430×880 像素基线；Android/iOS 真机截图、键盘/安全区/动态字号检查、逐页像素对比 SSIM ≥0.95，以及经法律批准的生产注册告知，仍是发布门禁。无患者 Web/H5 发布目标。

## B05b F12 站内通知

通知中心、详情、普通通知偏好和分析/建议受保护 target 均使用注册路由。`NotificationApi` 复用共享 RequestClient；筛选、cursor、未读计数、单条/批量已读及偏好 DTO 直接来自 OpenAPI 生成类型。通知仅显示契约事件类别/时间/优先级，不构造通知正文、药名剂量、报告或建议内容。target 严格按服务端类型 allowlist 映射；target 缺失/不可用时不推测路由。建议通知进入已实现的受保护详情，并由路由器内存授权固定 `from=notification`；详情返回时恢复来源通知详情，缺少有效来源 ID 则回通知列表。任意外部 URL/query 不作为返回地址，直接建议深链仍回 owner Tab。

批量操作仅提交患者明确选择的未读通知 ID；后端失败时列表与选择保留，成功按返回 DTO 精确更新。首页和“我的”通过 `/notifications/unread-count` 显示真实数字，错误不显示成 0。普通提醒开关/quiet hours 不隐藏风险通知、不更改风险提示状态；不接外部 push 或供应商 SDK。T121 自动化覆盖 API、过滤与分页、目标 allowlist、批量状态 helper、偏好豁免及未读入口；设备真机/无障碍验收仍单独进行。

## B06a F13 账号注销

设置与隐私页进入高危确认，明确理解勾选后才允许单飞提交。202 受理后先把 `{operation_id, receipt}` 写入独立原生 Keychain/Keystore 命名空间，再撤销本地刷新凭据、清理 access/profile/returnTo 并 `reLaunch` 到无认证进度页；不调用 logout，不提供取消注销。安全存储写入失败时仅留进程内并明确要求手动记录首次响应凭证，绝不降级到普通 uni storage；receipt 为 `null` 时只关联相同 operation ID 的既存凭证，否则明确说明无法恢复，不覆盖、不声称已恢复。

进度页不把凭证或操作 ID 放在 APP 路由/query；手工查询通过受控 POST body，输入凭证在发送前从页面状态清除。手工输入可恢复查询但只在未完成状态保存到原生安全存储；`completed` 删除对应安全凭证。`overdue/dead_letter` 显示联系支持且不触发重新注销。原生 secure-store 接口的 HBuilderX 编译、安装与 Android/iOS 真机证据仍需单独验收；CLI build 不等于系统安全能力真机通过。

## B06b F13 个人数据导出

隐私中心进入受保护导出页。用户从冻结的 14 类白名单中明确选择类别；空选择拒绝，包含心情记录时显示 S4 提醒。创建接口只产生 `preview`，必须再次确认才调用 confirm 入队。列表、详情与手动刷新只呈现服务端七状态；失败与空历史分开，刷新失败保留已显示内容；取消仅限 preview/pending/processing，409/503 不自动重提。

下载能力只从 ready 的详情响应取得，保留在页面进程内存，固定同源 `/privacy/exports/download` 并仅放 `X-Export-Capability` 请求头；绝不放 query、普通存储、日志、analytics 或剪贴板。当前客户端没有可验证的系统 ZIP 保存/分享能力，因此保存/分享入口 fail-closed 且不会消费 capability；真机 ZIP 保存/分享与原生适配器仍是外部门禁。适配器只使用 uni 临时沙箱路径并提供清理，不直连对象存储/MinIO。T123 覆盖操作集合、类别、显式确认、状态与 capability 边界。

## B07a F11 历史时间线

受保护 `/pages/history/index` 从记录 Tab 进入，返回所属根 Tab。`HistoryApi` 复用共享 `RequestClient`，DTO 来自 `getHistoryTimeline` 的生成 OpenAPI 类型。多类别筛选仅使用冻结的七类枚举；本地日历筛选转换为带时区的 UTC `[since, until)`，按时区日历边界计算以正确处理 DST。追加分页采用后端签名 cursor；失败保留当前项目和 cursor，支持重试。

页面只显示记录类别、时间和固定 target。目标通过 allowlist 映射到记录详情、用药页或受保护建议详情；未知/null/无效 ID 不跳转。不会复制记录正文、mood note、emotion_tags、敏感摘要，也不调用 Agent 或发送 patient_id。T124 覆盖类别/时间序列化、DST、目标 allowlist、筛选重置、首次 onShow 去重、详情返回刷新、离页响应失效及追加失败保留；双端 CLI/自动化不替代 Android/iOS 真机视觉与无障碍验收。

## B07b F11 确定性趋势

`/pages/trends/index` 是受保护趋势二级页；分析与我的入口共用页面并固定各自 ownerTab。`TrendApi` 复用共享 `RequestClient`，GET `/trends` 的所有 DTO 均由 OpenAPI 生成。页面通过账户 IANA 时区构造 UTC 半开区间，支持快速/自定义日期和日/周切换；切换会重新查询且用 generation 丢弃离页或过期响应。

页面分别呈现服务端 activity、stool、symptom、diet-confirmed-category、medication-checkin 和 mood 聚合，不在客户端计算/合并指标。Mood 仅依据服务端 `availability` 判别：available 空 buckets 是已授权无记录；consent_required 只展示缺失的 health_data_processing/mood_data_processing 及隐私中心入口，绝不变成零数据。界面只显示本人自评与记录统计，不含 mood note/emotion_tags、诊断、因果或饮食/运动建议。T125 覆盖 OpenAPI 运行时/契约 schema 与 examples、DST/UTC 半开边界、授权分流、空/错误/离线、bucket/ownerTab 路由、请求竞争与 note/tag 排除；Android/iOS CLI build 和自动化不替代设备视觉/无障碍验收。

## B08a F08 分析任务基础切片

受保护 `/analysis/new`、`/analysis/history` 与 `/analysis/task/:id` 分别提供预览/创建、稳定游标历史和任务状态详情。请求与响应 DTO 由 `contracts/openapi/gutcare-v1.yaml` 生成；创建为单飞并带 `Idempotency-Key`，仅接受 `202` 且校验 `Location` 指向同一任务 ID。预览仅为当时统计，不承诺创建快照完全一致；任务快照和 mood 纳入/排除由服务端授权 fence 决定。

综合分析时间范围允许两端都省略或两端都提供，periodic 必须提供两端；显式时间按 UTC 半开区间 `[from,to)`。历史分页 cursor 是不透明值，服务端以 HMAC `patient_scope` 绑定患者且不在载荷中放原始 patient UUID；cursor 仅进入请求参数，不写日志。B08a基础阶段详情只显示后端状态、attempt/retry_of、输入摘要、错误码和结果存在性，不显示结果正文或 evidence；B08b扩展见下节。页面不调用 Agent，也不传 `patient_id`。APP T126 覆盖客户端 API、表单、分页、生命周期和深链；后端 T66–T71、T111–T112 仍是独立证据。Android/iOS CLI build 不替代真机视觉/无障碍签收。

## B08b F08 取消、重试与结构化结果

详情页仅在 pending/processing 显示二次确认取消，仅 failed 显示二次确认重试；`needs_input` 是终态并引导补齐后新建任务。重试带 Idempotency-Key，成功必须核验 202、Location 与 `retry_of` 后打开服务端新任务，失败不覆盖当前状态、不自动重提。非终态每15秒刷新，页面隐藏停止、显示恢复时刷新；错误保留最后状态，不制造进度。partial 与 succeeded 分开标识。

结果仅展示生成 DTO `AnalysisResult` schema_version `1.0` 的 summary、observations、evidence、uncertainties、missing_data。证据通过 source_type 固定映射；已删除来源隐藏 locator 且不跳转，未知/不支持来源不跳转。错误码只显示通用安全映射；不显示 callback_id、prompt、模型原始输出、报告正文/URL 或 mood note。结果明确不是诊断或处方。“报告与结果”入口指向任务历史，结构化内容从任务详情进入。APP T127 覆盖状态矩阵、动作、轮询生命周期与结果白名单；服务端能力仍以 T66–T71、T111–T112 为准。

## B09a F09 建议 APP

`/pages/advice/analysis` 和 `/pages/advice/index` 分别归属分析与“我的”Tab；详情 `/pages/advice/detail` 保留 owner/from，并支持历史/通知按受控 UUID 映射进入。通知发起的详情只在内存授权的 `from=notification` 下返回原通知详情；缺少内存通知 UUID 时回通知列表，未经授权的直接深链回 owner Tab。顶部返回与系统返回执行同一来源策略。`AdviceApi` 与 Advice/Feedback DTO 由 OpenAPI 生成，复用共享 `RequestClient` 的 RFC 9457、认证刷新与请求 ID。列表/详情显式区分 loading、empty、error/offline、refresh 与 append 错误；追加失败保留已载入记录和 cursor，首次 onShow 不重复请求，隐藏/卸载后响应失效。

标记已读、归档、反馈均由患者显式操作；反馈使用契约 `expected_version` 和 `Idempotency-Key`。409 不覆盖当前内容、不自动重提。risk_priority_context 总在建议前优先展示并固定路由 F10；状态文案不把 read/reevaluated 解释为风险解除或安全。来源只呈现经过 source_type、source_id、`type:id` locator、target、删除状态共同校验的固定标签；知识引用仅展示无 userinfo HTTPS 域名，不显示 URL 或自动打开。mood evidence 已受后端冻结快照和四授权 fence 限制；APP 不显示 mood note/emotion_tags、不传 patient_id、不记录建议正文到通知、日志或埋点。T128 覆盖 API、证据/引用 allowlist、风险优先、A/B 与授权 fence、409、owner/from/deep-link 和生命周期竞态。CLI build 不替代 Android/iOS 真机无障碍签收。

## B09b 今日首页真实数据摘要

今日页只调用五项既有本人 API：风险前三条未读、今日用药打卡、通知未读数、最近一条建议、以及患者 IANA 时区当日的六类趋势聚合。风险优先展示；建议卡按服务端返回状态直显（包括已归档），不将其描述为待处理或有效。每卡独立加载/空/错误/重试；刷新失败保留已载入数据，首次失败不折算为零/无数据。心情授权缺失与授权下空桶分别呈现。趋势原样展示后端聚合，不在客户端生成结论；不请求逐条记录详情。

## F02a 医疗档案基础 APP

“记录 → 健康档案”使用受保护 `/records/health-archive`，文档详情使用 `/records/medical-documents/:documentId`。APP 只通过既有业务 API 创建上传会话、向同源受保护 gateway 传原始 bytes、完成扫描后创建本人档案；禁止直连 Agent/MinIO、持久化 capability、记录 capability URL/本地路径/文件名或展示 bucket/key。PDF 最大 20 MiB，JPEG/PNG 最大 10 MiB；客户端预检不替代服务器 MIME、大小与安全扫描。扫描不可用显示可重试错误，不伪装成功。`store_only` 不提交解析；`analyze` 的授权与解析任务由后端执行，未经患者逐字段确认的候选不成为事实。

原生文件选择由窄 UTS 插件提供：Android SAF `ACTION_OPEN_DOCUMENT`、iOS `UIDocumentPickerViewController`，单选后复制到 APP cache，上传/取消/失败清理 cache；不申请广泛存储/照片权限。H5 与插件不可用均 fail-closed。当前自动化与 CLI 检查不等同于 HBuilderX 自定义基座/签名安装或 Android、iOS/iCloud/cloud-provider 真机验证；这些设备证据仍是外部发布门禁。T130 是本切片 APP 合同测试；后端 F02/T03–T06、T60–T65、T103–T104 与本次 APP 验收分开记录。

## F02b 医疗解析候选逐字段审核 APP

文档详情在解析 outcome 为 `extracted` 时读取生成类型的候选 DTO，并仅对 `pending` 候选提供逐字段“按原值确认 / 更正后确认 / 不采纳”；没有批量或自动确认。决定请求携带候选当前 `record_version`、独立 `Idempotency-Key` 和契约要求的 body。`accepted/corrected/rejected/invalidated` 状态及已确认值按后端返回显示；诊断确定性保持原值，不作升级。`no_supported_facts`、`insufficient_quality` 与技术 `failed` 分别说明。409 保留当前内容、重新读取文档/候选并要求用户查看，不自动重发；跨患者/删除 404 显示统一不可用状态并清除候选来源证据。

来源定位只显示受控页码/文本位置/页面区域标签，excerpt 必须在受保护详情中显式按需展开且仅短显；离页清空内存候选/更正草稿并在返回时重新取数。更正值按字段类型编辑（诊断仅改文字并保留 certainty；对象值采用 JSON 输入，服务端继续校验）。候选内容不写路由、日志、遥测或普通持久化。T131 为本切片 APP 合同/辅助函数/交互状态测试；不代表 Agent 推理、真机或完整 F02 验收。

## F02c 已确认检验事实冲突 APP

健康档案“待核对冲突”入口进入受保护收件箱；默认只读 `open`，可显式筛选 `resolved`、`invalidated` 或 `all`。既有 API 无分页，列表按服务端返回顺序原样展示，不在 APP 推断或按临床含义重排。详情仅显示受控检验项目/结果值、单位、采样日期和来源档案 ID；不显示 excerpt、报告正文或 Agent 输出。来源档案使用固定文档详情路由。

唯一操作是显式确认 `keep_both`：双方继续作为独立事实保留，不选择正确性/严重性、不合并或删除。提交使用当前 `record_version` 和新 `Idempotency-Key`；409 只刷新详情并要求用户再次明确确认，不自动重发。页面为 ADR-0018 驱动的补充页面，原型无冻结冲突页，因此不宣称达到该页截图验收比例。T132 是本切片 APP 合同/辅助函数/导航测试；后端 T104 验收状态单独记录，不由此切片改变。
