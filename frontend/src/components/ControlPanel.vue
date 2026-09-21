<template>
  <div class="panel">
    <h2>控制面板</h2>

    <div class="row">
      <button class="primary" @click="$emit('toggle-polling')">
        {{ polling ? '停止轮询' : '开始轮询' }}
      </button>
      <button @click="$emit('refresh')">强制反演</button>
    </div>

    <label class="field">
      <span>轮询周期: {{ intervalMs / 1000 }} s</span>
      <input
        type="range"
        min="1000"
        max="15000"
        step="500"
        :value="intervalMs"
        @input="$emit('update:intervalMs', Number($event.target.value))"
      />
    </label>

    <label class="field">
      <span>正则化系数 λ: {{ lambda }}</span>
      <input
        type="range"
        min="-4"
        max="-1"
        step="0.1"
        :value="lambdaLog"
        @input="onLambda($event.target.value)"
      />
    </label>

    <div class="status">
      <div>状态: <b :class="{ ok: connected, bad: !connected }">{{ connected ? '已连接' : '未连接' }}</b></div>
      <div>最近更新: {{ lastUpdate || '—' }}</div>
      <div v-if="residual !== null">拟合残差: {{ (residual * 100).toFixed(2) }}%</div>
    </div>

    <div v-if="tcValues.length" class="tc">
      <h3>热电偶读数 (°C)</h3>
      <div class="tc-grid">
        <span v-for="(v, i) in tcValues" :key="i" class="tc-cell">#{{ i }} {{ v.toFixed(0) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  polling: Boolean,
  connected: Boolean,
  intervalMs: { type: Number, default: 3000 },
  lambda: { type: Number, default: 5e-3 },
  lastUpdate: { type: String, default: '' },
  residual: { type: Number, default: null },
  tcValues: { type: Array, default: () => [] },
})

const emit = defineEmits(['toggle-polling', 'refresh', 'update:intervalMs', 'update:lambda'])

const lambdaLog = computed(() => Math.log10(props.lambda))

function onLambda(v) {
  emit('update:lambda', Math.pow(10, Number(v)))
}
</script>

<style scoped>
.panel {
  background: #171c26;
  color: #dfe5ee;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-size: 14px;
}
h2 { margin: 0; font-size: 16px; }
h3 { margin: 0 0 6px; font-size: 13px; color: #9aa4b5; }
.row { display: flex; gap: 8px; }
button {
  background: #2a3345;
  color: #e8ecf3;
  border: 1px solid #3a465e;
  border-radius: 6px;
  padding: 8px 14px;
  cursor: pointer;
}
button.primary { background: #2563eb; border-color: #2563eb; }
button:hover { filter: brightness(1.15); }
.field { display: flex; flex-direction: column; gap: 4px; }
.status { display: flex; flex-direction: column; gap: 4px; color: #9aa4b5; }
.ok { color: #4ade80; }
.bad { color: #f87171; }
.tc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
  max-height: 180px;
  overflow-y: auto;
}
.tc-cell {
  background: #10141c;
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 12px;
  color: #b7c0cf;
}
</style>
