<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost, apiPut, apiDelete } from '@/services/api'

interface SkillSummary {
  name: string
  description: string
  phase: string
  version: string
  triggers: string[]
}

interface SkillDetail {
  name: string
  description: string
  triggers: string[]
  phase: string
  tools: string[]
  agent_role: string
  body: string
  version: string
  is_chat_skill: boolean
  is_chainable: boolean
}

interface VersionEntry {
  version: string
  changed_at: string
  diff_summary: string
}

const skills = ref<SkillSummary[]>([])
const selected = ref<SkillDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const versions = ref<VersionEntry[]>([])
const showVersions = ref(false)

// 编辑表单
const editName = ref('')
const editDesc = ref('')
const editTriggers = ref('')
const editPhase = ref('chat')
const editTools = ref('')
const editAgentRole = ref('developer')
const editBody = ref('')
const editIsChainable = ref(false)
const isNew = ref(false)

async function loadSkills() {
  loading.value = true
  try {
    const res = await apiGet<{ skills: SkillSummary[] }>('/api/v1/skills')
    skills.value = res.skills || []
  } catch { /* 后端未就绪——静默降级 */ }
  finally { loading.value = false }
}

async function selectSkill(name: string) {
  isNew.value = false
  try {
    const res = await apiGet<SkillDetail>(`/api/v1/skills/${name}`)
    const d = (res as any).data || res
    selected.value = d
    editName.value = d.name
    editDesc.value = d.description
    editTriggers.value = (d.triggers || []).join(', ')
    editPhase.value = d.phase
    editTools.value = (d.tools || []).join(', ')
    editAgentRole.value = d.agent_role
    editBody.value = d.body
    editIsChainable.value = d.is_chainable
  } catch { /* 静默 */ }
}

function newSkill() {
  isNew.value = true
  selected.value = null
  editName.value = ''
  editDesc.value = ''
  editTriggers.value = ''
  editPhase.value = 'chat'
  editTools.value = ''
  editAgentRole.value = 'developer'
  editBody.value = ''
  editIsChainable.value = false
}

async function saveSkill() {
  saving.value = true
  try {
    const payload = {
      name: editName.value,
      description: editDesc.value,
      triggers: editTriggers.value.split(',').map(t => t.trim()).filter(Boolean),
      phase: editPhase.value,
      tools: editTools.value.split(',').map(t => t.trim()).filter(Boolean),
      agent_role: editAgentRole.value,
      body: editBody.value,
      is_chainable: editIsChainable.value,
    }
    if (isNew.value) {
      await apiPost('/api/v1/skills', payload)
    } else {
      await apiPut(`/api/v1/skills/${editName.value}`, { ...payload, version_bump: 'patch', change_summary: 'GUI 编辑保存' })
    }
    await loadSkills()
    await selectSkill(editName.value)
  } catch { /* 静默 */ }
  finally { saving.value = false }
}

async function deleteSkill(name: string) {
  if (!confirm(`确认删除 Skill "${name}"？此操作不可逆。`)) return
  try {
    await apiDelete(`/api/v1/skills/${name}`)
    selected.value = null
    await loadSkills()
  } catch { /* 静默 */ }
}

async function loadVersions(name: string) {
  try {
    const res = await apiGet<{ versions: VersionEntry[] }>(`/api/v1/skills/${name}/versions`)
    versions.value = (res as any).data?.versions || []
    showVersions.value = true
  } catch { /* 静默 */ }
}

async function rollbackSkill(name: string, version: string) {
  if (!confirm(`回滚 "${name}" 到版本 ${version}？当前版本将被保存为历史。`)) return
  try {
    await apiPost(`/api/v1/skills/${name}/rollback`, { version })
    await loadSkills()
    await selectSkill(name)
    showVersions.value = false
  } catch { /* 静默 */ }
}

const phaseLabel: Record<string, string> = {
  plan: '📋 方案', implement: '🔧 实现', review: '🔍 审查',
  verify: '✅ 验证', merge: '🔀 合并', chat: '💬 对话',
}

onMounted(() => loadSkills())
</script>

<template>
<div class="skill-manager" style="display:flex;height:100vh;background:var(--color-orbit-bg);color:var(--color-orbit-text);font-family:var(--font-mono)">
  <!-- 左侧 Skill 列表 -->
  <div class="skill-list" style="width:280px;border-right:1px solid var(--color-orbit-border);overflow-y:auto;padding:12px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h2 style="font-size:14px;margin:0">Skills</h2>
      <button class="btn-sm" @click="newSkill">+ New</button>
    </div>
    <div v-if="loading" style="color:var(--color-orbit-text-secondary);font-size:12px">Loading...</div>
    <div v-for="s in skills" :key="s.name" class="skill-item"
         :class="{ active: selected?.name === s.name }"
         @click="selectSkill(s.name)"
         style="padding:8px;cursor:pointer;border-radius:4px;margin-bottom:4px;font-size:12px">
      <div style="font-weight:600">{{ s.name }}</div>
      <div style="color:var(--color-orbit-text-secondary);font-size:10px">
        {{ phaseLabel[s.phase] || s.phase }} · v{{ s.version }}
      </div>
      <div style="color:var(--color-orbit-text-muted);font-size:10px">{{ s.description }}</div>
    </div>
    <div v-if="skills.length === 0 && !loading" style="color:var(--color-orbit-text-secondary);font-size:12px;padding:12px">
      暂无 Skill。点击 "+ New" 创建。
    </div>
  </div>

  <!-- 右侧编辑器 -->
  <div class="skill-editor" style="flex:1;overflow-y:auto;padding:16px">
    <div v-if="selected || isNew" style="max-width:800px">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <h2 style="font-size:16px;margin:0">{{ isNew ? '新建 Skill' : selected?.name }}</h2>
        <span v-if="selected" style="font-size:11px;color:var(--color-orbit-text-secondary)">v{{ selected.version }}</span>
        <button v-if="selected" class="btn-sm" @click="loadVersions(selected.name)">版本历史</button>
        <button v-if="selected" class="btn-sm btn-danger" @click="deleteSkill(selected.name)">删除</button>
      </div>

      <!-- 表单 -->
      <div class="form-group">
        <label>Name</label>
        <input v-model="editName" :disabled="!isNew" style="width:100%" />
      </div>
      <div class="form-group">
        <label>Description</label>
        <input v-model="editDesc" style="width:100%" />
      </div>
      <div class="form-group">
        <label>Triggers（逗号分隔）</label>
        <input v-model="editTriggers" style="width:100%" placeholder="审查, review, 检查代码" />
      </div>
      <div style="display:flex;gap:12px">
        <div class="form-group" style="flex:1">
          <label>Phase</label>
          <select v-model="editPhase" style="width:100%">
            <option v-for="(label, key) in phaseLabel" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div class="form-group" style="flex:1">
          <label>Agent Role</label>
          <select v-model="editAgentRole" style="width:100%">
            <option value="developer">Developer</option>
            <option value="architect">Architect</option>
            <option value="reviewer">Reviewer</option>
            <option value="clarifier">Clarifier</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Tools（逗号分隔）</label>
        <input v-model="editTools" style="width:100%" placeholder="read_file, grep, glob" />
      </div>
      <div class="form-group">
        <label style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" v-model="editIsChainable" />
          is_chainable（可作编排链一环）
        </label>
      </div>
      <div class="form-group">
        <label>Body（Markdown——Skill 指令）</label>
        <textarea v-model="editBody" rows="16" style="width:100%;font-family:var(--font-mono);font-size:12px"
                  placeholder="# Skill 指令&#10;&#10;## 流程&#10;1. ..." />
      </div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn-primary" :disabled="saving" @click="saveSkill">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>

      <!-- 版本历史弹窗 -->
      <div v-if="showVersions" class="version-modal" style="margin-top:16px;padding:12px;background:var(--color-orbit-surface);border-radius:4px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <strong style="font-size:13px">版本历史</strong>
          <button class="btn-sm" @click="showVersions=false">✕</button>
        </div>
        <div v-for="v in versions" :key="v.version" style="padding:6px 0;border-bottom:1px solid var(--color-orbit-border);font-size:11px">
          <span style="font-weight:600">v{{ v.version }}</span>
          <span style="color:var(--color-orbit-text-secondary);margin-left:8px">{{ v.diff_summary }}</span>
          <span style="color:var(--color-orbit-text-muted);margin-left:8px">{{ v.changed_at?.slice(0, 16) }}</span>
          <button class="btn-sm" style="margin-left:auto" @click="rollbackSkill(editName, v.version)">回滚到此版本</button>
        </div>
        <div v-if="versions.length === 0" style="font-size:11px;color:var(--color-orbit-text-secondary)">暂无版本历史</div>
      </div>
    </div>

    <!-- 无选中状态的占位符 -->
    <div v-else style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-orbit-text-secondary);font-size:13px">
      选择左侧 Skill 或 "+ New" 创建新 Skill
    </div>
  </div>
</div>
</template>

<style scoped>
.skill-item:hover { background: var(--color-orbit-surface-hover) }
.skill-item.active { background: var(--color-orbit-surface-hover); border-left: 3px solid var(--color-orbit-accent) }
.form-group { margin-bottom: 12px }
.form-group label { display: block; font-size: 11px; color: var(--color-orbit-text-secondary); margin-bottom: 4px; text-transform: uppercase }
input, select, textarea {
  background: var(--color-orbit-surface); border: 1px solid var(--color-orbit-border);
  color: var(--color-orbit-text); padding: 6px 8px; border-radius: 4px; font-size: 13px;
}
input:focus, select:focus, textarea:focus { outline: none; border-color: var(--color-orbit-accent) }
input:disabled { opacity: 0.5; cursor: not-allowed }
.btn-sm { padding: 2px 8px; border: 1px solid var(--color-orbit-border); border-radius: 4px;
  background: var(--color-orbit-glass); color: var(--color-orbit-text); cursor: pointer; font-size: 11px; font-family: var(--font-mono) }
.btn-sm:hover { background: var(--color-orbit-surface-hover) }
.btn-primary { padding: 6px 16px; border: none; border-radius: 4px; background: var(--color-orbit-accent);
  color: #fff; cursor: pointer; font-size: 12px; font-family: var(--font-mono) }
.btn-primary:disabled { opacity: 0.5 }
.btn-danger { border-color: var(--color-orbit-error); color: var(--color-orbit-error) }
</style>
