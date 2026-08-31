<template>
  <div class="diff-view">
    <div v-if="!lines.length" class="diff-empty muted">暂无 diff 内容</div>
    <div v-else class="diff-content">
      <div
        v-for="(line, i) in lines"
        :key="i"
        class="diff-line"
        :class="lineClass(line)"
      >
        <span class="diff-marker">{{ line[0] }}</span>
        <span class="diff-text">{{ line.slice(1) || ' ' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** diff 文本（unified diff）或任意前后对比文本 */
  diff: { type: String, default: '' },
  /** 可选：两段对比文本（oldText/newText），自动生成简易 diff */
  oldText: { type: String, default: '' },
  newText: { type: String, default: '' }
})

const lines = computed(() => {
  const raw = props.diff || ''
  const source = raw ? raw.split('\n') : []
  if (source.length) return source
  // 简易两栏对比
  const oldLines = (props.oldText || '').split('\n')
  const newLines = (props.newText || '').split('\n')
  const max = Math.max(oldLines.length, newLines.length)
  const out = []
  for (let i = 0; i < max; i++) {
    const o = oldLines[i] ?? ''
    const n = newLines[i] ?? ''
    if (o !== n) {
      if (o) out.push(`-${o}`)
      if (n) out.push(`+${n}`)
    }
  }
  return out
})

function lineClass(line) {
  const c = line[0]
  if (c === '+') return 'add'
  if (c === '-') return 'del'
  if (c === '@') return 'meta'
  return ''
}
</script>

<style scoped>
.diff-view {
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  overflow: hidden;
  background: var(--card);
}

.diff-empty {
  padding: 20px;
  text-align: center;
  font-size: 13px;
}

.diff-content {
  max-height: 360px;
  overflow: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.7;
}

.diff-line {
  display: flex;
  gap: 6px;
  padding: 0 10px;
  white-space: pre-wrap;
  word-break: break-all;
}

.diff-marker {
  width: 12px;
  flex-shrink: 0;
  color: var(--text-secondary);
  user-select: none;
}

.diff-text {
  flex: 1;
  color: var(--text);
}

.diff-line.add {
  background: rgba(29, 201, 129, 0.1);
}

.diff-line.add .diff-marker,
.diff-line.add .diff-text {
  color: #0aa368;
}

.diff-line.del {
  background: rgba(232, 70, 58, 0.09);
}

.diff-line.del .diff-marker,
.diff-line.del .diff-text {
  color: var(--danger);
}

.diff-line.meta {
  background: var(--primary-light);
}

.diff-line.meta .diff-text {
  color: var(--primary);
  font-weight: 600;
}
</style>
