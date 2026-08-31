<template>
  <div class="artifact-list">
    <el-empty v-if="!items.length" description="暂无工件" :image-size="40" />
    <div v-for="a in items" :key="a.id" class="artifact-item">
      <el-icon class="artifact-icon"><Document /></el-icon>
      <div class="artifact-info">
        <div class="artifact-name">{{ a.name }}</div>
        <div class="artifact-sub">
          {{ a.type }}
          <template v-if="a.version"> · v{{ a.version }}</template>
          <template v-if="a.created_at"> · {{ formatDate(a.created_at) }}</template>
        </div>
      </div>
      <div class="artifact-actions">
        <el-tooltip content="下载" placement="top">
          <el-button size="small" text circle @click="$emit('download', a)">
            <el-icon><Download /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="删除" placement="top">
          <el-button size="small" text circle type="danger" @click="$emit('remove', a)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] }
})

defineEmits(['download', 'remove'])

function formatDate(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.artifact-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  padding: 8px 10px;
  margin-bottom: 6px;
}

.artifact-icon {
  color: var(--primary);
  font-size: 18px;
  flex-shrink: 0;
}

.artifact-info {
  flex: 1;
  min-width: 0;
}

.artifact-name {
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-sub {
  font-size: 12px;
  color: var(--text-secondary);
}

.artifact-actions {
  display: flex;
  align-items: center;
}
</style>
