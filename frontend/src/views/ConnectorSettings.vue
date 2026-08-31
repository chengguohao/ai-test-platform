<template>
  <div class="page">
    <div class="page-header">
      <h3 class="page-title">连接器设置</h3>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建连接器</el-button>
    </div>

    <el-alert type="info" :closable="false" class="mb12" title="连接器是「取数/通知」能力，供流程步骤使用。常见场景：">
      <ul class="connector-tips">
        <li><b>paste（粘贴文本）</b>：直接把需求/知识库文字粘进来存为工件，最常用的免文件方式。</li>
        <li><b>url_fetch（URL 拉取）</b>：抓取网页内容，如 Swagger/OpenAPI 在线接口文档、需求页面。</li>
        <li><b>http（通用 HTTP）</b>：调自研平台的 REST 接口拉数据，可配请求头/JSON 路径解析。</li>
        <li><b>mcp（MCP Server）</b>：对接外部公司平台（如企业 OA/CRM），列出该平台暴露的 tools 后拉真实数据存为工件。</li>
        <li><b>smtp（邮件通知）</b>：评审结果等通过 SMTP 发邮件给相关人员（push 场景）。</li>
        <li><b>local（本地文件）</b>：读取服务端本地已有文件内容。</li>
      </ul>
      <div class="form-hint">需求接入 / 接口文档 / 平台取数等阶段里都能选用这些连接器拉数据；MCP 的具体 tool 用法以各平台文档为准。</div>
    </el-alert>

    <div class="panel">
      <h4 class="panel-title">连接器列表（全局）</h4>
      <el-table :data="connectors" v-loading="loading" border size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <span class="pill pill-primary">{{ row.kind }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="150">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              size="small"
              @change="(v) => toggleEnabled(row, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="240">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openTest(row)">测试连接</el-button>
            <el-button v-if="row.kind === 'mcp'" size="small" text @click="openMcpTools(row)">列出 tools</el-button>
            <el-button size="small" text @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新建 / 编辑连接器 -->
    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑连接器' : '新建连接器'"
      width="560px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="连接器类型" required>
          <el-select v-model="form.kind" style="width: 100%" :disabled="!!form.id" @change="onKindChange">
            <el-option v-for="k in kinds" :key="k.kind" :label="`${k.name}（${k.kind}）`" :value="k.kind" />
          </el-select>
          <div v-if="kindDesc" class="form-hint">{{ kindDesc }}</div>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="连接器名称" />
        </el-form-item>
        <template v-if="form.kind">
          <el-form-item v-for="f in kindFields" :key="f.key" :label="f.label">
            <el-input
              v-if="f.type === 'input'"
              v-model="form.cfg[f.key]"
              :type="f.type === 'password' ? 'password' : 'text'"
              :placeholder="f.placeholder || ''"
              show-password
            />
            <el-select v-else-if="f.type === 'select'" v-model="form.cfg[f.key]" style="width: 100%">
              <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
            </el-select>
            <el-input-number
              v-else-if="f.type === 'number'"
              v-model="form.cfg[f.key]"
              :min="0"
              style="width: 100%"
            />
            <el-input
              v-else
              v-model="form.cfg[f.key]"
              type="textarea"
              :rows="3"
              class="mono-input"
              :placeholder="f.placeholder || ''"
            />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 测试连接 -->
    <el-dialog v-model="testVisible" :title="`测试连接：${testConnector?.name || ''}`" width="560px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="参数（JSON）">
          <el-input v-model="testParams" type="textarea" :rows="4" class="mono-input" placeholder='{"url":"https://..."}' />
        </el-form-item>
        <el-form-item v-if="testConnector?.kind === 'mcp'" label="Tool 名称">
          <el-input v-model="testTool" placeholder="MCP tool 名称" />
        </el-form-item>
      </el-form>
      <div v-if="testResult" class="block-title">返回内容</div>
      <pre v-if="testResult" class="code-block">{{ testResult }}</pre>
      <template #footer>
        <el-button @click="testVisible = false">关闭</el-button>
        <el-button type="primary" :loading="testing" @click="doTest">拉取</el-button>
      </template>
    </el-dialog>

    <!-- MCP tools -->
    <el-dialog v-model="toolsVisible" :title="`MCP Tools：${toolsConnector?.name || ''}`" width="560px" destroy-on-close>
      <el-empty v-if="!mcpTools.length" description="未获取到 tools" :image-size="50" />
      <el-table v-else :data="mcpTools" size="small" border>
        <el-table-column prop="name" label="Tool 名称" width="180" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <el-button @click="toolsVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { connectorApi } from '@/api'

const connectors = ref([])
const kinds = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)

const form = reactive({
  id: null,
  kind: '',
  name: '',
  enabled: true,
  cfg: {}
})

const testVisible = ref(false)
const testing = ref(false)
const testConnector = ref(null)
const testParams = ref('{}')
const testTool = ref('')
const testResult = ref('')

const toolsVisible = ref(false)
const toolsConnector = ref(null)
const mcpTools = ref([])

/* 每种 kind 的配置表单字段定义 */
const KIND_FIELDS = {
  mcp: [
    { key: 'command', label: '启动命令', type: 'input', placeholder: '如 npx -y @modelcontextprotocol/server-filesystem' },
    { key: 'servers', label: 'Servers 列表', type: 'textarea', placeholder: 'JSON，可选，覆盖 command' }
  ],
  http: [
    { key: 'url', label: 'URL', type: 'input', placeholder: 'https://.../rest/api/2/issue/{key}' },
    { key: 'method', label: '请求方法', type: 'select', options: ['GET', 'POST', 'PUT', 'DELETE'] },
    { key: 'headers', label: 'Headers', type: 'textarea', placeholder: 'JSON，如 {"Authorization":"Bearer xxx"}' },
    { key: 'json_path', label: 'JSON 解析路径', type: 'input', placeholder: '如 fields.description' }
  ],
  smtp: [
    { key: 'host', label: 'SMTP 主机', type: 'input' },
    { key: 'port', label: '端口', type: 'number' },
    { key: 'user', label: '用户名', type: 'input' },
    { key: 'password', label: '密码', type: 'password' }
  ],
  url_fetch: [
    { key: 'timeout', label: '超时（秒）', type: 'number' }
  ],
  local: [],
  paste: []
}

const JSON_FIELDS = {
  mcp: ['servers'],
  http: ['headers']
}

const kindFields = computed(() => KIND_FIELDS[form.kind] || [])
const kindDesc = computed(() => kinds.value.find((k) => k.kind === form.kind)?.desc || '')

async function load() {
  loading.value = true
  try {
    const [conns, kds] = await Promise.all([connectorApi.list(0), connectorApi.kinds()])
    connectors.value = conns
    kinds.value = kds
  } finally {
    loading.value = false
  }
}

function onKindChange() {
  form.cfg = {}
  form.name = form.name || kinds.value.find((k) => k.kind === form.kind)?.name || ''
}

function openCreate() {
  Object.assign(form, { id: null, kind: '', name: '', enabled: true, cfg: {} })
  dialogVisible.value = true
}

function openEdit(c) {
  const cfg = {}
  for (const f of KIND_FIELDS[c.kind] || []) {
    const raw = c.cfg?.[f.key]
    cfg[f.key] = JSON_FIELDS[c.kind]?.includes(f.key)
      ? (raw != null ? JSON.stringify(raw, null, 2) : '')
      : raw ?? (f.type === 'number' ? undefined : '')
  }
  Object.assign(form, { id: c.id, kind: c.kind, name: c.name, enabled: c.enabled, cfg })
  dialogVisible.value = true
}

function buildCfg() {
  const cfg = {}
  for (const f of KIND_FIELDS[form.kind] || []) {
    let v = form.cfg[f.key]
    if (JSON_FIELDS[form.kind]?.includes(f.key)) {
      if (!v || !String(v).trim()) continue
      try {
        v = JSON.parse(v)
      } catch {
        throw new Error(`字段「${f.label}」不是合法 JSON`)
      }
    } else if (f.type === 'number') {
      if (v == null || v === '') continue
      v = Number(v)
    }
    if (v !== '' && v != null) cfg[f.key] = v
  }
  return cfg
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写名称')
  let cfg
  try {
    cfg = buildCfg()
  } catch (e) {
    return ElMessage.error(e.message)
  }
  saving.value = true
  try {
    const payload = { project_id: 0, kind: form.kind, name: form.name, cfg, enabled: form.enabled }
    if (form.id) {
      await connectorApi.update(form.id, payload)
      ElMessage.success('连接器已更新')
    } else {
      await connectorApi.create(payload)
      ElMessage.success('连接器已创建')
    }
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(c, v) {
  await connectorApi.update(c.id, { project_id: c.project_id || 0, kind: c.kind, name: c.name, cfg: c.cfg || {}, enabled: v })
  c.enabled = v
  ElMessage.success(v ? '已启用' : '已禁用')
}

async function remove(c) {
  try {
    await ElMessageBox.confirm(`确定删除连接器「${c.name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  await connectorApi.remove(c.id)
  ElMessage.success('已删除')
  await load()
}

function openTest(c) {
  testConnector.value = c
  testParams.value = c.kind === 'url_fetch' || c.kind === 'http' ? JSON.stringify({ url: c.cfg?.url || '' }, null, 2) : '{}'
  testTool.value = ''
  testResult.value = ''
  testVisible.value = true
}

async function doTest() {
  const c = testConnector.value
  let params = {}
  try {
    params = testParams.value.trim() ? JSON.parse(testParams.value) : {}
  } catch {
    return ElMessage.error('参数不是合法 JSON')
  }
  if (c.kind === 'mcp' && testTool.value) params.tool = testTool.value
  testing.value = true
  try {
    const r = await connectorApi.fetch({ kind: c.kind, cfg: c.cfg || {}, params })
    testResult.value = r.text || '(空)'
  } finally {
    testing.value = false
  }
}

async function openMcpTools(c) {
  toolsConnector.value = c
  toolsVisible.value = true
  mcpTools.value = []
  const r = await connectorApi.mcpTools(c.id)
  mcpTools.value = r.tools || []
}

function formatDate(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}

onMounted(load)
</script>

<style scoped>
.mb12 {
  margin-bottom: 12px;
}

.connector-tips {
  margin: 6px 0 4px;
  padding-left: 18px;
  font-size: 13px;
  line-height: 2;
  color: var(--text);
}

.connector-tips b {
  font-family: Consolas, Menlo, monospace;
}

.form-hint {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 6px;
}

.mono-input :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin: 14px 0 8px;
}
</style>
