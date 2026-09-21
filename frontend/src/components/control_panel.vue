<template>
  <div class="control-panel">
    <h2>控制面板</h2>

    <div class="group">
      <div class="row">
        <button
          class="btn"
          :class="running ? 'btn-danger' : 'btn-primary'"
          @click="running ? $emit('stop') : $emit('start')"
        >
          {{ running ? '停止轮询' : '开始轮询' }}
        </button>
        <button class="btn" @click="$emit('refresh')" :disabled="loading">
          手动刷新
        </button>
      </div>
      <label class="slider-label">
        轮询周期：{{ (pollInterval / 1000).toFixed(1) }} s
        <input
          type="range"
          min="500"
          max="10000"
          step="500"
          :value="pollInterval"
          @input="$emit('interval', Number($event.target.value))"
        />
      </label>
    </div>

    <div class="group">
      <h3>数据源</h3>
      <div class="kv"><span>来源</span><b :class="sourceClass">{{ state.source }}</b></div>
      <div class="kv"><span>数据时间戳</span><b>{{ formattedTs }}</b></div>
      <div class="kv"><span>最近更新</span><b>{{ formattedUpdate }}</b></div>
    </div>

    <div class="group">
      <h3>缓存 / 增量更新</h3>
      <div class="kv"><span>结果版本</span><b>v{{ state.version }}</b></div>
      <div class="kv"><span>轮询次数</span><b>{{ state.pollCount }}</b></div>
      <div class="kv"><span>增量跳过</span><b>{{ state.skipCount }}</b></div>
      <template v-if="state.cache">
        <div class="kv"><span>缓存命中</span><b>{{ state.cache.cache_hits }}</b></div>
        <div class="kv"><span>真实重算</span><b>{{ state.cache.cache_misses }}</b></div>
        <div class="kv"><span>反演耗时</span><b>{{ state.cache.compute_ms }} ms</b></div>
      </template>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="running" class="status-ok">● 轮询中</div>
    <div v-else class="status-idle">○ 已停止</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: Object, required: true }, // data_poller 暴露的响应式状态
  running: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  pollInterval: { type: Number, default: 2000 },
})

defineEmits(['start', 'stop', 'refresh', 'interval'])

const formattedTs = computed(() =>
  props.state.timestamp ? new Date(props.state.timestamp * 1000).toLocaleTimeString() : '-',
)
const formattedUpdate = computed(() =>
  props.state.lastUpdate ? props.state.lastUpdate.toLocaleTimeString() : '-',
)
const sourceClass = computed(() => (props.state.source === 'mock' ? 'src-mock' : 'src-influx'))
</script>

<style scoped>
.control-panel {
  width: 260px;
  padding: 16px;
  background: #141d33;
  border-radius: 10px;
  color: #dfe6f3;
  font-size: 13px;
  flex-shrink: 0;
}
h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #8fa1c0;
}
.group {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #22304d;
}
.row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.btn {
  flex: 1;
  padding: 7px 0;
  border: none;
  border-radius: 6px;
  background: #2a3a5f;
  color: #dfe6f3;
  cursor: pointer;
}
.btn:hover {
  filter: brightness(1.2);
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.btn-primary {
  background: #2f6fdd;
}
.btn-danger {
  background: #c0392b;
}
.slider-label {
  display: block;
  color: #8fa1c0;
}
.slider-label input {
  width: 100%;
  margin-top: 6px;
}
.kv {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
}
.kv span {
  color: #8fa1c0;
}
.src-mock {
  color: #f6d55c;
}
.src-influx {
  color: #59c2a5;
}
.error {
  color: #ff6b6b;
}
.status-ok {
  color: #59c2a5;
}
.status-idle {
  color: #8fa1c0;
}
</style>
