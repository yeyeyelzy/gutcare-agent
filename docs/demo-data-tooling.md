# 比赛演示数据构建

构建器只接受结构化白名单输入，并要求每条来源记录由调用方声明 `synthetic=true`、`for_testing_only=true`、`clinical_use_allowed=false`。这些标记只是项目方/调用方的来源声明，代码无法证明数据实际为合成数据。使用任何外部压缩包或数据集前，仍须由主团队提供并确认合成来源证明；本工具不证明压缩包来源或数据不可识别。未知字段一律拒绝，错误信息不包含源文件内容或字段值。

## 离线构建

```powershell
python scripts/demo_data.py build <source.json> <demo-bundle.json>
```

输入 schema 为 JSON 对象：`schema_version` 固定 `1.0`，`records` 最多 500 条。每条允许 `cohort`（`cohort_a`/`cohort_b`）、`record_type`（diet/stool/symptom）、`occurred_day`（0–29）和结构化 `payload`。Diet 仅支持 meal_type 与 item 的 name/category_code/amount_text；Stool 仅支持 Bristol 1–7；Symptom 仅支持受控 symptom_code、severity 和状态。拒绝任何额外属性，包括媒体、OCR、报告正文、自由文本/notes、participant/source ID、UUID、URL/path 和精确时间戳。

示例仅用于说明输入格式，字段值为虚构合成样例；示例本身也不能证明任意其他输入的来源：

```json
{
  "schema_version": "1.0",
  "records": [
    {
      "synthetic": true,
      "for_testing_only": true,
      "clinical_use_allowed": false,
      "cohort": "cohort_a",
      "record_type": "diet-records",
      "occurred_day": 3,
      "payload": {
        "meal_type": "lunch",
        "items": [{"name": "Synthetic rice", "category_code": "grain", "amount_text": "one bowl"}]
      }
    },
    {
      "synthetic": true,
      "for_testing_only": true,
      "clinical_use_allowed": false,
      "cohort": "cohort_b",
      "record_type": "stool-records",
      "occurred_day": 7,
      "payload": {"bristol_type": 4}
    }
  ]
}
```

构建结果生成全新 UUID，将时间映射到虚构的 2026-01-01 起 30 天区间，并只允许最多两个 cohort。Diet 输入名称不进入 bundle，而被映射为 `Demo food 1` 等固定展示名，类别和份量写为 `null`；bundle 标记 `demo_only`、`synthetic_only`、schema 版本和创建时间。输出标签描述处理意图，不是对来源真实性的证明。该结果只能用于隔离演示环境，不得用于临床。

输入源、输出 bundle 和账号密码不可提交到 Git；仓库 `.gitignore` 已忽略 `.demo-source/`、`.demo-output/`、`demo-source*.json`、`demo-bundle*.json`。不要把真实数据拷入这些目录。

## 比赛演示环境初始化

初始化仅面向隔离的比赛 demo 环境，必须显式 `--demo-mode`。必须显式指定 `--registration-notice` 指向与目标后端同步的告知 JSON 制品；不提供默认制品路径。初始化器仅接受 `development_test_only` / `not_approved_for_production` 制品，校验 schema、两个注册授权版本及摘要哈希与制品内 `backend_config` 一致。后端注册 API 会再次校验版本；任一非预期状态均 fail-closed，错误不显示远端响应正文。

```powershell
$env:GUTCARE_DEMO_API_BASE = 'https://demo.example.invalid'
$env:GUTCARE_DEMO_EMAIL_PREFIX = 'gutcare-demo'
$env:GUTCARE_DEMO_EMAIL_DOMAIN = 'example.invalid'
# 可选：密码由进程环境注入；不设置时逐个使用 getpass 交互输入
$env:GUTCARE_DEMO_PASSWORD_A = 'replace-with-test-only-secret'
$env:GUTCARE_DEMO_PASSWORD_B = 'replace-with-test-only-secret'
python scripts/demo_data.py initialize <demo-bundle.json> --demo-mode --target-env demo --registration-notice <synced-registration-notices.json>
```

账号别名固定由配置生成：`<prefix>+cohort_a@<domain>` 与 `<prefix>+cohort_b@<domain>`。两种 cohort 都必须出现在已验证 bundle。工具先调用 readiness，再对 OpenAPI 版本、初始化依赖路径与方法、注册/验证/登录/记录请求体 DTO、记录 payload DTO 和必需 `Idempotency-Key` 头做预检；任何契约缺项在首次登录/注册/写入前失败。之后先尝试邮箱密码登录；只有登录返回 401 时才走注册→邮箱验证→登录。这样重复执行时已有有效身份不会重复注册，也不会要求二次验证；账号密码必须与已有 demo 账号相符。登录后读取本人资料/授权，再通过 `POST /api/v1/{diet-records|stool-records|symptom-records}` 创建记录。记录写入使用 bundle UUID 构造稳定 `Idempotency-Key`，重复执行同一 bundle 不重复创建记录。

记录 POST 仅接受 HTTP 201：后端路由固定 `status_code=201`，OpenAPI 的 create record 成功响应也是 201；幂等重放返回原记录 DTO，但仍走同一 POST 路由，因此状态码仍为 201。其他状态码（包括 200）均 fail-closed。

默认必须使用 HTTPS。仅对明确的 local/test loopback API，可同时指定 `--allow-local-http --test-opt-in` 例外。邮箱验证默认由操作者在终端 getpass 粘贴 token。仅当显式提供 `--mailpit-url http://127.0.0.1:8025` 并同时指定 `--test-opt-in` 时，工具才会经 Mailpit API 在内存检索匹配收件人的测试验证邮件；Mailpit URL 必须为 loopback HTTP，不打印或保存邮件正文/token。

```powershell
python scripts/demo_data.py initialize <demo-bundle.json> --demo-mode --target-env test --test-opt-in --allow-local-http --registration-notice <synced-registration-notices.json> --mailpit-url http://127.0.0.1:8025
```

告知版本由调用方提供的同步制品读取，服务端拒绝版本不一致；当前业务 API 没有注册前公开告知读取接口，因此本工具不能独立证明制品与远端当前法律告知逐字同源，部署方必须负责同步。此初始化器是竞赛演示辅助工具，不是生产注册入口，不得用于真实患者、真实数据或 production。工具不访问数据库或 Agent 服务，不把凭据/Token 写入文件。
