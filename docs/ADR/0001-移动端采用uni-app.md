# ADR-0001：移动端采用 uni-app

- 状态：Superseded（由 ADR-0022 取代）
- 日期：2026-10-14

## 决策

历史决策：患者端采用 uni-app + Vue 3 + TypeScript 构建 Android/iOS APP，不交付患者 H5/Web。该决策已由 ADR-0022 取代；`app/` 保留为只读归档，当前唯一活跃客户端为 `android/` 原生工程。Node.js 22 LTS 等仅为旧客户端历史构建基线，不约束 Android 原生工程。

## 理由与后果

延续 Vue 技术栈并以单代码库适配双端，适合 UI 后到、并行开发的周期。相机、文件、通知、安全存储必须双端真机验证；Refresh Token 使用项目自有 UTS Keychain/Keystore 插件，禁止普通 Storage 降级。

依据：<https://uniapp.dcloud.net.cn/tutorial/typescript-subject.html>、<https://uniapp.dcloud.net.cn/tutorial/app-sec-api.html>、<https://nodejs.org/en/about/previous-releases>
