<template>
  <article
    class="step-card"
    :class="cardClass"
    :title="stage.meta?.error || stage.stage_name"
    @click="$emit('click', stage)"
  >
    <div class="card-top">
      <span class="idx-badge" :class="{ done: isSuccess }">{{ index + 1 }}</span>
      <span v-if="isRunning" class="pulse-dot" aria-label="进行中" />
    </div>
    <div class="card-name" :title="stage.stage_name">{{ stage.stage_name }}</div>
    <div class="card-desc">{{ desc }}</div>
    <div v-if="pendingReviewText" class="card-pending">{{ pendingReviewText }}</div>
    <span class="status-badge" :class="statusClass">
      <span v-if="isRunning" class="dot" />
      {{ statusText }}
    </span>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  stage: { type: Object, required: true },
  index: { type: Number, default: 0 },
  selected: { type: Boolean, default: false }
})

defineEmits(['click'])

const DESC = {
  requirement: '提交需求资料：上传 / 粘贴 / URL / 对接公司平台',
  api_doc: '提交接口文档；本需求没有新增接口时可跳过',
  case_gen: 'AI 把需求（+接口文档）自动转成测试用例',
  auto_gen: 'AI 按已批准用例生成接口自动化脚本',
  execute: '检查环境，自动跑用例，生成 Allure 报告',
  skill: '单独运行一种 AI 能力，结果存为工件',
  mcp: '从公司平台(MCP)拉取真实资料存为工件'
}

const STATUS_TEXT = {
  pending: '待处理',
  running: '进行中',
  success: '已完成',
  failed: '失败',
  returned: '打回',
  pending_review: '待评审',
  skipped: '已跳过'
}

const isSuccess = computed(() => props.stage.status === 'success')
const isRunning = computed(() => props.stage.status === 'running')
const isMuted = computed(() => props.stage.enabled === false || props.stage.status === 'skipped')
const isDanger = computed(() => props.stage.status === 'failed' || props.stage.status === 'returned')

const statusText = computed(() => STATUS_TEXT[props.stage.status] || props.stage.status || '未知')
const desc = computed(() => DESC[props.stage.stage_type] || '')

/* 生成用例阶段的组合状态文案：按业务/接口两类的生成+评审状态拼装。
   后端在 meta.case_gen_summary 里写入每类型状态（none=未生成 / pending_review=待评审 / approved=已评审）。
   未提供摘要（旧数据/兜底）时回退 pending_review 数组逻辑。 */
const CASE_LABEL = { business: '业务用例', api: '接口用例' }
const TYPE_STATE_TEXT = {
  approved: '已评审',
  pending_review: '待评审',
  none: '待生成'
}
const pendingReviewText = computed(() => {
  if (props.stage.stage_type !== 'case_gen') return ''
  if (props.stage.status === 'success') return ''   // 两类都已评审完成：不显示组合文案
  const summary = props.stage.meta?.case_gen_summary
  if (summary && (summary.business || summary.api)) {
    const parts = []
    for (const t of ['business', 'api']) {
      const s = summary[t]
      if (!s) continue
      parts.push(`${CASE_LABEL[t]}${TYPE_STATE_TEXT[s] || s}`)
    }
    return parts.join('，')
  }
  // 兜底：旧数据无摘要
  if (props.stage.status !== 'pending_review') return ''
  const pending = props.stage.meta?.pending_review || []
  if (pending.length === 0) return '用例已生成，待评审'
  return pending.map((t) => `${CASE_LABEL[t]}待评审`).join('，')
})
const statusClass = computed(() => props.stage.status || 'pending')
const cardClass = computed(() => ({
  'is-selected': props.selected,
  'is-running': isRunning.value,
  'is-success': isSuccess.value,
  'is-muted': isMuted.value,
  'is-danger': isDanger.value
}))
</script>

<style scoped>
.step-card {
  position: relative;
  width: 216px;
  min-height: 128px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 14px 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  flex-shrink: 0;
}

/* 悬停上浮 2px + 淡阴影（仅在允许动画时） */
@media (prefers-reduced-motion: no-preference) {
  .step-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(27, 29, 42, 0.08);
  }
}

.step-card:hover {
  border-color: rgba(75, 63, 227, 0.35);
}

/* 当前阶段：紫色边框高亮 */
.step-card.is-running {
  border: 2px solid var(--primary);
  padding: 13px 13px 11px;
  box-shadow: 0 6px 18px rgba(75, 63, 227, 0.18);
}

/* 被选中查看：紫色边框 + 浅紫背景，与 running（深紫发光）区分，便于定位正在查看的阶段 */
.step-card.is-selected {
  border: 2px solid var(--primary);
  padding: 13px 13px 11px;
  background: rgba(75, 63, 227, 0.05);
  box-shadow: 0 6px 18px rgba(75, 63, 227, 0.18);
}

/* 打回 / 失败：红色描边 */
.step-card.is-danger {
  border-color: rgba(232, 70, 58, 0.45);
}

/* 禁用 / 跳过：置灰 */
.step-card.is-muted {
  opacity: 0.55;
  filter: grayscale(0.6);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.idx-badge {
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
}

.idx-badge.done {
  background: var(--primary);
  color: #fff;
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-top: 4px;
  min-height: 36px;
  /* 允许换行，最多两行，超出省略 */
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* 待评审副文案：橙色小字，醒目但不喧宾夺主 */
.card-pending {
  font-size: 12px;
  font-weight: 600;
  color: #b2761a;
  line-height: 1.4;
}

/* 脉冲点：进行中状态 */
.pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--primary);
  position: relative;
}

@media (prefers-reduced-motion: no-preference) {
  .pulse-dot::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: var(--primary);
    animation: pulse-ring 1.4s ease-out infinite;
  }
}

@keyframes pulse-ring {
  0% {
    transform: scale(1);
    opacity: 0.6;
  }
  100% {
    transform: scale(2.4);
    opacity: 0;
  }
}
</style>
