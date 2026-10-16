<template>
  <view class="screen">
    <text class="heading">欢迎回来</text>
    <text class="intro">使用邮箱和密码登录 GutCare</text>
    <label class="label" for="email">邮箱</label>
    <input id="email" v-model="email" class="input" type="text" autocomplete="email" placeholder="name@example.com" />
    <label class="label" for="password">密码</label>
    <input id="password" v-model="password" class="input" password placeholder="请输入密码" />
    <button class="primary" disabled>登录界面待 UI 交付</button>
    <text class="notice">该页面仅占位，认证流程通过统一会话服务接入。</text>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const email = ref('')
const password = ref('')
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; padding: 64px 24px 32px; display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.heading { font-size: 28px; font-weight: 700; }
.intro { margin: 8px 0 32px; color: var(--gc-color-muted); }
.label { margin: 18px 0 8px; font-weight: 600; }
.input { height: 52px; padding: 0 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); }
.primary { margin-top: 28px; border-radius: var(--gc-radius-md); background: var(--gc-color-brand); color: white; }
.primary[disabled] { opacity: .5; }
.notice { margin-top: 16px; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); text-align: center; }
</style>
