<template>
  <div class="page">
    <div class="page-header">
      <h3 class="page-title">项目列表</h3>
      <div class="header-actions">
        <el-button :icon="FolderAdd" @click="createFolderOnRoot">新建文件夹</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建项目</el-button>
      </div>
    </div>

    <div class="project-layout">
      <!-- 左侧目录树：根 → 文件夹（多级嵌套）→ 项目 -->
      <aside class="tree-panel">
        <div class="tree-title">目录</div>
        <el-tree
          ref="treeRef"
          :data="treeData"
          :props="treeProps"
          node-key="id"
          highlight-current
          :expand-on-click-node="false"
          :current-node-key="currentFolderId ?? 0"
          :default-expanded-keys="expandedKeys"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <el-icon class="tree-icon"><Folder /></el-icon>
              <span class="tree-label">{{ data.name }}</span>
              <span class="tree-ops" @click.stop>
                <el-icon v-if="data.id !== 0" title="新建子文件夹" @click="addSubFolder(data)"><FolderAdd /></el-icon>
                <el-icon v-if="data.id !== 0" title="重命名" @click="renameFolder(data)"><EditPen /></el-icon>
                <el-icon v-if="data.id !== 0" title="删除" @click="removeFolder(data)"><Delete /></el-icon>
                <el-icon v-else title="新建文件夹" @click="createFolderOnRoot"><FolderAdd /></el-icon>
              </span>
            </span>
          </template>
        </el-tree>
      </aside>

      <!-- 右侧项目卡片 -->
      <div v-loading="loading" class="grid-panel">
        <div class="grid-head">
          <span class="grid-title">{{ currentTitle }}</span>
          <span class="grid-count" v-if="projects.length">{{ projects.length }} 个项目</span>
        </div>
        <el-empty v-if="!loading && !projects.length" description="当前目录下暂无项目" />
        <div class="project-grid">
          <article
            v-for="p in projects"
            :key="p.id"
            class="project-card"
            @click="goBoard(p)"
          >
            <div class="project-head">
              <div class="project-avatar">{{ p.name.slice(0, 1).toUpperCase() }}</div>
              <div class="project-info">
                <div class="project-name">{{ p.name }}</div>
                <div class="project-date">{{ formatDate(p.created_at) }}</div>
              </div>
            </div>
            <p class="project-desc">{{ p.desc || '暂无描述' }}</p>
            <div class="project-actions">
              <el-button type="primary" size="small" @click.stop="goBoard(p)">打开工作台</el-button>
              <el-button size="small" :loading="copying === p.id" @click.stop="copyProject(p)">复制</el-button>
              <el-button size="small" @click.stop="openEdit(p)">编辑</el-button>
              <el-button size="small" @click.stop="goDesigner(p)">模板设计</el-button>
              <el-button size="small" type="danger" plain @click.stop="confirmDelete(p)">删除</el-button>
            </div>
          </article>
        </div>
      </div>
    </div>

    <!-- 新建 / 编辑项目对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑项目' : '新建项目'"
      width="620px"
      destroy-on-close
    >
      <el-form :model="form" label-width="120px">
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" placeholder="如 SmartAdmin-通知公告" />
        </el-form-item>
        <el-form-item label="所属文件夹">
          <el-select v-model="form.folder_id" style="width: 100%" clearable placeholder="不选=全部项目（未归类）">
            <el-option v-for="f in flatFolders" :key="f.id" :label="f.path" :value="f.id" />
          </el-select>
          <div class="form-hint">仅当前目录树中的文件夹；不选则项目显示在「全部项目」下。</div>
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input v-model="form.desc" type="textarea" :rows="2" placeholder="一句话描述被测系统" />
        </el-form-item>
        <el-divider content-position="left">被测系统与执行引擎</el-divider>
        <el-form-item label="被测系统地址">
          <el-input v-model="engine.base_url" placeholder="http://127.0.0.1:1024" />
        </el-form-item>
        <el-form-item label="登录账号">
          <el-input v-model="engine.login_name" placeholder="admin" />
        </el-form-item>
        <el-form-item label="登录密码">
          <el-input v-model="engine.password" type="password" show-password placeholder="被测系统登录密码" />
        </el-form-item>
        <el-form-item label="pytest 项目目录">
          <el-input v-model="engine.pytest_project_dir" placeholder="c:\...\pytest-bdd" />
        </el-form-item>
        <el-form-item label="python 解释器">
          <el-input v-model="engine.python" placeholder="c:\...\python.exe" />
        </el-form-item>
        <el-form-item label="allure 路径">
          <el-input v-model="engine.allure_bin" placeholder="c:\...\allure.bat" />
        </el-form-item>
        <el-form-item label="用例生成目录">
          <el-input v-model="engine.gen_dir" placeholder="留空默认 tests/api；指定到 tests/api/smartadmin 可复用其 conftest" />
        </el-form-item>
        <el-divider content-position="left">AI 模型（未选则用全局默认）</el-divider>
        <el-form-item label="AI 模型">
          <el-select v-model="form.ai_model_id" style="width: 100%" placeholder="选择模型配置">
            <el-option label="默认（全局 .env 配置）" :value="0" />
            <el-option
              v-for="m in enabledModels"
              :key="m.id"
              :label="`${m.name}（${m.model}）`"
              :value="m.id"
            />
          </el-select>
          <div class="form-hint">可在左侧「AI 配置」页管理多套模型；不选择时使用全局默认。</div>
        </el-form-item>
        <el-form-item label="副模型">
          <el-select v-model="form.vision_model_id" style="width: 100%" placeholder="多模态视觉模型">
            <el-option label="未勾选（回退主模型/全局）" :value="0" />
            <el-option
              v-for="m in enabledModels"
              :key="m.id"
              :label="`${m.name}（${m.model}）`"
              :value="m.id"
            />
          </el-select>
          <div class="form-hint">多模态视觉模型：需求文档含图片时，用它识别 docx 内嵌图并规范化；未勾选则回退主模型或全局默认。</div>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Folder, FolderAdd, EditPen, Delete
} from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { aiModelApi, projectApi, folderApi } from '@/api'

const router = useRouter()
const store = useAppStore()

const projects = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)

/* ---------------- 目录树 ---------------- */
const folders = ref([])           // 后端文件夹树（根级数组）
const currentFolderId = ref(null) // null=全部项目；>0=文件夹 id
const treeRef = ref(null)
const expandedKeys = ref([])
const treeProps = { label: 'name', children: 'children' }
/** 包一层虚拟根节点「全部项目」给 el-tree */
const treeData = computed(() => [{ id: 0, name: '全部项目', children: folders.value }])
const currentTitle = computed(() => {
  if (!currentFolderId.value) return '全部项目'
  const f = flatFolders.value.find((x) => x.id === currentFolderId.value)
  return f ? f.path : '全部项目'
})
/** 拍平文件夹树（含路径展示），供新建/编辑项目下拉选择 */
const flatFolders = computed(() => {
  const out = []
  const walk = (nodes, prefix) => {
    for (const n of nodes) {
      const path = prefix ? `${prefix} / ${n.name}` : n.name
      out.push({ id: n.id, name: n.name, path })
      if (n.children && n.children.length) walk(n.children, path)
    }
  }
  walk(folders.value, '')
  return out
})

async function loadFolders() {
  try {
    folders.value = await folderApi.tree()
  } catch {
    folders.value = []
  }
}

function onNodeClick(data) {
  currentFolderId.value = data.id === 0 ? null : data.id
  load()
}

/* ---------------- 文件夹操作 ---------------- */
async function createFolderOnRoot() {
  const { value } = await ElMessageBox.prompt('请输入文件夹名称', '新建文件夹', {
    confirmButtonText: '创建', cancelButtonText: '取消',
    inputPattern: /\S+/, inputErrorMessage: '名称不能为空'
  })
  await folderApi.create({ name: value.trim(), parent_id: null })
  ElMessage.success('文件夹已创建')
  await afterFolderChanged(null)
}

async function addSubFolder(data) {
  const { value } = await ElMessageBox.prompt(`在「${data.name}」下新建文件夹`, '新建子文件夹', {
    confirmButtonText: '创建', cancelButtonText: '取消',
    inputPattern: /\S+/, inputErrorMessage: '名称不能为空'
  })
  await folderApi.create({ name: value.trim(), parent_id: data.id })
  ElMessage.success('子文件夹已创建')
  await afterFolderChanged(data.id)
}

async function renameFolder(data) {
  const { value } = await ElMessageBox.prompt('请输入新的文件夹名称', '重命名文件夹', {
    confirmButtonText: '保存', cancelButtonText: '取消',
    inputValue: data.name, inputPattern: /\S+/, inputErrorMessage: '名称不能为空'
  })
  await folderApi.update(data.id, { name: value.trim() })
  ElMessage.success('已重命名')
  await afterFolderChanged(null)
}

async function removeFolder(data) {
  try {
    await ElMessageBox.confirm(
      `确定删除文件夹「${data.name}」？将连同其下全部子文件夹一并删除，文件夹内项目会移到「全部项目」（项目本身不删除）。`,
      '删除文件夹',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await folderApi.remove(data.id)
  ElMessage.success('文件夹已删除')
  if (currentFolderId.value === data.id) currentFolderId.value = null
  await afterFolderChanged(null)
}

/** 文件夹增删改后：刷新树 + 刷新项目列表 */
async function afterFolderChanged(expandId) {
  await loadFolders()
  if (expandId != null) {
    expandedKeys.value = [...new Set([...expandedKeys.value, expandId])]
  }
  await load()
}

/* ---------------- 项目 ---------------- */
async function load() {
  loading.value = true
  try {
    const all = await store.reloadProjects() // 全量刷新 store，前端按文件夹过滤
    const fid = currentFolderId.value
    projects.value = fid == null ? all : all.filter((p) => (p.folder_id || 0) === fid)
  } finally {
    loading.value = false
  }
}

async function loadAiModels() {
  try {
    aiModels.value = await aiModelApi.list()
  } catch {
    aiModels.value = []
  }
}

const defaultEngine = {
  base_url: '',
  login_name: '',
  password: '',
  pytest_project_dir: '',
  python: '',
  allure_bin: '',
  gen_dir: ''
}

const form = reactive({ id: null, name: '', desc: '', folder_id: null, ai_model_id: 0, vision_model_id: 0 })
const engine = reactive({ ...defaultEngine })
const aiModels = ref([])
/** 启用的模型配置，供项目弹窗下拉选择 */
const enabledModels = computed(() => aiModels.value.filter((m) => m.enabled))

function openCreate() {
  Object.assign(form, {
    id: null, name: '', desc: '', folder_id: currentFolderId.value,
    ai_model_id: 0, vision_model_id: 0,
  })
  Object.assign(engine, defaultEngine)
  dialogVisible.value = true
}

function openEdit(p) {
  Object.assign(form, {
    id: p.id, name: p.name, desc: p.desc || '', folder_id: p.folder_id || null,
    ai_model_id: p.ai_model_id || 0, vision_model_id: p.vision_model_id || 0,
  })
  Object.assign(engine, defaultEngine, p.engine_config || {})
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写项目名称')
  saving.value = true
  try {
    const payload = {
      name: form.name, desc: form.desc, engine_config: { ...engine },
      folder_id: form.folder_id || null,
      ai_model_id: form.ai_model_id || 0, vision_model_id: form.vision_model_id || 0,
    }
    if (form.id) {
      await projectApi.update(form.id, payload)
      ElMessage.success('项目已更新')
    } else {
      await projectApi.create(payload)
      ElMessage.success('项目已创建')
    }
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const copying = ref(null)

async function copyProject(p) {
  if (copying.value) return
  try {
    await ElMessageBox.confirm(
      `确定复制项目「${p.name}」？将连同流程实例、工件、用例集一起复制为「${p.name}-副本」。`,
      '复制项目',
      { type: 'info', confirmButtonText: '复制', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  copying.value = p.id
  try {
    const np = await projectApi.copy(p.id)
    ElMessage.success(`已复制为「${np.name}」，工作流内容已一并复制`)
    await load()
  } finally {
    copying.value = null
  }
}

async function confirmDelete(p) {
  try {
    await ElMessageBox.confirm(
      `确定删除项目「${p.name}」？该项目的流程模板、全部流程实例、用例集、工件文件与执行记录将一并删除，不可恢复。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await projectApi.remove(p.id)
  ElMessage.success('项目已删除')
  await load()
}

function goBoard(p) {
  router.push(`/project/${p.id}`)
}

function goDesigner(p) {
  router.push(`/project/${p.id}/designer`)
}

function formatDate(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}

onMounted(async () => {
  await Promise.all([loadFolders(), loadAiModels()])
  await load()
})
</script>

<style scoped>
.project-layout {
  display: flex;
  gap: 0;
  align-items: flex-start;
}

/* ---- 左侧目录树 ---- */
.tree-panel {
  width: 268px;
  flex-shrink: 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 12px;
  margin-right: 16px;
  position: sticky;
  top: 8px;
  max-height: calc(100vh - 140px);
  overflow: auto;
}

.tree-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 4px 8px 10px;
}

.tree-node {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 6px;
  padding-right: 4px;
}

.tree-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.tree-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.tree-ops {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.tree-node:hover .tree-ops {
  display: inline-flex;
}

.tree-ops .el-icon {
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  color: var(--text-secondary);
}

.tree-ops .el-icon:hover {
  background: rgba(75, 63, 227, 0.12);
  color: var(--accent);
}

/* ---- 右侧网格 ---- */
.grid-panel {
  flex: 1;
  min-width: 0;
}

.grid-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}

.grid-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.grid-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(540px, 1fr));
  gap: 16px;
  min-height: 200px;
}

.project-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px 18px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

@media (prefers-reduced-motion: no-preference) {
  .project-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 24px rgba(27, 29, 42, 0.08);
  }
}

.project-card:hover {
  border-color: rgba(75, 63, 227, 0.35);
}

.project-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-avatar {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4b3fe3, #7c73ea);
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.project-info {
  flex: 1;
  min-width: 0;
}

.project-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-date {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.project-desc {
  margin: 14px 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 5 个操作按钮一行展示（不换行），靠卡片宽度保证放得下 */
.project-actions {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.project-actions .el-button {
  flex-shrink: 0;
}

.form-hint {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 6px;
}
</style>
