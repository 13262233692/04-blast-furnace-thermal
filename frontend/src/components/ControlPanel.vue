<script setup>
// 控制面板：轮询开关/间隔、正则化系数、缓存与增量更新统计、传感器状态。
import { computed, ref } from 'vue'
import { thermalState } from '../services/data_poller.js'

const props = defineProps({
  polling: { type: Boolean, required: true },
})
const emit = defineEmits(['toggle-polling', 'interval-change', 'lambda-change', 'refresh'])

const intervalMs = ref(5000)
const lambda = ref('')

const stats = computed(() => [
  { label: '请求次数', value: thermalState.requestCount },
  { label: '增量更新', value: thermalState.incrementalCount },
  { label: '缓存命中', value: thermalState.cacheHitCount },
  {
    label: '数据源',
    value: thermalState.sensors
      ? (thermalState.sensors.source === 'mock' ? '模拟器' : 'InfluxDB')
      : '-',
  },
  {
    label: '矩阵缓存',
    value: thermalState.cacheStats
      ? (thermalState.cacheStats.matrices_cached ? '已建立' : '未建立')
      : '-',
  },
  {
    label: '最后更新',
    value: thermalState.lastUpdateAt
      ? new Date(thermalState.lastUpdateAt).toLocaleTimeString()
      : '-',
  },
])

const changedSensors = computed(() => thermalState.field?.changed_sensors?.length ?? 0)

function onInterval() {
  emit('interval-change', Number(intervalMs.value))
}
function onLambda() {
  emit('lambda-change', lambda.value === '' ? null : Number(lambda.value))
}
</script>

<template>
  <div class="panel">
    <h3>控制面板</h3>

    <div class="row">
      <button :class="['btn', polling ? 'stop' : 'start']" @click="emit('toggle-polling')">
        {{ polling ? '停止轮询' : '开始轮询' }}
      </button>
      <button class="btn" @click="emit('refresh')">立即刷新</button>
    </div>

    <label class="field">
      <span>轮询间隔 (ms)</span>
      <input type="number" v-model="intervalMs" min="1000" step="500" @change="onInterval" />
    </label>

    <label class="field">
      <span>正则化系数 λ（留空用默认）</span>
      <input type="number" v-model="lambda" placeholder="默认 0.001" step="0.0001" @change="onLambda" />
    </label>

    <div class="stats">
      <div v-for="s in stats" :key="s.label" class="stat">
        <span class="label">{{ s.label }}</span>
        <span class="value">{{ s.value }}</span>
      </div>
      <div class="stat">
        <span class="label">本帧变化测点</span>
        <span class="value">{{ changedSensors }} / 32</span>
      </div>
    </div>

    <div v-if="thermalState.lastError" class="error">
      请求失败：{{ thermalState.lastError }}
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: #182034;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
h3 { margin: 0; font-size: 15px; color: #9db4dd; }
.row { display: flex; gap: 8px; }
.btn {
  flex: 1;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: #2a3a5f;
  color: #dbe2ef;
  cursor: pointer;
  font-size: 13px;
}
.btn:hover { filter: brightness(1.2); }
.btn.start { background: #1f7a4d; }
.btn.stop { background: #a03a3a; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #8fa3c8; }
.field input {
  background: #0f1420;
  border: 1px solid #2a3a5f;
  border-radius: 6px;
  color: #dbe2ef;
  padding: 6px 8px;
}
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stat {
  background: #0f1420;
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.label { font-size: 11px; color: #8fa3c8; }
.value { font-size: 14px; font-weight: 600; }
.error { color: #ff7b7b; font-size: 12px; }
</style>
