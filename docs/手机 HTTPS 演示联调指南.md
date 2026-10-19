# 实体手机 HTTPS 演示联调（仅 test/demo）

这条路径只用于比赛展示和合成数据联调：它单独构建 FastAPI、PostgreSQL、Redis 和 Mailpit，Compose 项目固定为 `gutcare-phone-demo`。它不修改根 `compose.yaml` 的事实：根 Compose 仍未纳入 API 镜像服务，也不是完整 B00 拓扑或生产部署。

严禁录入真实患者数据。生成的 `phone-demo.env` 含本机随机密钥和口令，已被 Git 忽略；不复制、不提交、不复用到任何其他环境。

## 前置条件

- Windows Docker Desktop 已启动，Docker Compose v2 可用。
- 已安装 `cloudflared`，且可在独立 PowerShell 终端运行。
- APP 通过 HBuilder 启动；不要把实体手机的 API 地址设为 `localhost`。

该演示只包括认证所需的 API、数据库、Redis 与本机 Mailpit。F02 文件上传/下载、对象存储、病毒扫描、记录图片识别、F08 智能体任务及其他依赖独立 worker/agent 的功能不在此路径中，不能据此声称完整功能验收。

## 启动和检查

从仓库根目录执行：

```powershell
.\scripts\phone-demo-up.ps1
Invoke-WebRequest http://127.0.0.1:8000/health/live
```

首次运行时脚本才创建 `phone-demo.env`，其中全部口令、crypto key 和 pepper 都由系统随机数生成且彼此不同；脚本不会打印它们，也不读取根 `.env`。随后会先执行 Compose 配置校验，再构建 API；API 容器在启动 Uvicorn 前必须成功运行 `alembic upgrade head`。`-ConfigOnly` 只生成本机配置并执行 `docker compose config --quiet`，不拉取、构建或启动服务：

```powershell
.\scripts\phone-demo-up.ps1 -ConfigOnly
```

API 仅映射到 `127.0.0.1:8000`；PostgreSQL 和 Redis没有主机端口，Mailpit 仅映射本机 `127.0.0.1:8025`。数据库与 Redis 只连接 Compose 内部 `private` 网络；API 和 Mailpit 额外连接非内部 `edge` 网络，仅使上述 loopback 端口发布在 Windows 主机，仍不会暴露到局域网或公网。API 到 Mailpit 的 SMTP 仍经 `private` 网络。打开 [Mailpit](http://127.0.0.1:8025) 查看合成账号注册或重置邮件并在 APP 输入验证码。建议每次演示注册一个显然是演示用途的别名，例如 `demo-日期-序号@example.test`，自行设置演示密码；不要保存或共享该密码。

## Quick Tunnel 与 APP

在**另一个** PowerShell 终端运行：

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Cloudflare 会显示一个临时 HTTPS URL。它是公开、匿名的 URL；每次启动通常会变化，停止该 `cloudflared` 进程即失效。只使用合成演示数据，不要把这个 URL 发送给不受控的人员。不要使用 `--allowed-mail`：原生 APP API 调用没有交互式浏览器 cookie，不能完成该访问控制流程。

取得 URL 后，将 `app/.env` 的 API 基址改成：

```text
VITE_API_BASE_URL=$tunnelUrl/api/v1
```

其中 `$tunnelUrl` 是 Cloudflare 输出的完整 HTTPS URL（不要保留字面量 `$tunnelUrl`），然后重启 HBuilder。不能写 `localhost`、`127.0.0.1` 或宿主机局域网地址。

此 API 没有浏览器 CORS 需求：原生 Android/iOS 网络请求不受浏览器同源策略约束；认证仍由 API 校验。`APP_PUBLIC_BASE_URL` 在该路径固定为 loopback，因为 F02 capability URL 流程未启用；因此不必、也不应在每次 Quick Tunnel URL 改变后重建 API。若未来将 F02 加入演示，需要另行设计能安全反映临时 HTTPS origin 的对象能力 URL 与相应验证，不能沿用本指南假设。

## 停止和清理

先在 Quick Tunnel 终端按 `Ctrl+C`，再执行：

```powershell
.\scripts\phone-demo-down.ps1
```

默认仅停止此 Compose 项目的容器并保留它自己的演示卷。要删除**本项目**的演示 PostgreSQL、Redis 和 Mailpit 数据卷：

```powershell
.\scripts\phone-demo-down.ps1 -PurgeData
```

脚本先逐一验证容器/卷的 `com.docker.compose.project=gutcare-phone-demo` 标签，拒绝清理其他 Compose 项目资源。它不会删除 `phone-demo.env`；如需轮换全部本机演示密钥，应先停机并手工删除这个确切文件，再次运行启动脚本。

## 验收边界

`/health/live` 只说明 API 进程存活；可额外查看 `/health/ready` 以检查数据库、迁移 head 和隐私 replay 门禁。Docker daemon、镜像拉取/构建、Cloudflare 出站访问、实体 Android/iOS 与 HBuilder 都是本机外部条件，必须在目标机器实际运行后才可记为运行或真机证据。
