<template>
  <div class="page designer-page">
    <div class="page-header">
      <h3 class="page-title">模板设计</h3>
      <div class="toolbar">
        <span class="muted">当前模板：</span>
        <el-select v-model="currentTemplateId" placeholder="选择模板" style="width: 220px" @change="onSelectTemplate">
          <el-option
            v-for="t in templates"
            :key="t.id"
            :label="t.name"
            :value="t.id"
          />
        </el-select>
        <el-button @click="newTemplate">新建模板</el-button>
        <el-button type="danger" plain :disabled="!currentTemplateId" @click="deleteTemplate">删除模板</el-button>
        <el-button type="primary" :loading="saving" @click="saveTemplate">保存模板</el-button>
      </div>
    </div>

    <div class="designer-body">
      <!-- 左侧：阶段类型库 -->
      <aside class="stage-library panel">
        <h4 class="panel-title">阶段类型库</h4>
        <div
          v-for="item in library"
          :key="item.type"
          class="library-item"
          draggable="true"
          @dragstart="onDragStart(item)"
        >
          <div class="library-info">
            <div class="library-name">{{ item.name }}</div>
            <div class="library-desc">{{ item.desc }}</div>
          </div>
          <el-tooltip content="增加卡片到画布" placement="left">
            <el-button size="small" circle type="primary" plain @click="addStage(item)">
              <el-icon><Plus /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </aside>

      <!-- 中间：画布 -->
      <section class="canvas-wrap panel">
        <h4 class="panel-title">
          流程画布
          <span class="muted canvas-count">{{ stages.length }} 个阶段</span>
        </h4>
        <el-empty v-if="!stages.length" description="从左侧阶段类型库点击「+」或拖拽卡片到此画布" :image-size="70" />

        <div
          v-for="(s, i) in stages"
          :key="s._uid"
          class="stage-row"
          draggable="true"
          @dragstart="dragIndex = i"
          @dragover.prevent="dragOverIndex = i"
          @drop.prevent="onDrop(i)"
          @dragend="dragIndex = null; dragOverIndex = null"
          :class="{ 'drag-over': dragOverIndex === i }"
        >
          <div class="stage-row-head">
            <span class="stage-idx">{{ i + 1 }}</span>
            <span class="stage-type-pill pill" :class="pillClass(s.type)">{{ typeName(s.type) }}</span>
            <span class="stage-name">{{ s.name }}</span>
            <div class="stage-ops">
              <el-tooltip content="启用/禁用（禁用=跳过）" placement="top">
                <el-switch v-model="s.enabled" size="small" />
              </el-tooltip>
              <el-button size="small" text circle :disabled="i === 0" @click="moveUp(i)">
                <el-icon><Top /></el-icon>
              </el-button>
              <el-button size="small" text circle :disabled="i === stages.length - 1" @click="moveDown(i)">
                <el-icon><Bottom /></el-icon>
              </el-button>
              <el-button size="small" text circle @click="copyStage(i)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
              <el-button size="small" text circle type="danger" @click="removeStage(i)">
                <el-icon><Delete /></el-icon>
              </el-button>
              <el-button size="small" text circle @click="toggleExpand(s)">
                <el-icon><ArrowDown /></el-icon>
              </el-button>
            </div>
          </div>

          <div v-if="s._expanded" class="stage-row-body">
            <el-form label-width="90px" size="small">
              <el-form-item label="阶段名称">
                <el-input v-model="s.name" />
              </el-form-item>
              <el-form-item v-if="s.type === 'skill'" label="绑定 Skill">
                <el-select v-model="s.skill_id" style="width: 100%" placeholder="选择要运行的 AI 能力" clearable>
                  <el-option
                    v-for="sk in skills"
                    :key="sk.id"
                    :label="`${sk.name}（${sk.id}）${sk.desc ? ' — ' + sk.desc : ''}`"
                    :value="sk.id"
                  />
                </el-select>
                <div class="form-hint">AI 处理步骤将默认运行该 Skill；实例中也可临时更换。</div>
              </el-form-item>
              <el-form-item label="数据来源">
                <el-select v-model="s.source" style="width: 100%">
                  <el-option label="无（手动操作）" value="" />
                  <el-option label="上传文件" value="upload" />
                  <el-option label="粘贴文本" value="paste" />
                  <el-option label="URL 抓取" value="url_fetch" />
                  <el-option label="MCP Server" value="mcp" />
                  <el-option label="连接器" value="connector" />
                </el-select>
              </el-form-item>
              <el-form-item label="来源配置">
                <el-input
                  v-model="s._sourceConfigText"
                  type="textarea"
                  :rows="3"
                  class="mono-input"
                  placeholder='JSON，如 {"url":"..."}'
                />
              </el-form-item>
              <el-form-item label="AI 配置">
                <el-input
                  v-model="s._aiConfigText"
                  type="textarea"
                  :rows="2"
                  class="mono-input"
                  placeholder="JSON，可留空"
                />
              </el-form-item>
            </el-form>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Top, Bottom, CopyDocument, Delete, ArrowDown } from '@element-plus/icons-vue'
import { aiApi, workflowApi } from '@/api'

const route = useRoute()
const projectId = route.params.id

const library = ref([])
const templates = ref([])
const skills = ref([])
const currentTemplateId = ref(null)
const stages = ref([])
const saving = ref(false)
const dragIndex = ref(null)
const dragOverIndex = ref(null)

let uidSeed = 0
function nextUid() {
  uidSeed += 1
  return `st-${Date.now()}-${uidSeed}`
}

const TYPE_NAMES = {
  requirement: '需求上传',
  api_doc: '接口文档',
  case_gen: '生成用例',
  skill: 'AI 处理',
  mcp: '平台取数',
  case_review: '用例评审',
  auto_gen: '自动化生成',
  execute: '执行报告'
}

function typeName(t) {
  return TYPE_NAMES[t] || t
}

function pillClass(t) {
  return ['requirement', 'case_gen', 'skill', 'auto_gen'].includes(t) ? 'pill-primary' : 'pill'
}

function normalizeStage(s) {
  return {
    type: s.type || 'custom',
    name: s.name || TYPE_NAMES[s.type] || '未命名阶段',
    enabled: s.enabled !== false,
    source: s.source || '',
    source_config: s.source_config || {},
    ai_config: s.ai_config || {},
    skill_id: s.skill_id || '',
    _uid: nextUid(),
    _expanded: false,
    _sourceConfigText: JSON.stringify(s.source_config || {}, null, 2),
    _aiConfigText: JSON.stringify(s.ai_config || {}, null, 2)
  }
}

async function loadLibrary() {
  library.value = await workflowApi.stageLibrary()
}

async function loadTemplates(select = true) {
  templates.value = await workflowApi.templates(projectId)
  if (select) {
    currentTemplateId.value = templates.value[0]?.id ?? null
    if (currentTemplateId.value) applyTemplate(templates.value[0])
    else stages.value = []
  }
}

function applyTemplate(t) {
  stages.value = (t.stages || []).map(normalizeStage)
}

function onSelectTemplate(id) {
  const t = templates.value.find((x) => x.id === id)
  if (t) applyTemplate(t)
}

function addStage(item) {
  stages.value.push(normalizeStage({ type: item.type, name: item.name }))
}

function onDragStart(item) {
  dragIndex.value = null
  // 拖拽库项到画布：临时放到末尾
  stages.value.push(normalizeStage({ type: item.type, name: item.name }))
  dragIndex.value = stages.value.length - 1
}

function onDrop(i) {
  const from = dragIndex.value
  if (from == null || from === i) return
  const [moved] = stages.value.splice(from, 1)
  stages.value.splice(i, 0, moved)
  dragIndex.value = null
  dragOverIndex.value = null
}

function moveUp(i) {
  if (i <= 0) return
  const arr = stages.value
  ;[arr[i - 1], arr[i]] = [arr[i], arr[i - 1]]
}

function moveDown(i) {
  if (i >= stages.value.length - 1) return
  const arr = stages.value
  ;[arr[i + 1], arr[i]] = [arr[i], arr[i + 1]]
}

function copyStage(i) {
  const s = stages.value[i]
  const clone = normalizeStage({ ...s })
  stages.value.splice(i + 1, 0, clone)
}

function removeStage(i) {
  stages.value.splice(i, 1)
}

function toggleExpand(s) {
  s._expanded = !s._expanded
}

function parseStages() {
  return stages.value.map((s) => {
    let sourceConfig = s.source_config || {}
    let aiConfig = s.ai_config || {}
    try {
      sourceConfig = s._sourceConfigText ? JSON.parse(s._sourceConfigText) : {}
    } catch {
      throw new Error(`阶段「${s.name}」的来源配置不是合法 JSON`)
    }
    try {
      aiConfig = s._aiConfigText ? JSON.parse(s._aiConfigText) : {}
    } catch {
      throw new Error(`阶段「${s.name}」的 AI 配置不是合法 JSON`)
    }
    return {
      type: s.type,
      name: s.name,
      enabled: s.enabled,
      source: s.source || '',
      source_config: sourceConfig,
      ai_config: aiConfig,
      skill_id: s.skill_id || ''
    }
  })
}

async function saveTemplate() {
  if (!stages.value.length) return ElMessage.warning('画布为空，请先添加阶段')
  let payloadStages
  try {
    payloadStages = parseStages()
  } catch (e) {
    return ElMessage.error(e.message)
  }
  const templateName = currentTemplateId.value
    ? templates.value.find((t) => t.id === currentTemplateId.value)?.name || '流程模板'
    : '流程模板'
  saving.value = true
  try {
    const body = { project_id: projectId, name: templateName, stages: payloadStages }
    if (currentTemplateId.value) {
      await workflowApi.updateTemplate(currentTemplateId.value, body)
      ElMessage.success('模板已更新')
    } else {
      const t = await workflowApi.createTemplate(body)
      currentTemplateId.value = t.id
      ElMessage.success('模板已保存')
    }
    await loadTemplates(false)
  } finally {
    saving.value = false
  }
}

function newTemplate() {
  stages.value = []
  currentTemplateId.value = null
}

async function deleteTemplate() {
  try {
    await ElMessageBox.confirm('确定删除当前模板？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  await workflowApi.deleteTemplate(currentTemplateId.value)
  ElMessage.success('模板已删除')
  currentTemplateId.value = null
  stages.value = []
  await loadTemplates(false)
}

onMounted(async () => {
  await loadLibrary()
  await loadTemplates(true)
  try {
    skills.value = await aiApi.skills()
  } catch {
    skills.value = []
  }
})
</script>

<style scoped>
.designer-body {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 16px;
  align-items: start;
}

.stage-library {
  position: sticky;
  top: 0;
}

.library-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  padding: 10px;
  margin-bottom: 8px;
  cursor: grab;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.library-item:hover {
  border-color: rgba(75, 63, 227, 0.4);
  background: var(--primary-light);
}

.library-info {
  flex: 1;
  min-width: 0;
}

.library-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.library-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-top: 2px;
}

.canvas-count {
  font-size: 12px;
  font-weight: 400;
  margin-left: 8px;
}

.stage-row {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  margin-bottom: 10px;
  background: var(--card);
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.stage-row.drag-over {
  border-color: var(--primary);
  box-shadow: 0 4px 14px rgba(75, 63, 227, 0.15);
}

.stage-row-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
}

.stage-idx {
  width: 22px;
  height: 22px;
  border-radius: 8px;
  background: var(--secondary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stage-type-pill {
  flex-shrink: 0;
}

.stage-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-ops {
  display: flex;
  align-items: center;
  gap: 2px;
}

.stage-row-body {
  border-top: 1px solid var(--border);
  padding: 12px 14px;
  background: var(--secondary);
}

.mono-input :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
}
</style>
