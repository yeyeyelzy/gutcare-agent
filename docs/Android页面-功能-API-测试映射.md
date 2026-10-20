# Android 页面—功能—API—测试映射

> 状态：静态 UI 基线已提取；Android 原生工程基座、认证运行时及 F03/F04/F05/F14 手工记录切片已进入工作树。当前切片已通过 Debug 构建、JVM 51/51、`RecordScreensTest` 9/9、全量 instrumentation 23/23，并通过真实 phone-demo 记录 API 联调；逐页 UI ≥80% 且无明显错误和发布前真机验收尚未完成。本文记录页面映射、已验范围及联调缺口。日期：2026-10-20。
> 权威来源：`UI原型审查与页面导航规范.md`、`UI源码基线与导入规范.md`、`UI交付与实现规范.md`、`详细功能设计.md`、ADR-0022、`contracts/openapi/gutcare-v1.yaml`、`需求追踪矩阵.md`。

## 1. 基线与实施边界

ZIP 静态清单见 [`design-reference/android-ui-baseline/manifest.json`](../design-reference/android-ui-baseline/manifest.json)。规范页序号为 01–22，清单 `page` 为 0–21；页面图片原始尺寸宽度均为 1290 px、高度 2693–3971 px（欢迎页 2818 px）。另有一张运动页替代导出 `page18_运动记录_2x.png`，尺寸 860×2170 px，不计入 22 个规范页。文件按页码与识别出的中文标题保留原名。来源哈希和每张图片的字节数、尺寸、SHA-256 均在 manifest；manifest 只写 ZIP 文件名和相对路径，不含用户绝对路径。素材来源/授权尚未确认，`production_allowed=false`；不得导入 APK。

Android 是唯一患者端开发和验收目标。现有 `android/` 已有 Kotlin/Compose 工程基座、认证运行时、会话/网络基础设施和四个受保护底栏根路由。注册、邮箱验证、登录、refresh 恢复、`GET /patients/me` 引导和退出已连接业务 API；真实运行时不使用 `UnconnectedAuthWorkflow`，它仅是 NavHost 默认/测试回退。注册告知由 Gradle 从 `contracts/consent/registration-notices.json` 生成 Android 资源并在运行时校验。T01k 已在 phone-demo 上真实跑通原生 Repository 注册—邮箱验证—登录—本人资料读取—refresh 后资料刷新—退出链路（1/1），但不经过 Compose 页面；页面级认证 E2E 仍待验收。

当前工作树加入 F03/F04/F05/F14 的 Retrofit DTO/Repository、受保护列表/新增/详情/编辑页面、真实 CRUD、症状状态历史、游标分页、加载/空/错误/401/409 处理、登出清态和跨会话迟到响应隔离。`other_description` 及记录表单可见控件已接入 payload。今日根页已提供记录入口，记录根页已提供四类记录及健康档案入口；Analysis 仍为明确不连接智能体的安全占位，“我的”目前仅提供退出。健康档案页面只读取已加载的本人资料，医疗档案 API 与上传尚未接入并保持禁用。心情授权管理、图片上传/识别、活动记录和完整历史时间线尚未在原生工程交付。真实 phone-demo 验收摘要位于 `android/build/emulator-evidence/phone-demo-records-20261020-014006-b480ec9f/summary.json`；它覆盖 diet/stool/symptom/mood CRUD、游标分页、symptom status-history、409 和登出后 401，不扩大其他 Fxx 的交付状态。下表“API 后端状态 / 当前 Android 可联调”不把旧 `app/` 代码或静态原型当作原生验收证据。

非 Agent 区域始终由 Android + FastAPI 业务后端负责：认证、资料、授权、记录 CRUD、文件与候选生命周期、任务/快照/状态、建议/风险/趋势/通知/隐私。Agent 只从业务后端领取允许的冻结快照并返回受限结果；APP 不直连 Agent、数据库或对象存储。图片候选在患者确认前不是事实。未获专业审核的风险规则只能是 `test_only`。

## 2. 逐页映射

| 页 | 原图 | 功能 / 非 Agent 与 Agent 边界 | 建议 Android route | 业务 API（APP 只调业务后端） | 关键状态 | 测试追踪 | API 后端状态 / 当前 Android 可联调 |
|---:|---|---|---|---|---|---|---|
| 01 | [欢迎页](../design-reference/android-ui-baseline/pages/page00_欢迎页.png) | F01 公开入口；认证与会话归 APP/业务端，无 Agent | `welcome` | 无；进入登录/注册；冷启动尝试 refresh 并读取 `/patients/me` | 首次启动、已有会话恢复、会话失效 | T01、T01g、T01j、T01k；UI-01/02 | 认证后端 verified；运行时已接线，T01k Repository 链路通过；页面级 E2E 待验收 |
| 02 | [今日](../design-reference/android-ui-baseline/pages/page01_今日.png) | F01/F06/F09/F10/F11/F12 首页摘要；规则风险由业务端计算，建议内容可来自受限 Agent 任务 | `tabs/today` | 目标为 `GET /risk-alerts`、`/medication-checkins/today`、`/notifications/unread-count`、`/advice`、`/trends` | 当前仅显示本人昵称/中性称呼、明确未接入摘要及记录快捷入口；不伪造业务摘要 | T01j、T119–T121、T125、T128–T129；`RecordScreensTest`；UI-03/06/07 | 后端相关端点 verified；Android 页面/导航已实现，摘要 API 未接入，视觉待评分 |
| 03 | [饮食记录](../design-reference/android-ui-baseline/pages/page02_饮食记录.png) | F03；记录与确认事实归业务端；识别候选由 Agent 通过独立任务返回，患者逐字段确认 | `records/diet`、`records/diet/new`、`records/detail/diet/{id}`、`records/edit/diet/{id}` | `GET/POST /diet-records`，`GET/PATCH/DELETE /diet-records/{id}`；附件与识别按 OpenAPI image operations | 手工 CRUD、分页、加载/空/错误、401/409 与反馈已接入；图片与候选未接入 | T07–T10、T116、T133–T140、T145–T146；UI-04 | CRUD 后端 verified；Android 手工 CRUD 的自动化、模拟器和真实 phone-demo API 场景已通过；视觉待评分，图片/Agent 未接入 |
| 04 | [综合分析报告](../design-reference/android-ui-baseline/pages/page03_综合分析报告.png) | F08；业务端持有任务、快照、证据归属和可见性；Agent 仅消费快照并回传结构化结果 | `analysis/task/{taskId}` | `GET /analysis-tasks/{task_id}`；受控取消/重试分别为 `/cancel`、`/retry` | pending/processing/needs_input/succeeded/partial/failed/cancelled；只呈现白名单结果与证据 | T66–T71、T127、T14–T18；A25–A29；UI-05 | 业务后端 verified；Agent 服务/E2E 未交付，Android 否 |
| 05 | [个性化建议](../design-reference/android-ui-baseline/pages/page04_个性化建议.png) | F09；业务端校验和保存建议、证据、生命周期；Advice Agent 经受限 callback 生成内容 | `advice/index`、`advice/detail/{adviceId}` | `GET /advice`、`GET /advice/{advice_id}`、`POST .../read`、`.../archive`、`.../feedback` | new/read/archived 与 basis_updated 分开；风险优先；来源失效/越权安全态 | T72–T79、T128、A30–A32；UI-06 | 后端 verified；Agent 真实服务待验，Android 否 |
| 06 | [健康趋势](../design-reference/android-ui-baseline/pages/page05_健康趋势.png) | F11；确定性 SQL 聚合由业务端完成，不调用 Agent | `trends?owner=analysis|me` | `GET /trends` | loading/available 空/consent_required/error/offline；mood 授权缺失不得显示为零；不呈现 note | T36–T38、T88–T91、T109/T113、T125；A37–A39/A51；UI-06 | 后端 verified；Android 否 |
| 07 | [风险提示](../design-reference/android-ui-baseline/pages/page06_风险提示.png) | F10；确定性规则和风险状态由业务端负责，不等待 Agent | `risk-alerts`、`risk-alerts/{alertId}` | `GET /risk-alerts`、`GET /risk-alerts/{alert_id}`、`POST .../read`、`POST .../reevaluate` | 未读/已读/重新评估；读不等于解除；规则未审核只能 test_only | T31–T35c、T120、A33–A36；UI-07 | 后端 verified；生产规则审核另门禁；Android 否 |
| 08 | [健康档案](../design-reference/android-ui-baseline/pages/page07_健康档案.png) | F02；文件/档案/删除/确认由业务端，解析仅生成待确认字段 | `records/health-archive` | 目标为 `/files/uploads`、`/files/uploads/{upload_id}/complete`、`/medical-documents`、`/medical-documents/{id}`、download grant | 当前仅显示已加载本人资料和明确未接入错误态；上传/编辑按钮禁用，不构造档案数据 | T03–T06、T60–T65、T103–T104、T130–T132；`RecordScreensTest`；UI-08 | 后端主范围 implemented；Android 静态页面已实现但档案 API/上传未接入，视觉待评分 |
| 09 | [AI 助手](../design-reference/android-ui-baseline/pages/page08_AI助手.png) | 原型能力未冻结；不得自由聊天、直连 Agent 或查询业务数据库 | 不注册可用 route；受限提示可留在原入口 | 无 | 隐藏/不可用说明；不提供输入框和发送动作 | T01j、UI-09；安全边界见 UI 原型审查规范 | 无获批 API；不可联调 |
| 10 | [个人中心](../design-reference/android-ui-baseline/pages/page09_个人中心.png) | F01/F09/F11/F13 导航枢纽；无独立业务实体 | `tabs/me` | `GET /patients/me`；各功能端点由子页请求 | 资料缺失一致性错误；跳转仅指向已注册受保护页 | T01g–T01j、T49、T142；UI-03/10 | 资料后端 verified；Android 否 |
| 11 | [检查报告详情](../design-reference/android-ui-baseline/pages/page10_检查报告详情.png) | F02；候选抽取可由 Agent 处理，业务端逐字段确认、审计、转事实 | `records/medical-documents/{documentId}` | `GET /medical-documents/{id}`、`GET /medical-documents/{id}/candidates`、`POST /medical-field-candidates/{id}/decision`、download grant | extracted/no_supported_facts/insufficient_quality 与技术 failed 区分；pending/accepted/edited/rejected；409 刷新但不自动重发 | T60–T65、T103、T131；A04–A07；UI-08 | 后端实现并有已验子范围；真实 Agent 处理及 Android 否 |
| 12 | [排便记录](../design-reference/android-ui-baseline/pages/page11_排便记录.png) | F04；记录由业务端管理，图像仅产生 Bristol 候选且需患者确认 | `records/stool`、`records/stool/new`、`records/detail/stool/{id}`、`records/edit/stool/{id}` | `GET/POST /stool-records`，`GET/PATCH/DELETE /stool-records/{id}`；图片/识别 OpenAPI operations | 手工 CRUD、分页、加载/空/错误、401/409 已接入；Bristol 可选、图片不强制；图片候选未接入 | T09–T10、T116、T133–T140、T145–T146；UI-04 | CRUD 后端 verified；Android 手工 CRUD 的自动化、模拟器和真实 phone-demo API 场景已通过；视觉待评分，图像 Agent E2E 未验 |
| 13 | [症状记录](../design-reference/android-ui-baseline/pages/page12_症状记录.png) | F05/F10；CRUD 与确定性规则属于业务端 | `records/symptoms`、`records/symptoms/new`、`records/detail/symptom/{id}`、`records/edit/symptom/{id}` | `GET/POST /symptom-records`，`GET/PATCH/DELETE /symptom-records/{id}` 与状态历史 GET；风险为 `GET /risk-alerts` | 手工 CRUD、分页、状态历史、`other_description`、加载/空/错误、401/409 已接入；风险卡未接入 | T13–T15、T35b–T35c、T116、T120、T145–T146；UI-04/07 | 后端 verified；Android 手工 CRUD/status-history 的自动化、模拟器和真实 phone-demo API 场景已通过；视觉待评分，F10 风险页未迁移 |
| 14 | [发起综合分析](../design-reference/android-ui-baseline/pages/page13_发起综合分析.png) | F08；业务端校验授权、预览、快照和幂等；Agent 分析冻结输入 | `analysis/new` | `GET /analysis-tasks/preview`、`POST /analysis-tasks` | preview 不等于最终快照；范围 UTC 半开；显示服务端 mood in-range/eligible/excluded 数及原因；创建前复验 | T66–T71、T106–T108、T111–T112、T126；A25–A29/A52；UI-05 | 业务后端 verified；Agent 服务/E2E 未验；Android 否 |
| 15 | [用药计划](../design-reference/android-ui-baseline/pages/page14_用药计划.png) | F06；仅管理患者确认的处方/计划和打卡，不生成药物方案 | `medications` | `/medication-plans`、`/medication-schedules`、`/medication-checkins`、`/medication-checkins/today` | confirmation_status 与 plan_status 独立；pending 不是未服；409 不覆盖 | T52–T59、T119；A19–A22；UI-10 | 后端 verified；Android 否 |
| 16 | [心情记录](../design-reference/android-ui-baseline/pages/page15_心情记录.png) | F14；CRUD/授权/趋势由业务端；仅任务快照允许字段交 Agent，note 永不进入快照 | `records/mood`、`records/mood/new`、`records/detail/mood/{id}`、`records/edit/mood/{id}` | `GET/POST /mood-records`，`GET/PATCH/DELETE /mood-records/{id}`；授权目标为 `/patients/me/consents`、`/consent-notices` | 手工 CRUD 与分页接真实 API，五档映射且 `emotion_tags=[]`；note 只在本人详情/编辑内存态，登出/离页清草稿；授权管理和趋势未接入 | T105–T115、T117、T145–T146；A46–A52；UI-04/05/06 | F14 后端子范围 verified；Android 手工 CRUD 的自动化、模拟器和真实 phone-demo API 场景已通过，授权由后端最终栅栏并映射 `CONSENT_REQUIRED`；视觉、授权管理与趋势待验 |
| 17 | [开始建档](../design-reference/android-ui-baseline/pages/page16_开始建档.png) | F01 注册前置采集；仅内存草稿；最终一次提交业务后端，无 Agent | `auth/register/profile` | 告知从构建资源 `registration-notices.json` 读取；齐备后由注册流程 `POST /auth/register` | 两项独立明确同意后才收集出生年份和提交；取消/离页清密码草稿；邮箱验证不是已登录 | T01c–T01g、T01i、T01k；UI-01/02 | Repository 真实 API 链路通过；未覆盖此页面；页面级 E2E 待验收 |
| 18 | [历史报告](../design-reference/android-ui-baseline/pages/page17_历史报告.png) | F08/F11；任务历史和不可变输入摘要由业务端保存，Agent 不参与客户端展示 | `analysis/history` | `GET /analysis-tasks`、`GET /analysis-tasks/{task_id}` | 游标/筛选稳定；历史 mood 计数取任务快照，不按当前记录重算；分页错误保留游标 | T66–T71、T111–T112、T126–T127；A40/A52；UI-05 | 业务后端 verified；真实 Agent 结果可能未有；Android 否 |
| 19 | [运动记录](../design-reference/android-ui-baseline/pages/page18_运动记录.png) | F07；手动活动 CRUD 与统计由业务端，Agent 仅可能消费许可快照 | `records/activity` | `GET/POST /activity-records`、`GET/PATCH/DELETE /activity-records/{id}` | 无数据不等于没有活动；版本冲突/软删/离线 | T20–T21、T87、T118；A23–A24；UI-04 | 后端 verified；Android 否 |
| 20 | [设置](../design-reference/android-ui-baseline/pages/page19_设置.png) | F13/F12；设置枢纽及授权、通知偏好、注销/导出均由业务端 | `settings`、`privacy/center`、`privacy/consents` | `/patients/me/consents`、`/consent-notices`、`/notifications/preferences`、`/patients/me/account-deletion`、`/privacy/exports` | 授权撤回立即更新能力；注销冻结/进度独立；导出 preview 后需再次确认；下载能力仅内存 | T42–T47、T92–T98、T122–T123、T141–T144；A43–A45；UI-10 | 后端 F13 implemented，注销/导出子范围有验收；Android 否 |
| 21 | [登录](../design-reference/android-ui-baseline/pages/page20_登录.png) | F01；邮箱认证/会话恢复和资料读取属于 APP + 业务端 | `auth/login` | `POST /auth/login`；refresh/logout；成功后 `GET /patients/me` | 401 不枚举账户；未验证/错误凭据一致；资料 404 清会话并显示一致性错误 | T01、T01a–T01b、T01g–T01i、T01k、T49；UI-01/02 | Repository 真实 API 链路通过；未覆盖此页面；页面级 E2E 待验收 |
| 22 | [注册](../design-reference/android-ui-baseline/pages/page21_注册.png) | F01；注册收集邮箱/密码草稿；出生年份与独立健康数据同意在第17页完成后再统一提交 | `auth/register` | `POST /auth/register`（仅两项明确同意且第17页完成后调用） | 邮箱 + 密码；confirmation password 仅客户端；隐私与健康处理独立同意；成功后邮箱验证，不直接入首页 | T01c–T01i、T01k；UI-01/02 | Android 运行时已接线；页面级 E2E 待模拟器验收；Release 注册因生产批准告知制品规范/签核未冻结而 fail-closed |

### 联调判定

认证运行时已通过双 Retrofit 客户端接入业务 API：认证/refresh 使用无 Bearer、无 Authenticator 的客户端；资料/登出使用 Bearer 与 session Authenticator，refresh callback 回到纯认证客户端，避免递归。登录与冷启动恢复均须成功读取 `/patients/me` 才进入受保护导航；资料 404 清除本机会话并显示安全错误。Debug 使用 JSON 构建资源；只有 `development_test_only` 制品可用，因此 Release 注册 fail-closed。生产批准制品的 classification/schema 与签核尚未冻结，Debug 告知也仅可用于合成账户。T01k 已覆盖真实 phone-demo API 链路，但不覆盖页面交互。

今日和记录根 Tab 已有原生内容，Analysis 仍为不连接智能体的安全占位，“我的”当前只保留退出；22 个原型页面迁移尚未完成。F03/F04/F05/F14 手工记录页面与 Repository 已通过当前切片的 JVM、Compose 和全量 instrumentation 门禁，真实 phone-demo 也已覆盖 CRUD、分页、症状状态历史、409 及登出后 401。T01k 认证联调仍是独立证据，不等同于 Compose 认证页面 E2E。Agent 仍只在服务端消费冻结快照，真实 Agent E2E 为独立验收项；旧 `app/` 的结果不计入 Android 页面验收。

阶段证据：当前 Debug 构建通过，JVM 51/51、`RecordScreensTest` 9/9、全量 instrumentation 23/23。真实记录 API 专项证据 `android/build/emulator-evidence/phone-demo-records-20261020-014006-b480ec9f/summary.json` 状态为 `passed/complete`，测试环境为既有本机 phone-demo Compose 和模拟器 `10.0.2.2` 桥接。六张主要页面的固定 profile 截图、overlay/diff/result.json 与逐页 ≥80% 且无明显错误的视觉对比仍待归档；发布前真机、22 页整体迁移、F08 Agent E2E 和认证页面级 E2E 也不在本次通过结论内。

## 3. 原型与契约差异、导航风险

- 登录页把账号占位写成“手机号 / 邮箱”，注册页只收手机号；与 P0 邮箱 + 密码契约冲突。原生页面必须使用邮箱，不能复刻手机号/SMS 入口。
- 注册页截图把用户协议和隐私政策合在一个勾选项中；冻结流程要求 privacy_policy 与 health_data_processing 分开告知/同意。出生年份在第17页明确授权后收集，再将两页内存草稿合并成一次注册请求；注册成功后走邮箱验证与登录。
- 今日页截图显示“王先生”、本周记录天数、今日用药、餐食和趋势等完整数据。昵称可空且系统不收集性别/真实姓名，必须把这类内容视为原型演示数据；生产页只能显示服务端本人数据，昵称为空使用中性占位，空响应不可伪装成示例记录。
- 首页快捷记录卡横向布局在截图右侧被裁切，未见完整“心情/运动”入口；若实现横滑，应提供可发现的滚动/分页线索并确认触控可达，避免把页面截断误读为入口缺失。
- 22 张静态图只能核验画面顺序、可见文案和边界；不包含点击关系，不能验证入口、系统返回、跨 Tab 栈或深链。原型源码基线曾静态审阅到运动项回欢迎页、助手“查看近7天排便”错误指向趋势、跨 Tab 共用返回栈等缺陷；这些是原源码的静态缺陷，不等于本次图片本身能证明跳转，原生路由须按规范重建并用路由测试验证。
- 设置页原型是业务入口，不另建与“我的”冲突的底栏；隐私中心从设置进入。AI 助手页未获批时隐藏或显示受限说明，不提供自由对话入口。
- 画面是高长屏导出，不能直接当成设备全屏的可见区域。Android 实现需确定状态栏、安全区、滚动容器、键盘和系统返回行为；每页状态至少覆盖 loading/empty/error/offline/disabled/no-permission/pending-confirmation 中适用的项。

## 4. 可重复截图叠图与差异验收

页面视觉相似度目标为每个已实现且可比较页面 **≥80% 且无明显错误**。该目标不表示当前 22 页均已达到；它是像素差异分数，不替代功能、无障碍、隐私状态或真机验收；未提供的页面状态不能以理想态截图代替。

1. 固定同一 Android 模拟器型号、分辨率/density、系统字体缩放、主题、语言、状态栏/导航栏、安全区和键盘状态；使用固定合成账号及数据。原图保持只读，记录 Android build、设备 profile、页面 route、状态 fixture 和截图时间。
2. 把原型与设备截图裁到同一内容边界（状态栏/系统导航栏按基准策略统一保留或一起裁掉），按等比例缩放到共同尺寸，禁止非等比拉伸。将对齐参数记录下来；如需平移，只允许一次人工确认并固化的内容原点偏移。
3. 输出 50% alpha overlay、绝对差异图、差异热图和机器可读 JSON。比较区域可用逐页 ROI/mask 排除仅限动态时间、电池/网络图标等非产品像素；所有排除区域需列入版本化 mask，不得遮掉布局、文案、头像、按钮或系统安全区差异。
4. 推荐确定性评分：对非 mask 像素计算 CIE Lab 的 ΔE76；将 ΔE76 > 12 标为差异像素，`similarity = 1 - 差异像素数 / 有效像素数`。页面分数需 ≥0.90；同时保留差异像素率和每个 ROI 分数，避免某个小而关键的错位被全页大背景稀释。阈值和算法版本写入结果 JSON。
5. 每个 route 至少验收原型对应的主要态；缺少状态图的 loading/空/错误/离线/禁用/无权限/待确认态，按功能文档和业务契约逐态留图，标记为“功能状态验收”，不要宣称有原型像素分数。

建议脚本接口（不新增运行时依赖或在本次提取时执行）：

```text
python tools/ui_compare.py \
  --manifest design-reference/android-ui-baseline/manifest.json \
  --page 01 \
  --actual artifacts/ui/android/page01_today.png \
  --profile artifacts/ui/device-profile.json \
  --mask artifacts/ui/masks/page01.json \
  --out artifacts/ui/results/page01 \
  --threshold 0.90 --delta-e76 12
```

`device-profile.json` 建议记录设备/模拟器、屏幕像素、density、字体缩放、Android/API 版本、状态/导航栏裁切策略、色彩空间及 fixture ID。脚本输入和输出建议：

| 输入 | 输出 |
|---|---|
| manifest 中对应原型图 + Android 截图 + profile + 可选逐页 mask | `overlay.png`、`diff.png`、`heatmap.png`、`result.json`；记录图像实际尺寸、缩放/裁切/偏移、mask 像素、Lab 差异像素、相似度、阈值、pass/fail |

### 关键头像/图片几何硬门禁

头像和重要图片不能只靠全页 90% 分数放行。对每个相关 ROI 单独保存 reference bbox 和实际 bbox（坐标按统一视口像素，换算为 dp 对比）：

- 外盒必须正方形，`aspect_ratio` 偏离 1.0 不超过 1%；图片绘制盒与容器中心重合，中心偏差不超过 1 dp；外盒 x/y/width/height 与原型锚点偏差各不超过 2 dp。
- 图片必须等比 `aspectFill/cover` 居中裁切，不拉伸；头像边框厚度与颜色分别测量，边框不得被图片覆盖/裁切。默认、加载成功、加载失败三态的盒几何完全一致。
- 首页/header 头像基准按 UI 源码规范为 44×44 dp；Profile 头像 76×76 dp，5 dp 白色内叠描边、可见图片区域 66×66 dp。截图以 Compose density 换算 dp 后检查，不用像素尺寸猜 dp。
- 图片内容缩放、裁切锚点和可见主体另设 ROI；误差超过 2 dp 或圆形轮廓有椭圆拉伸、溢出、偏心即硬失败，即使全页分数达到 90%。基准图没有该组件/锚点的页面不套用头像门禁。

## 5. 静态验收边界

静态输入清点、尺寸/哈希记录和页面映射已完成；六张记录阶段参考页（今日、饮食、健康档案、排便、症状、心情）已有 Compose 实现，当前功能 instrumentation 已通过，但尚未形成固定设备 profile 下的完整截图、叠图和机器评分。未运行 ZIP 内代码，也未把静态原型当作点击路径证据。视觉评分通过后仍需无障碍检查与发布前真机门禁。
