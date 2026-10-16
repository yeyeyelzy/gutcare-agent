<template>
  <view class="launch">
    <text class="title">GutCare</text>
    <text class="subtitle">移动端应用基础壳</text>
    <button class="primary" @click="continueToLogin">继续</button>
  </view>
</template>

<script setup lang="ts">
function continueToLogin() {
  uni.redirectTo({ url: '/pages/auth/login' })
}
</script>

<style lang="scss" scoped>
.launch { min-height: 100vh; padding: 24px; display: flex; flex-direction: column; }
.title { font-size: var(--gc-font-size-display); font-weight: var(--gc-font-weight-bold); }
.subtitle { margin-top: 8px; color: var(--gc-color-muted); }
.primary { margin-top: auto; }
</style>
