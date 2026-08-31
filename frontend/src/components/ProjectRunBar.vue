<template>
  <div class="project-run-bar">
    <h3 class="page-title">{{ project?.name || '项目' }}</h3>
    <span v-if="project && project.desc" class="muted bar-desc">{{ project.desc }}</span>
    <el-select
      :model-value="modelValue"
      placeholder="选择流程实例"
      style="width: 220px"
      :loading="loading"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <el-option
        v-for="r in runs"
        :key="r.id"
        :label="runLabel(r)"
        :value="r.id"
      />
    </el-select>
    <span v-if="currentRun" class="status-badge" :class="currentRun.status">
      {{ runStatus(currentRun.status) }}
    </span>
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  project: { type: Object, default: null },
  runs: { type: Array, default: () => [] },
  modelValue: { type: [Number, String], default: null },
  loading: { type: Boolean, default: false }
})

defineEmits(['update:modelValue'])

const currentRun = computed(() =>
  props.runs.find((r) => r.id === props.modelValue)
)

/* 实例显示名：只显示名称；无名称时用项目内序号兜底（不显示全局 #id） */
function runLabel(r) {
  return r.name || (r.run_no ? `流程 ${r.run_no}` : '流程')
}

function runStatus(s) {
  return { pending: '待处理', running: '进行中', success: '已完成', failed: '失败', returned: '打回' }[s] || s
}
</script>

<style scoped>
.project-run-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.bar-desc {
  font-size: 13px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
