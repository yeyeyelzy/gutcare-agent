# GutCare Agent 文档基线与索引

已采纳 ADR-0009：F02 私有文件上传、医疗档案与删除补偿，见 `ADR/0009-f02-private-file-workflow.md`。
已采纳 ADR-0010：F06 用药计划、日程与打卡，见 `ADR/0010-f06-medication-schedule-checkin.md`。
已采纳 ADR-0011：F02 医疗候选与患者逐字段确认，见 `ADR/0011-f02-medical-candidate-confirmation.md`。
已采纳 ADR-0012：F08 冻结快照分析任务闭环，见 `ADR/0012-f08-frozen-analysis-task-workflow.md`。
已采纳 ADR-0013：F09 建议与证据业务闭环，见 `ADR/0013-f09-advice-evidence-lifecycle.md`。
已采纳 ADR-0014：F12 P0 站内通知与事务 outbox，见 `ADR/0014-f12-in-app-notifications.md`。
已采纳 ADR-0015：F07 活动记录与 F11 确定性历史趋势，见 `ADR/0015-f07-activity-f11-history-trends.md`。
已采纳 ADR-0016：F13 隐私导出、注销全量清理、审计和恢复重放，见 `ADR/0016-f13-privacy-deletion-export.md`。
已采纳 ADR-0017：F02 解析结果 outcome 与 A03 疾病专属建议适用性，见 `ADR/0017-f02-parse-outcomes-and-applicability.md`。
已采纳 ADR-0018：F02 已确认检验结果的保守冲突管理，见 `ADR/0018-f02-confirmed-lab-result-conflicts.md`。
已采纳 ADR-0019：F14 心情记录、两项独立授权及受控 F08 快照输入，见 `ADR/0019-f14-mood-records-and-consent.md`。
已采纳 ADR-0020：注册告知单一来源、生产 fail-closed 与登录后资料引导，见 `ADR/0020-registration-notice-source-and-profile-bootstrap.md`；仓库注册、心情/敏感图片授权及 F03/F04 purpose-specific 图像识别开发/测试告知制品分别见 `../contracts/consent/registration-notices.json`、`../contracts/consent/consent-notices.json` 和 `../contracts/consent/record-image-recognition-notices.json`，均不是生产法律文案。
已采纳 ADR-0021：F03/F04 记录图片附件与独立识别候选闭环，含 Diet request-local 候选分组、名称先决事实落点、类型化 FK 附件快照、显式患者 retry 和 Stool Bristol-only 候选；ADR-0023 补充附件响应完整性与安全预览授权。Android 可按 attachment ID 申请同源五分钟下载 grant，每次预览重新申请；永久图片 URL 不持久化。该 ADR 的 APP 源码实现与验收状态仅描述旧 `app/` 归档，不构成 Android 原生工程验收；原生迁移遵循 ADR-0022。业务后端边界、真实 Agent 端到端和 production purpose-specific notice 法律签核状态不变。
已采纳 ADR-0024：F04 Agent Bristol 1–7 分类直接作为 AI 辅助分类展示，不要求患者确认/决定，且绝不写入 `health.stool_record.bristol_type`；不进入 F10/F11/F08 确认事实。Diet 候选仍由患者逐字段确认。该分类不作诊断、出血或风险判断；详见 `ADR/0024-f04-direct-bristol-display.md`。T153 最小 mock E2E 已通过，未调用外部模型；T152 中患者 accept 的 F04 记录属于 ADR-0024 前历史证据，不作为当前设计验收，也不构成当前 Android UI 验收。
已采纳 ADR-0025：F04 患者端不再提供手工选择/推测 Bristol 类型；排便记录仅凭发生时间即可保存，图片识别后的 Agent Bristol 分类只在图片识别区直接展示，API 字段为兼容保留。详见 `ADR/0025-f04-agent-only-bristol-display.md`。
已采纳 ADR-0026：F03 饮食图片识别患者端只展示待确认/已确认食物名称，隐藏置信度、不确定性、处理状态与类别/份量候选；类别/份量须由另行批准的患者端界面确认。详见 `ADR/0026-f03-patient-facing-food-name-review.md`。
已采纳 ADR-0027：F03 新增饮食页支持图片优先录入；图片入口仅创建不含饮食事实的受控记录壳并进入既有安全上传/识别闭环。详见 `ADR/0027-f03-image-first-diet-entry.md`。
APP 22 页原型事实、导航规范、视觉验收与编码前 G1 数据契约门禁见 `UI原型审查与页面导航规范.md`。
比赛演示数据离线构建器的输入白名单、执行方式及初始化限制见 `demo-data-tooling.md`。
本机 phone-demo Agent profile、dispatcher、mock 闭环及脱敏证据见 `phone-demo-agent-f08.md`；F08 受控证据摘要见 `evidence/F08-phone-demo-mock-E2E-20261021.md`；F02 live 最小 E2E 脱敏记录见 `evidence/F02-phone-demo-live-E2E-20261022.md`；2026-10-21 Agent live 与原生 Android 图片识别脱敏记录见 `evidence/agent-live-android-20261021.md`。Agent 来源、未提供 LICENSE 及 2026-10-23 用户确认的当前项目公开发布授权范围见 `../agent/PROVENANCE.md`；该授权不构成开源许可或第三方再许可。2026-10-21 本机 mock 验证：F08 task 为 `partial` 且患者可读回结果；同一 Compose F08→F09 mock 路径通过，患者 `/api/v1/advice` 有该 task 对应 1 条建议；Diet mock 请求通过候选回调和患者确认。更早 F04 mock 患者确认属于 ADR-0024 前历史证据；当前 F04 Bristol 直接展示的最小 mock E2E 通过（T153，未调用外部模型），该证据不代表 Android UI/仪器验收。另已修复 Agent 容器缺少 live DNS/HTTPS 出网的问题：一张合成餐食图的 F03 direct live 冒烟 15.49 秒返回 3 个候选；F04 direct live 合成调用约 11.02 秒、0 retry。原生 Android 模拟器 F04 live accept 链路发生于 ADR-0024 前，仅为历史执行证据。F09 live smoke 在将 AdviceAgent 检索范围限定为 approved 知识、保持 mapper 策略不变后复验通过；只完成输出结构校验，未提交业务 callback，不构成完整后端 callback E2E。F02 受保护 claim API、`medical_parse_dispatcher` 与 Agent bridge 的 T154 本机 live 最小闭环已通过：文档列表 200、状态 `needs_confirmation`、outcome `extracted`、候选 2 条、患者确认事实 1 条、下载授权 200 且文件非空、未授权访问 401。该单次证据不代表真实识别准确率、临床有效性、完整 Android UI/真机或生产验收；患者逐字段确认前候选不构成事实。F08 ViewModel 定向测试 4/4 与 `assembleDebug` 已通过；本轮 F08 UI 与生产完整验收范围仍未完成。
比赛本机逐步操作、旁白、合成素材、证据级别和待验收标记见 `比赛本机演示手册.md`。
竞赛提交补充材料见[《可运行程序包、部署与环境配置说明》](可运行程序包、部署与环境配置说明.md)和[《开源组件、第三方模型与数据使用说明》](开源组件、第三方模型与数据使用说明.md)；前者覆盖本地运行、构建与环境边界，后者覆盖依赖、模型、外部服务、数据和导入源码许可限制。本次 Android 受限构建、签名覆盖安装与模拟器更新的处置记录见[《Android 构建与模拟器更新排障记录》](Android构建与模拟器更新排障记录-20261023.md)。
Agent 源码公开发布至当前项目仓库的授权已于 2026-10-23 确认；源仓未提供 LICENSE，授权范围不包括开源许可或第三方再许可，详见 `../agent/PROVENANCE.md`。再次进行 live 冒烟时需由操作者在本机配置 API Key，不要通过聊天发送或提交到仓库。
实体手机经 Cloudflare Quick Tunnel 的隔离 test/demo-only API 联调步骤、边界与清理方式见 `手机 HTTPS 演示联调指南.md`；不替代正式部署运维手册。
源码输入哈希、视觉令牌、资产隔离导入、静态跳转缺陷及 GcAvatar 几何基线见 `UI源码基线与导入规范.md`。
认证公开页面和组件化交付跟踪见 `前端开发与前后端联调计划.md` 的 B01-2 小节及 `需求追踪矩阵.md`。
F02 的表/状态/API/隐私/测试追踪增补见 `F02-文件与医疗档案实现补充.md`。
后端完成性与验收证据归档见 `后端交付验收报告.md`；该报告区分已实现证据、独立验收状态与外部依赖。

> 基线版本：V1.10（原生 Android 记录切片模拟器与真实 API 验收同步）
> 冻结日期：2026-10-20
> 工作目录：仓库 clone 根目录（不依赖固定盘符或绝对路径）

已采纳 ADR-0022：患者端迁移至原生 Android，见 `ADR/0022-原生Android客户端.md`；Android Studio 是唯一客户端开发/验收环境，旧 `app/` 只读归档，当前不做 iOS。

原生 Android 当前交付状态以 `Android页面-功能-API-测试映射.md`、`Android原生迁移工作准则.md` 和 `需求追踪矩阵.md` 的 `AND-*` 条目共同为准。最新 Android 静态门禁为 117/117；Lint 0 error、16 warning。默认完整仪器测试集 53 项、0 失败。综合 run 的截图阶段有历史失败；定向真实 PNG 截图 3/3 通过。SMTP 有界重试/503 契约修复后定向回归 50 passed，修复镜像已确认；分类 live gate Repository 1/1、UI 0/1，失败 checkpoint `registration_submit`。缺少该测试窗口 SMTP/Mailpit 证据，认证仍未通过，不得宣称完成。P1 phone-demo 汇总证据见 `../android/build/emulator-evidence/phone-demo-p1-20261020/summary.md`，仅覆盖列明业务 API，未调用 Agent。2026-10-21 F08 live 合成冒烟通过后端→dispatcher→Agent→callback→患者查询，终态 `partial` 且 `result_present=true`；另有 Android API 37 模拟器图片识别 live 合成端到端记录，详见 `evidence/agent-live-android-20261021.md`。这些证据只覆盖列明链路，不代表医学质量或完整验收。F08 ViewModel 定向测试 4/4 与 `assembleDebug` 已通过；F02 服务侧 T154 本机 live 最小链路现已通过，Android UI/仪器、真实识别质量、生产法律/医学审核与发布前真机门禁仍独立跟踪；候选必须经患者逐字段确认后才写入事实。视觉目标为每页至少 80% 且无明显视觉错误；F06/F10/F11 已有探索性分数，不等于正式验收。全页面视觉及发布前真机门禁分别跟踪，不得标成完成。用户协助事项见 `明日需用户协助事项.md`。旧 `APP-B*` 条目和 `app/` 自动化只保留迁移前追溯价值。

尚未完整迁移、尚未形成真实端到端证据或仅有条件测试覆盖的非智能体客户端能力，按 Fxx 与验收判据汇总在 `Android非智能体功能迁移与验收缺口清单.md`；该清单不得替代页面映射与追踪矩阵。

## 1. 文档用途

本目录是产品、APP/业务后端、智能体、测试和运维共同使用的唯一设计基线。文件名不再带 `(1)`；任何复制件不具有基线效力。

## 2. 主题权威矩阵

| 主题 | 权威文档/契约 | 冲突处理 |
|---|---|---|
| 产品目标与范围 | `设计方案.md` | 与详细行为冲突时以详细功能设计为准 |
| 用户行为、优先级、验收 | `详细功能设计.md` | 与接口/表实现冲突时先保持业务语义，再同步契约 |
| 两开发方责任 | `APP及业务后端与智能体系统开发边界.md` | 所有排期和任务分派必须遵守 |
| 技术栈与实现约束 | `技术方案.md`、ADR | 已接受 ADR 优先于旧正文，并须回写正文 |
| 字段、表、生命周期 | `数据库设计方案.md`、`数据字典与状态机.md` | 数据字典约束枚举；数据库文档约束物理模型 |
| HTTP 请求/响应 | `../contracts/openapi/gutcare-v1.yaml`、`../contracts/agent/agent-v1.yaml` | 机器可读契约为实现和契约测试依据 |
| 隐私与删除 | `隐私授权与数据生命周期.md` | 更严格的适用法律/正式隐私政策优先，变更须评审 |
| 原型页面、导航、视觉对照与 UI 验收 | `UI原型审查与页面导航规范.md` | 原型内容事实不等于跳转验证；功能/API 语义仍以 ADR 与机器可读契约为准 |
| 医疗安全规则 | `医疗安全规则规范.md` | 仅 `approved` 规则可在生产启用 |
| 测试与发布门禁 | `测试方案.md`、`部署运维手册.md` | 未满足阻断门禁不得发布 |
| 需求覆盖 | `需求追踪矩阵.md` | 每次功能交付同步更新 |

## 3. 决策优先级

同一主题内按以下顺序处理：已批准且未废弃的 ADR → 当前机器可读契约/数据字典 → 当前专题文档 → 总体文档。用户新确认的需求必须先落为 ADR 或文档变更，不能只存在于聊天记录。

## 4. 已冻结的跨文档结论

- 平台：现阶段仅原生 Android APP；Android Studio 是唯一客户端开发/验收环境；旧 `app/` 只读归档；当前不做 iOS，也无患者 Web 端。具体迁移与阶段门禁以 ADR-0022 和 `Android原生迁移工作准则.md` 为准。
- P0 登录：邮箱 + 密码；标准 SMTP，开发使用 Mailpit；无手机号/SMS。
- F14 心情记录使用 `health.mood_record`；独立 `mood_data_processing` 和 `mood_ai_sharing` 授权控制记录处理与智能共享；Agent 快照仅含受控等级/标签/时间，不含备注。
- F11 心情趋势只对本人结构化 `mood_level` 确定性分桶，不读备注/标签且不依赖 Agent 共享授权；分析预览使用冻结计数字段，任务实际纳入数保存在不可变快照摘要。
- 资料最小化：昵称可空、出生年份必填；不收集完整生日、身份证号、性别、身高、体重。
- HTTP：成功直接返回 DTO/分页对象或 `204`；错误为 RFC 9457 Problem Details。
- 数据：PostgreSQL 18.x；业务库与知识库分数据库；文件存 MinIO/S3，缓存/队列用 Redis。
- 智能任务：业务 Worker 唯一 claim，智能体不二次 claim；路径统一 `/internal/v1` 与 `snake_case`。
- 用药：`confirmation_status` 与 `plan_status` 分离。
- 删除：立即不可见；单记录 7 天后物理删除，注销 30 天内完成，备份最长 35 天轮转，去标识安全审计 180 天。
- F13：注销 receipt 只存 hash；操作与账户外键解耦；独立 privacy worker inventory/lease/step ledger；恢复后 replay 成功才开放 readiness；导出经同源 gateway 单次短时能力下载。
- 医疗安全：工程团队不制定临床阈值；未审核规则只能测试。
- F04 图像识别：Agent Bristol 1–7 输出仅作为 AI 辅助分类直接展示，不形成患者确认事实，不进入 `health.stool_record.bristol_type`、F10/F11/F08 或建议输入；Diet 识别仍须患者逐字段确认。详见 ADR-0024。
- 授权版本必须由服务端逐 consent type 与告知摘要哈希绑定；privacy policy 撤回唯一入口为账号注销，提交时立即冻结账户并撤销全部刷新会话。

## 5. 变更规则

改变平台、数据库边界、认证方式、API 兼容性、状态机、数据保留期或医疗安全策略时必须新增 ADR，并更新所有受影响文档、契约、测试和追踪矩阵。版本号采用 `V主.次`；正文与契约的提交必须原子化。
