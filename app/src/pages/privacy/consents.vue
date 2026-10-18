<template>
  <view v-if="authorized" data-testid="privacy-consents-page"><PrivacyConsentSettings @back="goBack" /></view>
  <view v-else class="auth-pending" role="status">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { onBackPress, onShow } from '@dcloudio/uni-app'
import { appRouterKey } from '../../api/context'
import { canRenderRoute } from '../../navigation/routes'
import { returnFromConsents } from '../../navigation/settingsNavigation'
import { useAuthStore } from '../../stores/auth'
import PrivacyConsentSettings from '../../components/PrivacyConsentSettings.vue'

const router = inject(appRouterKey)
const auth = useAuthStore()
const authorized = computed(() => canRenderRoute('privacyConsents', auth.state))
onShow(() => { if (!authorized.value) router?.requireAuthentication('privacyConsents') })
function goBack() { returnFromConsents(router, getCurrentPages().length) }
onBackPress(() => { goBack(); return true })
</script>

<style scoped>.auth-pending{display:grid;min-height:100vh;place-items:center;color:var(--gc-color-muted)}</style>
