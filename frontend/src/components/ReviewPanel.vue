<template>
  <div class="review-panel">
    <div class="row-actions">
      <el-button :loading="exporting === 'xmind'" @click="exportCases('xmind')">
        <el-icon style="margin-right: 4px"><Download /></el-icon>导出 XMind
      </el-button>
      <el-button :loading="exporting === 'excel'" @click="exportCases('excel')">
        <el-icon style="margin-right: 4px"><Download /></el-icon>导出 Excel
      </el-button>
      <el-button type="success" :loading="reviewing" @click="approve">
        <el-icon style="margin-right: 4px"><CircleCheck /></el-icon>评审通过
      </el-button>
      <el-button type="danger" plain :loading="reviewing" @click="returnCases">
        <el-icon style="margin-right: 4px"><RefreshLeft /></el-icon>打回
      </el-button>
    </div>

    <div class="mt8 block-title">上传修改后的用例（XMind / Excel）</div>
    <UploadZone
      accept=".xmind,.xlsx,.xls"
      accept-hint="下载标准模板修改后回传，将回读为批准用例集"
      placeholder="点击或拖拽修改后的用例文件到此处"
      @change="reviewFile = $event"
    />
    <el-button
      type="primary"
      class="mt8"
      :loading="importing"
      :disabled="!reviewFile"
      @click="importReviewed"
    >
      <el-icon style="margin-right: 4px"><Upload /></el-icon>上传并回读为批准
    </el-button>

    <div v-if="latestTree" class="mt8">
      <div class="block-title">当前用例集预览</div>
      <CaseTree :tree="latestTree" />
    </div>

    <div class="mt8">
      <div class="block-title">评审记录</div>
      <el-empty v-if="!caseSets.length" description="暂无评审记录" :image-size="40" />
      <el-timeline v-else>
        <el-timeline-item
          v-for="cs in caseSets"
          :key="cs.id"
          :timestamp="formatDate(cs.created_at)"
          :type="cs.status === 'approved' ? 'success' : cs.status === 'returned' ? 'danger' : 'primary'"
        >
          v{{ cs.version }} ·
          <span class="status-badge" :class="cs.status">{{ csStatus(cs.status) }}</span>
          <span v-if="cs.gen_meta?.reason" class="muted">（{{ cs.gen_meta.reason }}）</span>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import UploadZone from './UploadZone.vue'
import CaseTree from './CaseTree.vue'
import { artifactApi, aiApi } from '@/api'

const props = defineProps({
  project: { type: Object, default: null },
  run: { type: Object, default: null }
})

const emit = defineEmits(['changed'])

const caseSets = ref([])
const latestTree = ref(null)
const exporting = ref('')
const reviewing = ref(false)
const reviewFile = ref(null)
const importing = ref(false)

async function loadCaseSets() {
  if (!props.run) return
  caseSets.value = await aiApi.caseSets(props.run.id)
  if (caseSets.value.length) latestTree.value = caseSets.value[0].content
}

async function exportCases(format) {
  exporting.value = format
  try {
    const r = await aiApi.exportCases({ run_id: props.run.id, format, project: props.project?.name || '' })
    if (r?.artifact_id) {
      // blob 下载：await 之后 window.open 会被浏览器弹窗拦截（表现为点了没反应）
      await artifactApi.download(r.artifact_id, r.name)
      ElMessage.success('导出成功，已开始下载')
    }
  } finally {
    exporting.value = ''
  }
}

async function approve() {
  reviewing.value = true
  try {
    const r = await aiApi.review({ run_id: props.run.id, result: 'approved', reason: '', action: '', reviewer: '' })
    ElMessage.success(r.message || '评审通过')
    await loadCaseSets()
    emit('changed')
  } finally {
    reviewing.value = false
  }
}

async function returnCases() {
  try {
    const { value } = await ElMessageBox.prompt('打回必须填写原因', '打回用例集', {
      inputPlaceholder: '请说明需要修改的地方…',
      confirmButtonText: '打回',
      cancelButtonText: '取消',
      inputValidator: (v) => (v && v.trim() ? true : '原因不能为空')
    })
    reviewing.value = true
    try {
      const r = await aiApi.review({ run_id: props.run.id, result: 'returned', reason: value, action: 'regenerate', reviewer: '' })
      ElMessage.success(r.message || '已打回')
      await loadCaseSets()
      emit('changed')
    } finally {
      reviewing.value = false
    }
  } catch {
    /* 取消 */
  }
}

async function importReviewed() {
  if (!reviewFile.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('run_id', props.run.id)
    fd.append('project', props.project?.name || '')
    fd.append('file', reviewFile.value)
    const r = await aiApi.importReviewed(fd)
    ElMessage.success(r.message || '已回读为批准用例集')
    reviewFile.value = null
    await loadCaseSets()
    emit('changed')
  } finally {
    importing.value = false
  }
}

function formatDate(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}

function csStatus(s) {
  return { generated: '已生成', approved: '已批准', returned: '已打回', reviewed: '已评审' }[s] || s
}

onMounted(loadCaseSets)
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

.row-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
