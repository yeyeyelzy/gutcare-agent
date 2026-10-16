# ADR-0001：移动端采用 uni-app

- 状态：Accepted
- 日期：2026-10-14

## 决策

患者端采用 uni-app + Vue 3 + TypeScript 构建 Android/iOS APP，不交付患者 H5/Web。Node.js 22 LTS 为固定构建运行时，开发机与 CI 统一。

## 理由与后果

延续 Vue 技术栈并以单代码库适配双端，适合 UI 后到、并行开发的周期。相机、文件、通知、安全存储必须双端真机验证；Refresh Token 使用项目自有 UTS Keychain/Keystore 插件，禁止普通 Storage 降级。

依据：<https://uniapp.dcloud.net.cn/tutorial/typescript-subject.html>、<https://uniapp.dcloud.net.cn/tutorial/app-sec-api.html>、<https://nodejs.org/en/about/previous-releases>
