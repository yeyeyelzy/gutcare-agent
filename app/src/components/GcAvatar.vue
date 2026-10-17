<script setup lang="ts">
withDefaults(defineProps<{
  src?: string
  size?: 'header' | 'profile'
}>(), {
  src: '',
  size: 'header',
})
</script>

<template>
  <view class="gc-avatar" :class="`gc-avatar--${size}`">
    <image v-if="src" class="gc-avatar__image" :src="src" mode="aspectFill" />
  </view>
</template>

<style scoped>
.gc-avatar {
  position: relative;
  flex: none;
  aspect-ratio: 1 / 1;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: 50%;
  background: var(--gc-color-sage-pale);
}

.gc-avatar--header {
  width: 44px;
  height: 44px;
}

.gc-avatar--profile {
  width: 76px;
  height: 76px;
}

.gc-avatar--profile::after {
  position: absolute;
  inset: 0;
  border: 5px solid #fff;
  border-radius: 50%;
  content: '';
  pointer-events: none;
}

.gc-avatar__image {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-position: center;
}
</style>
