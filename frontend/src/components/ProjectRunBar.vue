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
        :label="`流程 #${r.id}`"
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
