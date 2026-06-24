<!-- CrossProjectWarning.vue: 跨项目引用警告弹窗 -->
<template>
  <el-dialog
    :model-value="!!warningProjectName"
    title="跨项目引用"
    width="480px"
    :close-on-click-modal="false"
    @update:model-value="() => { /* block close by click */ }"
  >
    <el-alert type="warning" :closable="false" show-icon>
      <template #title>
        当前会话绑定项目「{{ session.currentProjectName }}」，仅对该项目有完整读写权限。
      </template>
      <template #default>
        <p>
          对「<strong>{{ warningProjectName }}</strong>」仅有<span class="readonly-label">只读</span>权限。
        </p>
        <p style="margin-top: 8px;">
          是否切换到「{{ warningProjectName }}」的会话？（当前会话自动保存）
        </p>
      </template>
    </el-alert>

    <template #footer>
      <el-button @click="handleDismiss">取消</el-button>
      <el-button type="primary" @click="handleSwitch">
        切换会话
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'

const session = useSessionStore()
const chat = useChatStore()

const warningProjectName = computed(() => chat.crossProjectWarning)

async function handleSwitch() {
  const targetProject = warningProjectName.value
  if (!targetProject) return

  const existing = session.sessions.find(s => s.project_name === targetProject)
  if (existing) {
    await session.switchToSession(existing.session_id)
  } else {
    try {
      await session.createSession(targetProject)
    } catch {
      // 静默
    }
  }
  chat.dismissWarning()
}

function handleDismiss() {
  chat.dismissWarning()
}
</script>

<style scoped>
.readonly-label {
  color: #ff9800;
  font-weight: 600;
}
p { margin: 0; color: #c0c0c0; font-size: 13px; }
</style>
