<template>
  <div class="case-tree-wrap">
    <el-empty v-if="!treeData.length" description="暂无用例树数据" :image-size="50" />
    <el-tree
      v-else
      :data="treeData"
      :props="{ label: 'label', children: 'children' }"
      node-key="key"
      default-expand-all
      :expand-on-click-node="false"
      class="case-tree"
    >
      <template #default="{ data }">
        <div class="tree-node">
          <span v-if="data.type === 'case'" class="case-id">{{ data.caseId }}</span>
          <span class="node-label">{{ data.label }}</span>
          <template v-if="data.type === 'case'">
            <span class="pill" :class="priorityClass(data.priority)">{{ data.priority || '-' }}</span>
            <span v-if="data.api" class="node-api">{{ data.api }}</span>
          </template>
        </div>
      </template>
    </el-tree>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 用例树对象：{module,title,groups:[{name,cases:[{id,title,priority,api,...}]}]} */
  tree: { type: Object, default: () => ({}) }
})

const treeData = computed(() => {
  const t = props.tree || {}
  const root = {
    key: 'root',
    type: 'root',
    label: t.title || t.module || '用例树',
    children: []
  }
  const groups = Array.isArray(t.groups) ? t.groups : []
  root.children = groups.map((g, gi) => ({
    key: `g-${gi}`,
    type: 'group',
    label: g.name || `分组 ${gi + 1}`,
    children: (Array.isArray(g.cases) ? g.cases : []).map((c, ci) => ({
      key: `c-${gi}-${ci}`,
      type: 'case',
      caseId: c.id || `TC-${gi + 1}-${ci + 1}`,
      label: c.title || '(无标题)',
      priority: c.priority,
      api: c.api
    }))
  }))
  return [root]
})

function priorityClass(p) {
  const s = String(p || '')
  if (s.includes('高')) return 'pill-danger'
  if (s.includes('中')) return 'pill'
  return 'pill-success'
}
</script>

<style scoped>
.case-tree-wrap {
  width: 100%;
}

.case-tree {
  background: transparent;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  padding-right: 8px;
}

.case-id {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  background: var(--primary-light);
  border-radius: 6px;
  padding: 1px 6px;
  white-space: nowrap;
}

.node-label {
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-api {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--secondary);
  border-radius: 6px;
  padding: 1px 6px;
  white-space: nowrap;
}

.case-tree :deep(.el-tree-node__content) {
  height: 32px;
  border-radius: 8px;
}

.case-tree :deep(.el-tree-node__content:hover) {
  background: var(--secondary);
}
</style>
