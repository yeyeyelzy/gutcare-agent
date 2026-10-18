<template><MedicalArchiveWorkspace /></template>
<script setup lang="ts">
import { onShow } from '@dcloudio/uni-app'
import { inject } from 'vue'
import { appRouterKey } from '../../../api/context'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import MedicalArchiveWorkspace from '../../../components/MedicalArchiveWorkspace.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
onShow(() => { if (!canRenderRoute('medicalDocumentDetail', auth.state)) router?.requireAuthentication('medicalDocumentDetail') })
</script>
