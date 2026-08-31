<template>
  <div class="case-table-wrap">
    <el-empty v-if="!rows.length" description="暂无用例数据" :image-size="50" />
    <el-table v-else :data="rows" size="small" border :max-height="420" class="case-table">
      <el-table-column label="用例 ID" prop="id" width="120" fixed />
      <el-table-column label="标题" prop="title" min-width="180" show-overflow-tooltip />
      <el-table-column label="优先级" width="80">
        <template #default="{ row }">
          <span class="pill" :class="priorityClass(row.priority)">{{ row.priority || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联接口" prop="api" min-width="140" show-overflow-tooltip />
      <el-table-column label="前置条件" prop="precondition" min-width="120" show-overflow-tooltip />
      <el-table-column label="步骤" min-width="200">
        <template #default="{ row }">
          <ol class="steps-list">
            <li v-for="(s, i) in row.steps || []" :key="i">{{ s }}</li>
          </ol>
        </template>
      </el-table-column>
      <el-table-column label="预期" min-width="200">
        <template #default="{ row }">
          <ul class="expects-list">
            <li v-for="(e, i) in row.expects || []" :key="i">{{ e }}</li>
          </ul>
        </template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" min-width="100" show-overflow-tooltip />
    </el-table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 用例树对象：{groups:[{name,cases:[...]}]} */
  tree: { type: Object, default: () => ({}) }
})

const rows = computed(() => {
  const t = props.tree || {}
  const groups = Array.isArray(t.groups) ? t.groups : []
  const out = []
  groups.forEach((g) => {
    ;(Array.isArray(g.cases) ? g.cases : []).forEach((c) => {
      out.push({ ...c, group: g.name })
    })
  })
  return out
})

function priorityClass(p) {
  const s = String(p || '')
  if (s.includes('高')) return 'pill-danger'
  if (s.includes('中')) return 'pill'
  return 'pill-success'
}
</script>

<style scoped>
.steps-list,
.expects-list {
  margin: 0;
  padding-left: 16px;
}

.steps-list li,
.expects-list li {
  font-size: 12px;
  color: var(--text);
  line-height: 1.6;
}
</style>
