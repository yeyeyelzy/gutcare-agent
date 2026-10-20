# Android 原生迁移工作准则

本文依据 ADR-0022，约束患者端从旧 `app/` 归档迁移到 `android/` 原生工程的开发、验收与证据记录。客户端开发、构建、调试和验收统一使用 Android Studio。

## 阶段与门禁

| 阶段 | 工作范围 | 通过条件 |
|---|---|---|
| 0. 基线核对 | 阅读需求、UI、数据字典、OpenAPI 和 ADR；建立功能到页面/API/测试的映射 | 不改变已冻结业务语义；识别旧客户端仅可参考的内容 |
| 1. 原生工程基座 | 已建立 `android/` Kotlin/Compose 工程、应用启动、导航、网络与会话基础、主题和测试结构；认证运行时已接入业务 API | Debug 构建、lint、JVM 单测通过；认证 Repository 的 phone-demo 真实 API 链路已由 T01k 验证；认证页面级 E2E 与 22 页迁移仍未完成 |
| 2. 功能迁移 | 进行中：邮箱注册/验证/登录、刷新恢复、本人资料引导和登出已连接真实认证 API；F03 饮食、F04 排便、F05 症状和 F14 心情已具备受保护列表、新增、详情、编辑和删除路由，症状详情读取状态历史，真实业务 API Repository 已接线。今日页和记录入口已替换占位内容。健康档案仅展示本人资料和明确的未接入状态，Analysis 仍为不连接智能体的安全占位，“我的”仅保留退出入口。告知资源从冻结 JSON 构建并在运行时校验；`UnconnectedAuthWorkflow` 仅作为 NavHost 默认/测试回退，不用于 MainActivity 运行时 | 每个交付切片映射到 Fxx、API、状态机和测试编号；完成后逐项联调并检查越权或敏感信息泄漏；页面功能验收不得替代视觉评分和发布前真机证据 |
| 3. 模拟器验收 | 在 Android Studio 模拟器完成页面、导航、API 联调、错误态和权限相关可测流程 | 记录模拟器镜像/API level、应用构建标识、环境、合成数据集、测试编号和结果；阻断缺陷清零 |
| 4. 发布前真机门禁 | 对设备相关能力进行 Android 真机安装和场景验证 | 归档设备型号、Android 版本、构建标识、网络与合成数据集、用例及截图/录屏；系统能力相关问题关闭 |

本机认证联调门禁 T01k 已通过（2026-10-20；`android/build/emulator-evidence/phone-demo-auth-20261020-130223-f79a9c61/summary.json` 与 `junit-summary.json`，1/1）。脚本 `scripts/test-phone-demo-android-auth.ps1` 通过 Android Studio 模拟器 `emulator-5580` 的 `10.0.2.2` 桥接连接本机 phone-demo Compose；instrumentation 使用随机合成账户，经原生认证 Repository 依次完成注册、Mailpit 邮箱验证、登录、本人资料读取、refresh rotation/资料刷新和退出，并验证 SecureSessionStore 清理。该次执行复用了启动前已运行且健康的 Compose 容器，证据记为 `preexisting_project_preserved`，没有停止既有服务；只归档无凭据状态摘要和模拟器截图。T01k 验证 Android 网络栈、Repository、后端真实 API 与 Keystore 会话存储，不经过 Compose 认证页面；页面级认证 E2E 仍待验收。

Compose 生命周期按项目 label 执行 fail-closed：启动前查询同名项目的全部容器（包括 stopped），记录完整 container ID 与状态；只要存在任意容器就不调用 `up` 或 `down`，要求全部容器 running 且本机 health/live 返回 200，否则失败并原样保留。仅启动前容器集为空时才启动；成功后记录本次容器 ID。默认清理要求启动前为空、当前 ID 集合与启动后记录完全一致，并由 `phone-demo-down.ps1 -ExpectedContainerIds` 再校验一次；ID 集合改变或无法证明归属时拒绝清理并警告。演示数据卷始终保留。

模拟器通过表示当前阶段可验收，不代表发布前真机门禁已通过。未取得真机证据时，发布状态不得标记为完成。

截至 2026-10-20，本地验证门禁为 backend 207 项、Android 31 项通过。Android 原生认证与记录切片已有真实 phone-demo API 证据；F02 原生档案 UI 已支持 store-only 存档，phone-demo 文件 API E2E 通过真实 ClamAV clean、档案查询及授权下载。F02 的证据不覆盖 Android 上传端到端、analyze、Agent 候选生成/回调或服务端候选确认链路。今日页相似度 80.69% 仅为探索性分数，尚未满足正式截图采集、全页覆盖和对齐证据要求。旧 `app/` 只读归档。当前工作成果仍不代表 F06/F07/F08/F09/F10/F11/F12/F13 全部迁移或发布前真机门禁通过。

仓库当前仅有 `development_test_only` 注册告知制品。它可用于 Debug 合成账户联调，不可用于真实患者。Production/Release 注册保持 fail-closed；生产批准制品的 classification/schema 与签核流程尚未冻结，正式发布前需完成 ADR/制品规范与签核门禁。

## 路径与保留边界

- `android/`：唯一活跃的 Android 原生客户端工程；使用 Android Studio 开发和验收。
- `app/`：旧 uni-app 工程，只读归档。禁止新增功能、修复、依赖升级、格式化或生成文件；不得将其构建结果作为 Android 验收证据。
- `backend/`、`contracts/`、数据库迁移及智能体服务：本次客户端迁移不修改其业务边界。只有发现确需改变契约时，先按既有 ADR 流程单独评审，不在客户端迁移中隐式扩展。
- 当前只开发 Android；iOS 不属于本阶段范围。患者端仍为原生 APP，不新增 H5/Web 替代实现。

## 迁移与证据规则

1. 将旧客户端作为需求线索和历史实现参考；产品行为以已接受 ADR、功能设计和机器可读契约为准。
2. 每个迁移切片记录 Fxx、API operation、涉及实体/状态机、测试编号及证据位置。
3. 使用合成账户、合成记录和合成文件进行联调与截图；不得将密码、验证码、Token、报告正文、图片永久 URL、完整 prompt 或模型原始输出写入日志或证据。
4. 阶段证据至少记录环境、Android Studio/模拟器版本信息、应用构建标识、测试编号、执行结果及失败处置。模拟器证据与真机证据分别标注，不互相替代。
5. 真机发布前门禁重点覆盖安全存储、文件选择/上传、系统权限、通知、键盘与安全区、后台切换/进程恢复、网络变化和深链。按功能适用范围取证。
6. 服务端、OpenAPI、数据库和智能体边界继续遵守仓库既有规则：APP 仅访问业务 API；智能体只能读取任务冻结快照，不能直接写业务表。

## 验收结论用语

- `模拟器阶段已验收`：Android Studio 模拟器阶段门禁通过。
- `发布前真机待验`：尚未完成真机证据或仍有设备行为待验证。
- `发布前真机已验收`：相关 Android 真机场景均有可追溯证据且门禁通过。

不得以旧 uni-app 自动化、CLI 导出、Web 预览或模拟器截图表述为 Android 真机已验收。
