<template>
  <view v-if="canRender()" class="screen">
    <text>今日页面基础骨架</text>
  </view>
  <view v-else class="screen" aria-live="polite">
    <text>正在验证会话…</text>
  </view>
</template>

<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'
import { canRenderRoute } from '../../navigation/routes'

const auth = useAuthStore()
const canRender = () => canRenderRoute('today', auth.state)
</script>

