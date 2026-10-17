<script setup lang="ts">
import { inject } from 'vue'
import { onLaunch } from '@dcloudio/uni-app'
import { startupCoordinatorKey } from './api/context'

const startup = inject(startupCoordinatorKey)

onLaunch(() => {
  if (startup) void startup.start()
})
</script>
