# ADR-0006：项目本地 Python 运行时

- 状态：Accepted
- 日期：2026-10-14

## 背景

项目技术基线要求 Python 3.13。Codex 执行 `D:\Anaconda\python.exe` 返回 `STATUS_ACCESS_DENIED`，而该解释器路径本身存在。将其归因于 Codex 执行沙箱的访问限制是基于该错误和路径的推断，并非对机器策略的独立审计结论。

## 决策

将官方 CPython 3.13.16 x64 embeddable package 解压到仓库 `.runtime\cpython-3.13.16`，不运行全局安装器或修改系统配置。`python313._pth` 显式启用 `site` 并包含项目本地 `Lib\site-packages`，以允许在该目录安装和导入依赖。`scripts/resolve-python.ps1` 优先使用 `GUTCARE_PYTHON`，否则选择项目本地解释器，并拒绝非 3.13 版本；脚本输出可供调用方捕获的绝对路径，不回退到裸 `python` 或 Anaconda。

官方发布页给出的 Windows embeddable package (64-bit) SHA-256 为 `97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297`：<https://www.python.org/downloads/release/python-31316/>。需要 pip 时，使用 PyPA 的 `get-pip.py` 引导并安装到此解释器的本地 `site-packages`。运行时和下载缓存不纳入版本控制。

## 验证

通过 resolver 查询 Python 版本、`sys.executable` 和 pip 版本，并在可联网环境验证 embeddable package 的 SHA-256。此运行时只解决当前项目的本地执行需求。

## 回滚

删除本项目 `.runtime\cpython-3.13.16` 目录及下载缓存，并移除此 ADR 和 resolver；该决策不修改系统级 Python 配置。
