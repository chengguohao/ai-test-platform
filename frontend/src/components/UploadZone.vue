<template>
  <div
    class="upload-zone"
    :class="{ dragging }"
    @click="pick"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="input"
      type="file"
      class="hidden-input"
      :accept="accept"
      @change="onInputChange"
    />
    <div v-if="!file" class="upload-placeholder">
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <span class="upload-text">{{ placeholder || '点击或拖拽文件到此处上传' }}</span>
      <span v-if="acceptHint" class="upload-hint">{{ acceptHint }}</span>
    </div>
    <div v-else class="upload-file">
      <el-icon><Document /></el-icon>
      <span class="file-name">{{ file.name }}</span>
      <el-icon class="file-clear" @click.stop="clear"><Close /></el-icon>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  placeholder: { type: String, default: '' },
  accept: { type: String, default: '' },
  acceptHint: { type: String, default: '' }
})

const emit = defineEmits(['change', 'clear'])

const input = ref(null)
const file = ref(null)
const dragging = ref(false)

function pick() {
  input.value?.click()
}

function onInputChange(e) {
  const f = e.target.files?.[0]
  if (f) setFile(f)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) setFile(f)
}

function setFile(f) {
  file.value = f
  emit('change', f)
}

function clear() {
  file.value = null
  emit('clear')
}

defineExpose({ clear, file })
</script>

<style scoped>
.upload-zone {
  border: 1.5px dashed var(--border);
  border-radius: var(--radius-control);
  background: var(--card);
  padding: 18px 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
  min-height: 64px;
}

.upload-zone:hover,
.upload-zone.dragging {
  border-color: var(--primary);
  background: var(--primary-light);
}

.hidden-input {
  display: none;
}

.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
}

.upload-icon {
  font-size: 22px;
  color: var(--primary);
}

.upload-text {
  font-size: 13px;
}

.upload-hint {
  font-size: 12px;
  opacity: 0.7;
}

.upload-file {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
  font-size: 13px;
  max-width: 100%;
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}

.file-clear {
  color: var(--text-secondary);
  cursor: pointer;
}

.file-clear:hover {
  color: var(--danger);
}
</style>
