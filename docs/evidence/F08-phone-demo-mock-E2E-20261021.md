# F08 phone-demo mock E2E 脱敏证据

- 日期：2026-10-21
- 来源 Agent 仓库 commit：`40ec9f434632da587a66f4b10bf0e5e72693aa78`（来源与许可记录见 `../../agent/PROVENANCE.md`）
- 测试项：T150，本机隔离 phone-demo F08 mock 任务闭环
- 外部模型：未调用
- E2E 总体状态：`passed`
- 阶段：合成账户/测试授权准备、结构化输入、冻结任务创建、唯一 dispatcher 派发、Agent 读取任务输入、mock 结果回调、患者任务查询
- Agent 结果状态：`partial`
- 患者查询：`result_present=true`
- 结论范围：证明本机 mock F08 协议和任务路径可端到端运行；不证明真实模型质量、F03/F04 图片候选回调、F09 独立建议回调、标准 Python 3.12 镜像构建或 PDF 输入路径。

原始运行摘要位于被 `.gitignore` 排除的 `.demo-output/f08-agent/20261021-005531/summary.json`，仅为本机证据；本文件为可提交的脱敏摘要。原始文件不应解除忽略或提交。本文不含任务 ID、token、服务 URL、模型原始输出、账户/患者信息。

来源仓库没有提供 LICENSE。授权确认前，该 Agent 导入内容仍是公开推送阻塞项；本脱敏测试摘要不包含 Agent 源码或知识素材，不改变该许可状态。
