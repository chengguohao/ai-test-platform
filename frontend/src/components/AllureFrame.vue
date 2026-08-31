<template>
  <div class="allure-frame">
    <div v-if="!src" class="allure-empty muted">暂无 Allure 报告地址</div>
    <iframe
      v-else
      :src="src"
      class="allure-iframe"
      frameborder="0"
      @load="loaded = true"
    />
    <div v-if="src && !loaded" class="allure-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>报告加载中…</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  /** iframe 地址（/reports/... 经 vite 代理） */
  src: { type: String, default: '' }
})

const loaded = ref(false)
watch(
  () => props.src,
  () => {
    loaded.value = false
  }
)
</script>

<style scoped>
.allure-frame {
  position: relative;
  width: 100%;
  height: 560px;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: hidden;
  background: var(--card);
}

.allure-iframe {
  width: 100%;
  height: 100%;
  display: block;
}

.allure-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 13px;
}

.allure-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--card);
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
