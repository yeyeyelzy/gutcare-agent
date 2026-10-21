# 来源与导入记录

- 源仓库：<https://github.com/caoyimiao0625-alt/gutcare-agents>
- 导入 commit：`40ec9f434632da587a66f4b10bf0e5e72693aa78`（2026-10-20，`feat: add ready-to-run F08 integration setup`）
- 导入日期：2026-10-21
- 后续同步：已只读核对上游默认分支 `main` HEAD `f28a26e7da8566b2420ec46ab9f43abc2e1b61a3`（2026-10-21），同步 F08 的可选 F09 hook、F09 durable delivery、F03/F04 图片候选适配与相关测试/文档。该 SHA 是本次同步来源，不替代原始导入 commit。
- 导入范围：运行包 `gutcare_agents/`、提示词、知识条目、测试、运维/联调工具、必要文档、Dockerfile、Compose、依赖清单及启动脚本。
- 未从源仓导入：Git 元数据、原有 Python 缓存、运行期/生成数据库、真实模型录制目录及独立测试数据包。为通过源仓自带文档路径单测，保留了被文档直接引用的静态 CI 示例文件；未配置或运行 CI。
- 许可状态：源仓快照未提供 `LICENSE` 文件；本记录不推定或补写许可证。导入只记录来源与版本，不构成许可证授予或法律判断。
- 契约边界：源仓包含的固定版本后端契约副本仅作来源材料；主仓当前契约和 ADR 优先。本次未修改主仓业务契约。
- 同步边界：本次仅更新 Agent 运行代码、定向测试、live 图片冒烟工具及状态文档；未覆盖 `.env`、`data/`、`replays/`、固定契约参考副本或本文件原有安全边界。2026-10-21 已有本机 Compose F08→F09 mock 和 F03/F04 mock 患者确认 E2E 证据；这些不等于生产验收或真实模型效果验收。一次视觉模型层 live 冒烟等待后中断，结果不确定且未重试。Compose 最近确认恢复为 mock 且图片候选 fixture 关闭。
- 本地集成调整：Compose 与镜像的默认运行模式改为 `mock`；Compose 要求 shell 显式设置 `GCA_INTERNAL_TOKEN`，移除演示 token 和外部测试包挂载；补充本地启动说明。
- 测试副产物：离线单测在 `data/testtmp/` 生成了临时 SQLite 测试库，并在代码目录产生 Python `__pycache__`；均被 `.gitignore` 排除。当前执行环境的文件删除命令被安全策略拒绝，因此这些测试副产物仍留在工作树中，未纳入源仓导入。
