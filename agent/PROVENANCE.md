# 来源与导入记录

- 源仓库：<https://github.com/caoyimiao0625-alt/gutcare-agents>
- 导入 commit：`40ec9f434632da587a66f4b10bf0e5e72693aa78`（2026-10-20，`feat: add ready-to-run F08 integration setup`）
- 导入日期：2026-10-21
- 后续同步：已只读核对上游默认分支 `main` HEAD `f28a26e7da8566b2420ec46ab9f43abc2e1b61a3`（2026-10-21），同步 F08 的可选 F09 hook、F09 durable delivery、F03/F04 图片候选适配与相关测试/文档。该 SHA 是本次同步来源，不替代原始导入 commit。
- F02 同步：按用户提供并从源仓库核验的 commit `6662ebb7ccbf4149eb787de6b5c4bbdc56e57129`（`feat: add F02 medical parse agent bridge`）同步 F02 Agent bridge 的核心行为，并适配当前仓库的 F08/image Agent API、phone-demo Compose profile 与当前契约。上游原测试已缩减为本仓定向契约测试；业务 claim worker 由主仓 backend 实现提供。
- F08 综合归纳适配：已只读核对上游 commit `e3dd23701a027187ab57b38c2fec62b84df57633`（`Improve patient-facing F08 synthesis`，2026-10-22）。主仓未覆盖复制上游文件，而是在既有 F08 冻结快照与回调契约内采用同一方向：启用跨记录类型的 Trend v2 摘要提示词，并将旧结果缺省回退由“第一条观察”改为合并已校验观察；主仓契约仍是权威来源。
- 导入范围：运行包 `gutcare_agents/`、提示词、知识条目、测试、运维/联调工具、必要文档、Dockerfile、Compose、依赖清单及启动脚本。
- 未从源仓导入：Git 元数据、原有 Python 缓存、运行期/生成数据库、真实模型录制目录及独立测试数据包。为通过源仓自带文档路径单测，保留了被文档直接引用的静态 CI 示例文件；未配置或运行 CI。
- 发布授权记录（2026-10-23）：项目负责人确认拥有将 Agent 源码公开发布至当前 GutCare 项目仓库的授权，可继续公开提交该源码。上游源仓快照仍未提供 `LICENSE` 文件；该确认仅记录本仓库公开发布授权，不推定或补写开源许可证，也不授予第三方再许可或再发布权。
- 许可状态：源仓快照未提供 `LICENSE` 文件；本记录不推定或补写许可证。导入与发布授权分别记录来源版本和本仓库公开发布范围，不构成开源许可或对第三方的许可授予。
- 契约边界：源仓包含的固定版本后端契约副本仅作来源材料；主仓当前契约和 ADR 优先。本次未修改主仓业务契约。
- 同步边界：本次仅更新 Agent 运行代码、定向测试、live 图片冒烟工具及状态文档；未覆盖 `.env`、`data/`、`replays/`、固定契约参考副本或本文件原有安全边界。2026-10-21 已有本机 Compose F08→F09 mock 和 F03/F04 mock 患者确认 E2E 证据；这些不等于生产验收或真实模型效果验收。一次视觉模型层 live 冒烟等待后中断，结果不确定且未重试。Compose 最近确认恢复为 mock 且图片候选 fixture 关闭。
- 本地集成调整：Compose 与镜像的默认运行模式改为 `mock`；Compose 要求 shell 显式设置 `GCA_INTERNAL_TOKEN`，移除演示 token 和外部测试包挂载；补充本地启动说明。
- 测试副产物：离线单测在 `data/testtmp/` 生成了临时 SQLite 测试库，并在代码目录产生 Python `__pycache__`；均被 `.gitignore` 排除。当前执行环境的文件删除命令被安全策略拒绝，因此这些测试副产物仍留在工作树中，未纳入源仓导入。
