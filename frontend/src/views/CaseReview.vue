<template>
  <div class="page">
    <div class="page-header">
      <ProjectRunBar
        :project="project"
        :runs="runs"
        :model-value="selectedRunId"
        :loading="runsLoading"
        @update:model-value="onSelectRun"
      />
    </div>

    <div class="panel">
      <h4 class="panel-title">用例评审</h4>
      <el-empty v-if="!selectedRunId" description="请先选择流程实例" :image-size="60" />
      <ReviewPanel
        v-else
        :key="selectedRunId"
        :project="project"
        :run="run"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ProjectRunBar from '@/components/ProjectRunBar.vue'
import ReviewPanel from '@/components/ReviewPanel.vue'
import { projectApi, workflowApi } from '@/api'

const route = useRoute()

const project = ref(null)
const runs = ref([])
const runsLoading = ref(false)
const selectedRunId = ref(null)

const run = computed(() => runs.value.find((r) => r.id === selectedRunId.value))

async function loadProject() {
  project.value = await projectApi.get(route.params.id)
}

async function loadRuns() {
  runsLoading.value = true
  try {
    runs.value = await workflowApi.runs(route.params.id)
    if (!selectedRunId.value && runs.value.length) {
      selectedRunId.value = Number(route.query.run) || runs.value[0].id
    }
  } finally {
    runsLoading.value = false
  }
}

function onSelectRun() {
  /* ReviewPanel 通过 :key 重挂载 */
}

onMounted(async () => {
  await loadProject()
  await loadRuns()
})
</script>
