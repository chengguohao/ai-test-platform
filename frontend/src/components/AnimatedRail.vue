<template>
  <div class="rail">
    <div class="rail-track">
      <template v-if="stages.length">
        <template v-for="(stage, i) in stages" :key="stageKey(stage, i)">
          <!-- 卡片间细线连接 -->
          <div v-if="i > 0" class="connector" :class="connectorClass(stage, i)">
            <span class="connector-line" />
          </div>
          <StepCard :stage="stage" :index="i" :selected="stage.id === selectedStageId" @click="$emit('select', $event)" />
        </template>
      </template>
      <el-empty v-else description="暂无阶段，请先新建流程实例" :image-size="60" />
    </div>

    <!-- 底部进度条：已完成/总数 + 当前操作提示 -->
    <div class="rail-footer">
      <div class="rail-progress">
        <span class="rail-progress-label">流程进度</span>
        <el-progress
          :percentage="progressPct"
          :stroke-width="8"
          :show-text="false"
          class="rail-progress-bar"
        />
        <span class="rail-progress-text">{{ doneCount }}/{{ total }} 已完成</span>
      </div>
      <div class="rail-hint">
        <template v-if="runningStage">
          <span class="hint-dot" />
          <span>当前操作：<b>{{ runningStage.stage_name }}</b></span>
        </template>
        <template v-else-if="total && doneCount === total">
          <span class="hint-dot done" />
          <span>流程已完成</span>
        </template>
        <template v-else-if="total">
          <span class="hint-dot idle" />
          <span>等待启动：点右上角「一键执行」或点击阶段卡片逐步操作</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StepCard from './StepCard.vue'

const props = defineProps({
  stages: { type: Array, default: () => [] },
  selectedStageId: { type: [Number, String], default: null }
})

defineEmits(['select'])

/* 进度统计排除「已跳过」阶段：只有真实执行过的阶段计入（如仅需求模式 = 3/3，而非 6/6） */
const activeStages = computed(() => props.stages.filter((s) => s.status !== 'skipped'))
const doneCount = computed(() => activeStages.value.filter((s) => s.status === 'success').length)
const total = computed(() => activeStages.value.length)
const progressPct = computed(() =>
  total.value ? Math.round((doneCount.value / total.value) * 100) : 0
)
const runningStage = computed(() => props.stages.find((s) => s.status === 'running'))

function stageKey(stage, i) {
  return stage.id != null ? `s-${stage.id}` : `i-${i}`
}

/**
 * 连接线状态：
 * - flowing：前一段 success → 本段 success（紫色流动虚线）
 * - active ：前一段 success → 本段 running（紫色实线，进度已推进到当前）
 * - 其余   ：浅灰实线
 */
function connectorClass(cur, i) {
  const prev = props.stages[i - 1]
  if (!prev) return {}
  if (prev.status === 'success' && cur.status === 'success') return { flowing: true }
  if (prev.status === 'success' && cur.status === 'running') return { active: true }
  return {}
}
</script>

<style scoped>
.rail {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 22px 22px 16px;
}

.rail-track {
  display: flex;
  align-items: stretch;
  gap: 0;
  row-gap: 14px;
  flex-wrap: wrap;   /* 卡片多时换行显示，不再横向滚动留大片空白 */
  padding-bottom: 6px;
  min-height: 130px;
}

/* ---------- 卡片间连接线 ---------- */
.connector {
  flex: 0 0 34px;
  align-self: center;
  height: 3px;
  border-radius: 3px;
  background: rgba(27, 29, 42, 0.1);
  margin: 0 6px;
  overflow: hidden;
}

.connector.active {
  background: var(--primary);
}

/* 流动虚线：repeating-linear-gradient + background-position 动画 */
.connector.flowing .connector-line {
  display: block;
  width: 100%;
  height: 100%;
  background: repeating-linear-gradient(
    90deg,
    var(--primary) 0 6px,
    transparent 6px 12px
  );
  background-size: 12px 100%;
}

@media (prefers-reduced-motion: no-preference) {
  .connector.flowing .connector-line {
    animation: rail-dash 0.7s linear infinite;
  }
}

@keyframes rail-dash {
  to {
    background-position: 12px 0;
  }
}

/* ---------- 底部进度 ---------- */
.rail-footer {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--border);
  flex-wrap: wrap;
}

.rail-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 280px;
}

.rail-progress-label {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.rail-progress-bar {
  flex: 1;
}

.rail-progress-text {
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  min-width: 80px;
}

.rail-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.rail-hint b {
  color: var(--primary);
}

.hint-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
}

.hint-dot.done {
  background: var(--success);
}

.hint-dot.idle {
  background: var(--text-secondary);
  opacity: 0.4;
}
</style>
