<template>
  <div class="page">
    <div class="page-header">
      <ProjectRunBar
        :project="project"
        :runs="runs"
        :model-value="selectedRunId"
        :loading="runsLoading"
        @update:model-value="onSelectRun"
      >
        <el-button :icon="Refresh" @click="refresh">刷新</el-button>
      </ProjectRunBar>
    </div>

    <el-empty v-if="!selectedRunId" description="请先选择流程实例" :image-size="60" />

    <template v-else>
      <div class="panel">
        <h4 class="panel-title">执行操作</h4>
        <div class="toolbar">
          <el-button :loading="envChecking" @click="envCheck">
            <el-icon style="margin-right: 4px"><Monitor /></el-icon>环境自检
          </el-button>
          <el-button type="primary" :loading="executing" @click="execRun">
            <el-icon style="margin-right: 4px"><VideoPlay /></el-icon>执行测试
          </el-button>
          <el-button @click="openAllure">
            <el-icon style="margin-right: 4px"><Link /></el-icon>打开 Allure 报告
          </el-button>
        </div>

        <template v-if="envItems.length">
          <div class="block-title">环境自检结果</div>
          <el-table :data="envItems" size="small" border>
            <el-table-column prop="name" label="检查项" min-width="150" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <span class="pill" :class="row.ok ? 'pill-success' : 'pill-danger'">
                  {{ row.ok ? '通过' : '失败' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip />
          </el-table>
        </template>
      </div>

      <div class="panel">
        <h4 class="panel-title">执行历史</h4>
        <el-table
          :data="history"
          size="small"
          border
          highlight-current-row
          @row-click="loadDetail"
        >
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <span class="status-badge" :class="row.status">{{ execStatus(row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" min-width="150">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="通过/失败" min-width="120">
            <template #default="{ row }">
              <span class="pill pill-success">{{ row.summary?.passed ?? 0 }} 通过</span>
              <span class="pill pill-danger">{{ (row.summary?.failures ?? 0) + (row.summary?.errors ?? 0) }} 失败</span>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="detail" class="mt8">
          <div class="block-title">执行详情 #{{ detail.id }}</div>
          <div class="summary-stats">
            <div class="stat"><b>{{ detail.summary?.total ?? 0 }}</b><span>总计</span></div>
            <div class="stat ok"><b>{{ detail.summary?.passed ?? 0 }}</b><span>通过</span></div>
            <div class="stat fail"><b>{{ (detail.summary?.failures ?? 0) + (detail.summary?.errors ?? 0) }}</b><span>失败/错误</span></div>
            <div class="stat skip"><b>{{ detail.summary?.skipped ?? 0 }}</b><span>跳过</span></div>
          </div>
          <div v-if="(detail.summary?.cases || []).length" class="block-title mt8">
            逐用例结果（{{ detail.summary.cases.length }} 条）
          </div>
          <el-table v-if="(detail.summary?.cases || []).length"
                    :data="detail.summary.cases" size="small" max-height="360">
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status==='通过'?'success':(row.status==='跳过'?'info':'danger')" effect="dark">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="用例名" min-width="280" show-overflow-tooltip />
            <el-table-column label="耗时" width="90">
              <template #default="{ row }">{{ row.time ? (row.time*1000).toFixed(0)+' ms' : '-' }}</template>
            </el-table-column>
          </el-table>
          <div v-if="detail.error_log" class="block-title mt8">错误日志</div>
          <pre v-if="detail.error_log" class="code-block">{{ detail.error_log }}</pre>
        </div>
      </div>

      <div class="panel">
        <h4 class="panel-title">Allure 报告</h4>
        <AllureFrame :src="allureUrl" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Monitor, VideoPlay, Link } from '@element-plus/icons-vue'
import ProjectRunBar from '@/components/ProjectRunBar.vue'
import AllureFrame from '@/components/AllureFrame.vue'
import { projectApi, workflowApi, execApi, aiApi, allureReportUrl } from '@/api'

const route = useRoute()

const project = ref(null)
const runs = ref([])
const runsLoading = ref(false)
const selectedRunId = ref(null)

const envItems = ref([])
const envChecking = ref(false)
const executing = ref(false)
const history = ref([])
const detail = ref(null)

const run = computed(() => runs.value.find((r) => r.id === selectedRunId.value))
const allureUrl = computed(() =>
  project.value && selectedRunId.value
    ? allureReportUrl(project.value.name, selectedRunId.value)
    : ''
)

async function loadProject() {
  project.value = await projectApi.get(route.params.id)
}

async function loadRuns() {
  runsLoading.value = true
  try {
    runs.value = await workflowApi.runs(route.params.id)
    if (!selectedRunId.value && runs.value.length) {
      selectedRunId.value = Number(route.query.run) || runs.value[0].id
      await loadHistory()
    }
  } finally {
    runsLoading.value = false
  }
}

async function onSelectRun() {
  envItems.value = []
  detail.value = null
  await loadHistory()
}

async function loadHistory() {
  if (!selectedRunId.value) return
  history.value = await execApi.runs(selectedRunId.value)
  // 自动回显最新一次执行详情（关掉页面再进不丢内容）
  if (history.value.length && !detail.value) {
    detail.value = await execApi.detail(history.value[0].id)
  }
}

async function loadDetail(row) {
  detail.value = await execApi.detail(row.id)
}

async function refresh() {
  await loadRuns()
  await loadHistory()
}

async function envCheck() {
  if (!project.value) return
  envChecking.value = true
  try {
    const r = await execApi.envCheck(project.value.id)
    envItems.value = r.items || []
  } finally {
    envChecking.value = false
  }
}

async function execRun() {
  if (!project.value) return
  executing.value = true
  try {
    let module = 'module'
    try {
      const sets = await aiApi.caseSets(selectedRunId.value)
      module = sets[0]?.content?.module || module
    } catch {
      /* 取不到 module 时使用默认值 */
    }
    const r = await execApi.run({ run_id: selectedRunId.value, module, project_id: project.value.id })
    const first = r.result || r
    if (first.status === 'running' && first.message && first.message.includes('轮询')) {
      // 后台执行模式：轮询直到结束
      ElMessage.info('已提交后台执行，正在轮询结果…')
      const execId = r.execution_id
      const deadline = Date.now() + 31 * 60 * 1000
      while (Date.now() < deadline) {
        await new Promise(res => setTimeout(res, 3000))
        const d = await execApi.detail(execId)
        detail.value = d
        if (d.status && d.status !== 'running') break
      }
    } else {
      detail.value = first
    }
    ElMessage.success('执行完成')
    envItems.value = detail.value?.env_check?.items || envItems.value
    await loadHistory()
  } finally {
    executing.value = false
  }
}

function openAllure() {
  window.open(allureUrl.value, '_blank')
}

function formatDate(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}

function execStatus(s) {
  return { pending: '待处理', env_fail: '环境失败', running: '执行中', passed: '通过', failed: '失败' }[s] || s
}

onMounted(async () => {
  await loadProject()
  await loadRuns()
})
</script>

<style scoped>
.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin: 14px 0 8px;
}

.mt8 {
  margin-top: 8px;
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.stat {
  background: var(--secondary);
  border-radius: var(--radius-control);
  padding: 10px 8px;
  text-align: center;
}

.stat b {
  display: block;
  font-size: 20px;
  color: var(--text);
}

.stat span {
  font-size: 12px;
  color: var(--text-secondary);
}

.stat.ok b {
  color: #0aa368;
}

.stat.fail b {
  color: var(--danger);
}

.stat.skip b {
  color: var(--warning);
}
</style>
