<template>
  <div class="page board-page">
    <!-- 顶部：项目名 + 流程实例选择 + 新建 -->
    <div class="page-header">
      <div class="board-head-left">
        <h3 class="page-title">{{ project?.name || '项目工作台' }}</h3>
        <el-select
          v-model="selectedRunId"
          placeholder="选择流程实例"
          class="run-select"
          :loading="runsLoading"
          @change="onSelectRun"
        >
          <el-option
            v-for="r in runs"
            :key="r.id"
            :label="runLabel(r)"
            :value="r.id"
          />
        </el-select>
        <span v-if="run" class="status-badge" :class="run.status">{{ runStatus(run.status) }}</span>
        <el-button :icon="Plus" @click="openCreate">新建流程实例</el-button>
        <el-button
          v-if="selectedRunId"
          :icon="Delete"
          type="danger"
          plain
          :loading="deleting"
          @click="confirmDeleteRun"
        >删除实例</el-button>
      </div>
      <div class="toolbar">
        <el-button :icon="Refresh" :loading="loading" @click="refresh">刷新</el-button>
        <!-- 本次需求完成：把当前实例已评审通过的用例集快照入库到知识库 -->
        <el-button
          v-if="selectedRunId"
          type="success"
          plain
          :loading="collecting"
          @click="collectKnowledge"
        >
          <el-icon style="margin-right: 4px"><Collection /></el-icon>本次需求完成
        </el-button>
        <el-tooltip placement="top">
          <template #content>
            <div>当业务功能测试用例或接口用例评审通过后，<br />点击该按钮可将用例保存到知识库，供后续生成用例时参考。</div>
          </template>
          <el-icon class="kb-info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
        <el-button
          v-if="showOneClickRun"
          type="primary"
          :loading="autoRunning"
          @click="oneClickRun"
        >
          <el-icon style="margin-right: 4px"><VideoPlay /></el-icon>一键执行
        </el-button>
      </div>
    </div>

    <!-- 中部：动画工作流看板 -->
    <AnimatedRail
      v-loading="loading"
      :stages="stages"
      :selected-stage-id="selectedStage?.id"
      @select="onStageClick"
    />

    <!-- 阶段详情：点击卡片在卡片下方内嵌展示（默认收起，点卡片展开） -->
    <div class="mt8">
      <StageDetail
        v-model="drawerVisible"
        :project="project"
        :run="run"
        :stage="selectedStage"
        :stages="stages"
        @changed="refresh"
      />
    </div>

    <!-- 流程全部完成后：本次执行总结（AI 生成） -->
    <div v-if="run && run.status === 'success'" class="run-summary-card mt8">
      <div class="summary-head">
        <div class="summary-title">
          <el-icon style="margin-right: 6px"><CircleCheckFilled /></el-icon>
          本次执行总结（AI 生成）
        </div>
        <el-button size="small" :loading="summaryGenerating" @click="genRunSummary(true)">
          重新生成
        </el-button>
      </div>
      <div v-if="summaryGenerating" class="summary-body muted">AI 正在汇总本次流程数据，请稍候…</div>
      <div v-else-if="runSummaryText" class="summary-body">{{ runSummaryText }}</div>
      <div v-else class="summary-body muted">尚无总结，点击「重新生成」创建。</div>
    </div>

    <!-- 一键执行进度面板（执行中 / 有历史步骤时显示） -->
    <div v-if="autoRunning || autoRunSteps.length" class="auto-run-card mt8">
      <div class="summary-head">
        <div class="summary-title running">
          <el-icon style="margin-right: 6px"><VideoPlay /></el-icon>
          一键执行进度{{ autoRunning ? '' : '（已结束）' }}
        </div>
        <el-tag v-if="autoRunError" size="small" type="danger" effect="plain">{{ autoRunError }}</el-tag>
        <el-tag v-else-if="!autoRunning" size="small" type="success" effect="plain">完成</el-tag>
      </div>
      <!-- 真实进度：按阶段完成数/未跳过阶段总数计算（每 2 秒随轮询刷新） -->
      <el-progress
        v-if="autoRunning"
        :percentage="autoRunPct"
        :stroke-width="8"
        :status="autoRunPct >= 100 ? 'success' : undefined"
        class="mt8"
      />
      <div class="think-list mt8">
        <div v-if="!autoRunSteps.length" class="think-line muted">等待任务启动…</div>
        <div v-for="(s, i) in autoRunSteps" :key="i" class="think-line">
          <span class="think-ts">{{ s.ts }}</span>
          <span class="think-text">{{ s.text }}</span>
        </div>
      </div>
    </div>

    <!-- 底部快捷说明 -->
    <div v-if="stages.length" class="board-tip muted">
      <el-icon><InfoFilled /></el-icon>
      点击阶段卡片可逐步操作；上传需求文档并生成需求摘要后点「一键执行」：
      <b>已有接口文档</b>时自动跑完剩余全流程（含执行测试与失败 AI 修复），
      <b>仅有需求文档</b>时自动执行到「生成用例」为止，上传接口文档后可再次一键执行。
    </div>

    <!-- 新建流程实例对话框 -->
    <el-dialog v-model="createDialogVisible" title="新建流程实例" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="实例名称">
          <el-input v-model="newRunForm.name" placeholder="如：第一轮全流程（留空自动命名「第 N 轮流程」）" />
        </el-form-item>
        <el-form-item label="流程模板" required>
          <el-select v-model="newRunForm.template_id" placeholder="选择模板" style="width: 100%">
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="`${t.name}（${(t.stages || []).length} 阶段）`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createRun">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, InfoFilled, Delete, CircleCheckFilled, VideoPlay } from '@element-plus/icons-vue'
import AnimatedRail from '@/components/AnimatedRail.vue'
import StageDetail from '@/components/StageDetail.vue'
import { projectApi, workflowApi, aiApi, knowledgeApi } from '@/api'

const route = useRoute()
const router = useRouter()

const project = ref(null)
const runs = ref([])
const runsLoading = ref(false)
const selectedRunId = ref(null)
const stages = ref([])
const loading = ref(false)
const drawerVisible = ref(false)
const selectedStage = ref(null)

const createDialogVisible = ref(false)
const templates = ref([])
const creating = ref(false)
const deleting = ref(false)
const collecting = ref(false)
const newRunForm = reactive({ template_id: null, name: '' })

const run = computed(() => runs.value.find((r) => r.id === selectedRunId.value))

/* 仅需求模式完成的实例（自动化生成/执行阶段为 skipped）：上传接口文档后可续跑全流程 */
const canContinueRun = computed(() =>
  stages.value.some((s) => ['auto_gen', 'execute'].includes(s.stage_type) && s.status === 'skipped')
)

/* 一键执行/续跑 按钮：实例未完成，或存在失败阶段（可重跑），或有可续跑阶段时显示 */
const showOneClickRun = computed(() =>
  run.value && (
    run.value.status !== 'success' ||
    canContinueRun.value ||
    stages.value.some((s) => s.status === 'failed')
  )
)

/* ---------- 一键执行（自动跑完剩余全流程） ---------- */
const autoRunning = ref(false)
const autoRunSteps = ref([])
const autoRunError = ref('')
const autoRunPct = ref(0)
let autoRunTimer = null

/* 真实进度：已完成阶段数 / 未跳过阶段总数（与看板统计口径一致） */
function computeAutoRunPct() {
  const active = stages.value.filter((s) => s.status !== 'skipped')
  const done = active.filter((s) => s.status === 'success').length
  autoRunPct.value = active.length ? Math.round((done / active.length) * 100) : 0
}

async function oneClickRun() {
  if (!selectedRunId.value || autoRunning.value) return
  // 前置校验：需求阶段必须已生成摘要（生成摘要的前提是有需求文档，二者其一缺都会提示）
  const reqStage = stages.value.find((s) => s.stage_type === 'requirement')
  if (!reqStage?.meta?.summary) {
    ElMessage.warning('请先在「需求分析」阶段上传需求文档并生成需求摘要，再使用一键执行')
    return
  }
  try {
    const r = await aiApi.autoRun({ run_id: selectedRunId.value, project_id: Number(route.params.id) })
    // 后端按是否上传接口文档自动选择模式：全流程 / 仅执行到用例评审
    ElMessage.success(r.message || '一键执行已启动，可在下方进度面板查看过程')
  } catch {
    return /* 未就绪/进行中：提示由拦截器弹出 */
  }
  startAutoRunPolling()
}

function startAutoRunPolling() {
  stopAutoRunPolling()
  autoRunning.value = true
  autoRunError.value = ''
  computeAutoRunPct()
  autoRunTimer = setInterval(async () => {
    if (!selectedRunId.value) return
    try {
      // 双通道轮询：① 过程步骤日志；② 阶段状态（计算真实进度百分比）
      const [d, sts] = await Promise.all([
        aiApi.progress(`auto_run:${selectedRunId.value}`),
        workflowApi.stages(selectedRunId.value)
      ])
      autoRunSteps.value = d.steps || []
      stages.value = sts
      computeAutoRunPct()
      if (d.done) {
        stopAutoRunPolling()
        autoRunPct.value = d.error ? autoRunPct.value : 100
        autoRunError.value = d.error || ''
        if (d.error) ElMessage.error(`一键执行未完成：${d.error}`)
        else ElMessage.success('一键执行已完成')
        await refresh()
      }
    } catch { /* 轮询失败静默，下轮重试 */ }
  }, 2000)
}

function stopAutoRunPolling() {
  if (autoRunTimer) { clearInterval(autoRunTimer); autoRunTimer = null }
  // 复位 running 标记：完成后进度面板从「执行中」切到「已结束」，
  // el-progress 通过 v-if="autoRunning" 隐藏，避免完成后 UI 仍停留在 100% running 状态。
  autoRunning.value = false
}

/* 切换实例 / 离开页面时停止轮询 */
watch(selectedRunId, () => {
  stopAutoRunPolling()
  autoRunning.value = false
  autoRunSteps.value = []
  autoRunError.value = ''
  autoRunPct.value = 0
})

async function loadProject() {
  project.value = await projectApi.get(route.params.id)
}

async function loadRuns(select = true) {
  runsLoading.value = true
  try {
    runs.value = await workflowApi.runs(route.params.id)
    if (select) {
      // 优先级：URL ?run= 参数 > 上次进入的实例（localStorage 记忆）> 最新实例
      const fromQuery = Number(route.query.run)
      const lastRunId = Number(localStorage.getItem(runMemoryKey.value))
      const valid = (id) => id && runs.value.some((r) => r.id === id)
      selectedRunId.value = valid(fromQuery) ? fromQuery
        : (valid(lastRunId) ? lastRunId : runs.value[0]?.id ?? null)
    }
  } finally {
    runsLoading.value = false
  }
}

/* 实例记忆：按项目存 localStorage，用户上次选中哪个实例，下次进入仍显示哪个 */
const runMemoryKey = computed(() => `last_run_project_${route.params.id}`)

function rememberRun(id) {
  if (id) localStorage.setItem(runMemoryKey.value, String(id))
}

watch(selectedRunId, (v) => rememberRun(v))

async function loadStages() {
  if (!selectedRunId.value) {
    stages.value = []
    return
  }
  loading.value = true
  try {
    stages.value = await workflowApi.stages(selectedRunId.value)
    // 流程真正全部完成（成功/已跳过）且实例状态为已完成 → 才自动拉取 AI 执行总结。
    // 不能只看 run.status：重新生成用例后 case_gen 阶段回到 pending_review，
    // 但 run.status 仍可能保留 success，若按它触发会发现后端 422「流程尚未全部完成」，
    // 每次刷新/切页都弹错误提示（AI 总结未完成提示一直被弹）。
    const allDone = stages.value.every((s) => s.status === 'success' || s.status === 'skipped')
    if (run.value?.status === 'success' && allDone) genRunSummary(false)
  } finally {
    loading.value = false
  }
}

/* ---------- 执行总结（AI 文字总结，完成后展示在卡片下方） ---------- */
const runSummaryText = ref('')
const summaryGenerating = ref(false)

async function genRunSummary(force) {
  if (!selectedRunId.value || summaryGenerating.value) return
  summaryGenerating.value = true
  try {
    const r = await aiApi.runSummary(selectedRunId.value, !!force)
    runSummaryText.value = r.summary || ''
  } catch {
    /* 未完成/失败提示由拦截器弹出 */
  } finally {
    summaryGenerating.value = false
  }
}

watch(selectedRunId, () => { runSummaryText.value = '' })

async function onSelectRun() {
  // 切换流程实例：关闭/清空上一实例的阶段详情
  selectedStage.value = null
  drawerVisible.value = false
  await loadStages()
}

async function refresh() {
  await loadRuns(false)
  await loadStages()
}

/* 「本次需求完成」：把当前实例已评审通过的用例集快照入库到知识库（多次点击=多次独立入库） */
async function collectKnowledge() {
  if (!selectedRunId.value) return
  try {
    await ElMessageBox.confirm(
      '确认将该实例已评审通过的业务功能用例 / 接口测试用例保存到知识库吗？',
      '本次需求完成',
      { type: 'info', confirmButtonText: '确认入库', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  collecting.value = true
  try {
    const r = await knowledgeApi.collect(selectedRunId.value)
    const miss = (r.missing || []).map((t) => (t === 'api' ? '接口测试用例' : '业务功能用例'))
    if (r.added > 0) {
      ElMessage.success(
        miss.length
          ? `已入库 ${r.added} 份用例；${miss.join('、')}暂未评审通过，未入库`
          : `已入库 ${r.added} 份用例到知识库，可到「知识库」页查看`
      )
    } else {
      ElMessage.warning('暂无可入库用例：请先在「生成用例」阶段生成并评审通过业务功能/接口测试用例')
    }
  } finally {
    collecting.value = false
  }
}

async function openCreate() {
  templates.value = await workflowApi.templates(route.params.id)
  newRunForm.template_id = templates.value[0]?.id ?? null
  newRunForm.name = ''
  createDialogVisible.value = true
}

async function createRun() {
  if (!newRunForm.template_id) return ElMessage.warning('请选择流程模板')
  creating.value = true
  try {
    const r = await workflowApi.createRun({
      project_id: route.params.id,
      template_id: newRunForm.template_id,
      name: newRunForm.name
    })
    ElMessage.success('流程实例已创建')
    createDialogVisible.value = false
    await loadRuns(false)
    selectedRunId.value = r.id
    await loadStages()
  } finally {
    creating.value = false
  }
}

async function confirmDeleteRun() {
  if (!selectedRunId.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除流程「${runLabel(runs.value.find((r) => r.id === selectedRunId.value))}」？该实例的阶段进度、用例集、工件文件与执行记录将一并删除，不可恢复。`,
      '删除流程实例',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deleting.value = true
  try {
    await workflowApi.removeRun(selectedRunId.value)
    ElMessage.success('流程实例已删除')
    selectedStage.value = null
    drawerVisible.value = false
    selectedRunId.value = null
    stages.value = []
    await loadRuns(true)   // 自动选中剩余最新实例
    await loadStages()
  } finally {
    deleting.value = false
  }
}

function onStageClick(stage) {
  // 再点当前已展开的卡片 → 收起
  if (drawerVisible.value && selectedStage.value && stage.id === selectedStage.value.id) {
    selectedStage.value = null
    drawerVisible.value = false
    return
  }
  selectedStage.value = stage
  drawerVisible.value = true
}

/* 详情收起（顶部收起按钮 / 底部关闭 / 再点卡片）时清空选中卡片，取消高亮；
   避免「收起后 selectedStage 残留 → 再点同一卡片误走收起分支 → 需点两次才打开」 */
watch(drawerVisible, (v) => {
  if (!v) selectedStage.value = null
})

/* stages 刷新后（如调 summary / upload 自动推进状态后），同步刷新已打开抽屉里的 selectedStage：
   否则 selectedStage 仍指向被替换前的旧对象，抽屉里状态徽章会一直停留在旧 status（如「待处理」）。
   按 id 找到新数组里对应的最新对象，引用替换；找不到说明该阶段被删/不在新数组，关闭抽屉。 */
watch(stages, (list) => {
  if (!selectedStage.value) return
  const updated = list.find((s) => s.id === selectedStage.value.id)
  if (updated && updated !== selectedStage.value) {
    selectedStage.value = updated
  } else if (!updated) {
    selectedStage.value = null
    drawerVisible.value = false
  }
})

function runStatus(s) {
  return { pending: '待处理', running: '进行中', success: '已完成', failed: '失败', returned: '打回' }[s] || s
}

/* 实例显示名：只显示名称；无名称时用项目内序号兜底（不显示全局 #id） */
function runLabel(r) {
  return r.name || (r.run_no ? `流程 ${r.run_no}` : '流程')
}

watch(
  () => route.query.run,
  (v) => {
    if (v && runs.value.some((r) => r.id === Number(v))) {
      selectedRunId.value = Number(v)
      loadStages()
    }
  }
)

onMounted(async () => {
  await loadProject()
  await loadRuns(true)
  await loadStages()
  // 页面刷新/重进后，若后台一键执行仍在跑 → 恢复进度轮询
  if (selectedRunId.value) {
    try {
      const d = await aiApi.progress(`auto_run:${selectedRunId.value}`)
      if (d.exists && !d.done) startAutoRunPolling()
      else if (d.exists && d.steps?.length) {
        autoRunSteps.value = d.steps   // 已结束但留有步骤，展示结果
        autoRunError.value = d.error || ''
      }
    } catch { /* 忽略 */ }
  }
})

onUnmounted(stopAutoRunPolling)
</script>

<style scoped>
/* 「本次需求完成」旁的信息提示图标：与按钮同列居中显示 */
.kb-info-icon {
  align-self: center;
  color: var(--text-secondary, #909399);
  cursor: help;
  font-size: 15px;
}

.kb-info-icon:hover {
  color: var(--primary, #4b3fe3);
}

.board-head-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.run-select {
  width: 220px;
}

.board-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  margin-top: 12px;
}

.mt8 {
  margin-top: 8px;
}

/* 流程完成后的 AI 执行总结卡片 */
.run-summary-card, .auto-run-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 18px;
  background: var(--card-bg, #fff);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.summary-title.running {
  color: var(--primary, #4b3fe3);
}

.summary-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.summary-title {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: #0aa368;
}

.summary-body {
  font-size: 13px;
  line-height: 1.9;
  color: var(--text);
  white-space: pre-wrap;
}

/* 一键执行进度步骤列表（与 StageDetail 思考过程同款样式） */
.think-list {
  max-height: 240px;
  overflow-y: auto;
  background: var(--secondary);
  border-radius: var(--radius-control, 6px);
  padding: 6px 10px;
}

.think-line {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.8;
  font-family: Consolas, Menlo, monospace;
}

.think-ts {
  color: var(--text-secondary, #999);
  flex-shrink: 0;
}

.think-text {
  color: var(--text, #333);
  word-break: break-all;
  white-space: pre-wrap;
}

.muted {
  color: var(--text-secondary, #999);
}
</style>
