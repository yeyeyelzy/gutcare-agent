# 比赛演示素材

本目录中的说明和 `manual-input-examples.json` 均为虚构合成示例，仅供隔离的比赛演示与界面填表示范，禁止临床使用。没有从 `GutCare测试包_v4.zip` 导入、复制或改写任何内容；该压缩包未作为本演示数据来源。

## 已生成素材

- `synthetic-medical-report.pdf`：程序化从零合成的虚构报告样张，可用于 F02 档案上传演示。
- `synthetic-meal.png`：使用内置图像生成工具从零生成的虚构餐食图像，可用于 F03 演示。
- `synthetic-stool.png`：使用内置图像生成工具从零生成的虚构示意图，可用于 F04 演示。

三个素材均仅限 `demo_only` 隔离演示，不得用于临床。模拟器中已放置于 `/sdcard/Download/GutCareDemo/`；在 Android 文件选择器中进入 **Download → GutCareDemo** 即可选择。新增素材必须从零合成并由项目负责人确认来源；不应以简单遮挡身份信息的方式处理真实医疗材料。

## 安全与使用边界

- 所有示例均标记 `synthetic=true`、`for_testing_only=true`、`clinical_use_allowed=false`；这些标记是来源声明，本身不能证明数据来源。
- JSON 是跨功能手工输入演示清单，不是 `scripts/demo_data.py build` 的白名单输入。构建器只接受文档规定的 diet、stool、symptom 结构化字段；不得把本文件直接传给构建器。
- 注册示例中的密码值 `LOCAL_SECRET_CARD` 只是提醒操作者从本地秘密卡片/密码管理器注入演示密码的占位文本，不能作为真实密码提交。不要把密码、验证码、Token、账号凭据写入仓库。
- 手工示例中的演示邮箱仅用于本地/隔离演示配置；注册告知版本必须来自与目标后端同步的告知制品，不能使用占位版本绕过服务端校验。
- 不得将演示数据用于真实患者、临床决策、诊断、处方调整或剂量建议；图片识别候选不能代替患者确认事实。
- 源文件及构建输出应放在已忽略的 `.demo-source/` 与 `.demo-output/`，不要提交 Git。检查 `.gitignore` 可见这两个目录已被忽略。
