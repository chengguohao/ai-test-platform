<template>
  <div class="page">
    <div class="page-header">
      <h3 class="page-title">AI 配置</h3>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建模型配置</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="mb12"
      title="配置多套大模型（供应商/模型/密钥）。新建项目时可选择绑定其中一套；未选择时使用全局 .env 默认配置。API Key 仅显示后 4 位，编辑时留空表示不修改。"
    />

    <el-table v-loading="loading" :data="models" border size="default" empty-text="暂无模型配置">
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="base_url" label="接口地址" min-width="220" show-overflow-tooltip />
      <el-table-column prop="model" label="模型" min-width="130" />
      <el-table-column label="温度" width="80">
        <template #default="{ row }">{{ row.temperature }}</template>
      </el-table-column>
      <el-table-column label="API Key" width="130">
        <template #default="{ row }">
          <span class="mono">{{ row.api_key_masked || '未设置' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
            {{ row.enabled ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :loading="testingId === row.id" @click="test(row)">测试</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="confirmDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建 / 编辑 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑模型配置' : '新建模型配置'" width="540px" destroy-on-close>
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：DeepSeek / 通义千问 / 本地 Ollama" />
          <div class="form-hint">名称可重复：同一名称下可配多个不同模型（如 DeepSeek 名下配 v4-flash、chat…），「名称 + 模型名」组合唯一。</div>
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="form.base_url" placeholder="https://api.deepseek.com/v1（OpenAI 兼容）" />
        </el-form-item>
        <el-form-item label="模型名">
          <el-input v-model="form.model" placeholder="deepseek-chat" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="form.id ? '留空表示不修改' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="温度">
          <el-slider v-model="form.temperature" :min="0" :max="1.5" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { aiModelApi } from '@/api'

const models = ref([])
const loading = ref(false)
const saving = ref(false)
const testingId = ref(null)
const dialogVisible = ref(false)

const defaultForm = { id: null, name: '', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', api_key: '', temperature: 0.2, enabled: true }
const form = reactive({ ...defaultForm })

async function load() {
  loading.value = true
  try {
    models.value = await aiModelApi.list()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, defaultForm, { id: null })
  dialogVisible.value = true
}

function openEdit(m) {
  Object.assign(form, {
    id: m.id, name: m.name, base_url: m.base_url, model: m.model,
    api_key: '', temperature: m.temperature, enabled: m.enabled
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写配置名称')
  saving.value = true
  try {
    const payload = { name: form.name.trim(), base_url: form.base_url.trim() || 'https://api.deepseek.com/v1', model: form.model.trim() || 'deepseek-chat', temperature: form.temperature, enabled: form.enabled, api_key: form.api_key.trim() }
    if (form.id) {
      await aiModelApi.update(form.id, payload)
      ElMessage.success('配置已更新')
    } else {
      await aiModelApi.create(payload)
      ElMessage.success('配置已创建')
    }
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function test(m) {
  testingId.value = m.id
  try {
    const r = await aiModelApi.test(m.id)
    if (r.ok) ElMessage.success(r.message)
    else ElMessage.error(r.message)
  } finally {
    testingId.value = null
  }
}

async function confirmDelete(m) {
  try {
    await ElMessageBox.confirm(
      `确定删除模型配置「${m.name}」？绑定该配置的项目将自动回退全局默认模型。`,
      '删除配置',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await aiModelApi.remove(m.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.mb12 {
  margin-bottom: 12px;
}

.mono {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
}
</style>