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
已采纳 ADR-0020：注册告知单一来源、生产 fail-closed 与登录后资料引导，见 `ADR/0020-registration-notice-source-and-profile-bootstrap.md`；仓库注册、心情授权及 F03/F04 purpose-specific 图像识别开发/测试告知制品分别见 `../contracts/consent/registration-notices.json`、`../contracts/consent/consent-notices.json` 和 `../contracts/consent/record-image-recognition-notices.json`，均不是生产法律文案。
已采纳 ADR-0021：F03/F04 记录图片附件与独立识别候选闭环，含 Diet request-local 候选分组、名称先决事实落点、类型化 FK 附件快照、显式患者 retry 和 Stool Bristol-only 候选，见 `ADR/0021-f03-f04-image-recognition-lifecycle.md`。该 ADR 的 APP 源码实现与验收状态仅描述旧 `app/` 归档，不构成 Android 原生工程验收；原生迁移遵循 ADR-0022。业务后端边界、真实 Agent 端到端和 production purpose-specific notice 法律签核状态不变。APP 当前契约不支持记录图片持久预览。
APP 22 页原型事实、导航规范、视觉验收与编码前 G1 数据契约门禁见 `UI原型审查与页面导航规范.md`。
比赛演示数据离线构建器的输入白名单、执行方式及初始化限制见 `demo-data-tooling.md`。
实体手机经 Cloudflare Quick Tunnel 的隔离 test/demo-only API 联调步骤、边界与清理方式见 `手机 HTTPS 演示联调指南.md`；不替代正式部署运维手册。
源码输入哈希、视觉令牌、资产隔离导入、静态跳转缺陷及 GcAvatar 几何基线见 `UI源码基线与导入规范.md`。
认证公开页面和组件化交付跟踪见 `前端开发与前后端联调计划.md` 的 B01-2 小节及 `需求追踪矩阵.md`。
F02 的表/状态/API/隐私/测试追踪增补见 `F02-文件与医疗档案实现补充.md`。
后端完成性与验收证据归档见 `后端交付验收报告.md`；该报告区分已实现证据、独立验收状态与外部依赖。

> 基线版本：V1.8（ADR-0021 类型化附件快照与显式 retry 增补）
> 冻结日期：2026-10-18
> 工作目录：`D:\GutCare_Agent`

已采纳 ADR-0022：患者端迁移至原生 Android，见 `ADR/0022-原生Android客户端.md`；Android Studio 是唯一客户端开发/验收环境，旧 `app/` 只读归档，当前不做 iOS。

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
- 授权版本必须由服务端逐 consent type 与告知摘要哈希绑定；privacy policy 撤回唯一入口为账号注销，提交时立即冻结账户并撤销全部刷新会话。

## 5. 变更规则

改变平台、数据库边界、认证方式、API 兼容性、状态机、数据保留期或医疗安全策略时必须新增 ADR，并更新所有受影响文档、契约、测试和追踪矩阵。版本号采用 `V主.次`；正文与契约的提交必须原子化。
