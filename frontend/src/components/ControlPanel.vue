<template>
  <div class="panel">
    <h3>控制面板</h3>

    <div class="group">
      <label>截面层</label>
      <div class="level-btns">
        <button
          v-for="lv in 4"
          :key="lv"
          :class="{ active: state.level === lv - 1 }"
          @click="('update:level', lv - 1)"
        >
          第{{ lv }}层
        </button>
      </div>
    </div>

    <div class="group">
      <label>轮询间隔: {{ state.intervalMs / 1000 }}s</label>
      <input
        type="range"
        min="1000"
        max="10000"
        step="1000"
        :value="state.intervalMs"
        @input="$emit('update:interval', Number($event.target.value))"
      />
    </div>

    <div class="group row">
      <button @click="('togglePolling')">
        {{ state.polling ? '暂停轮询' : '恢复轮询' }}
      </button>
      <button @click="('refresh')">立即刷新</button>
    </div>

    <div class="group">
      <label>平滑正则化 λ</label>
      <input type="number" v-model.number="regLambda" step="0.001" min="0.0001" />
      <label>时序正则化 μ</label>
      <input type="number" v-model.number="regMu" step="0.01" min="0" />
      <button @click="applyParams">应用参数</button>
    </div>

    <div class="group stats" v-if="overview">
      <p>数据源: {{ overview.data_source === 'mock' ? '模拟数据' : 'InfluxDB' }}</p>
      <p>数据版本: {{ lastUpdate || '-' }}</p>
      <p v-for="lv in overview.levels" :key="lv.level">
        第{{ lv.level + 1 }}层 内壁均温 {{ lv.inner_avg.toFixed(0) }}°C
        / 峰值 {{ lv.inner_max.toFixed(0) }}°C
        / 残差 {{ lv.residual.toFixed(2) }}
      </p>
    </div>

    <div class="group" v-if="overview && overview.sensor_values">
      <label>热电偶读数 (第{{ state.level + 1 }}层, °C)</label>
      <div class="sensor-bars">
        <div
          v-for="(v, i) in overview.sensor_values[state.level]"
          :key="i"
          class="sensor-bar"
        >
          <div class="bar" :style="{ height: barHeight(v) }"></div>
          <span>{{ i + 1 }}</span>
        </div>
      </div>
    </div>

    <p v-if="state.error" class="error">{{ state.error }}</p>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { updateRegParams } from '../api/client'

const props = defineProps({
  state: { type: Object, required: true },
  overview: { type: Object, default: null },
  lastUpdate: { type: String, default: '' },
})

const emit = defineEmits([
  'update:level',
  'update:interval',
  'togglePolling',
  'refresh',
  'paramsApplied',
])

const regLambda = ref(0.005)
const regMu = ref(0.02)

watch(
  function () { return props.overview },
  function (ov) {
    if (ov) {
      regLambda.value = ov.reg_lambda
      regMu.value = ov.reg_mu
    }
  }
)

async function applyParams() {
  await updateRegParams(regLambda.value, regMu.value)
  emit('paramsApplied')
}

function barHeight(v) {
  const min = 200
  const max = 500
  const pct = Math.max(0, Math.min(1, (v - min) / (max - min)))
  return Math.round(10 + pct * 50) + 'px'
}
</script>

<style scoped>
.panel {
  width: 300px;
  padding: 16px;
  background: #1d1d1d;
  color: #ddd;
  border-radius: 8px;
  font-size: 13px;
}
.group {
  margin-bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.group.row {
  flex-direction: row;
}
label {
  color: #999;
}
button {
  background: #2f6fb2;
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 6px 10px;
  cursor: pointer;
}
button.active {
  background: #d9534f;
}
.level-btns {
  display: flex;
  gap: 6px;
}
input[type='number'] {
  background: #111;
  color: #ddd;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 4px 6px;
}
.stats p {
  margin: 2px 0;
}
.sensor-bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 70px;
}
.sensor-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.sensor-bar .bar {
  width: 14px;
  background: linear-gradient(#d9534f, #e8c14a);
  border-radius: 2px;
}
.error {
  color: #ff7b72;
}
</style>
