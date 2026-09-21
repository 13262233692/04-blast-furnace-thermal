<template>
  <div class="layout">
    <header>
      <h1>高炉炉温场反演系统</h1>
      <span class="tag">FEM 反演 · InfluxDB · ECharts</span>
    </header>
    <main>
      <section class="chart-wrap">
        <HeatmapView :payload="payload" />
      </section>
      <aside>
        <ControlPanel
          :polling="polling"
          :connected="connected"
          :intervalMs="intervalMs"
          :lambda="lambda"
          :last-update="lastUpdate"
          :residual="residual"
          :tc-values="tcValues"
          @toggle-polling="togglePolling"
          @refresh="forceRefresh"
          @update:intervalMs="onInterval"
          @update:lambda="onLambda"
        />
      </aside>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import HeatmapView from './components/HeatmapView.vue'
import ControlPanel from './components/ControlPanel.vue'
import { DataPoller } from './services/data_poller'
import { refreshInversion } from './api/client'

const payload = ref(null)
const polling = ref(false)
const connected = ref(false)
const intervalMs = ref(3000)
const lambda = ref(5e-3)
const lastUpdate = ref('')
const residual = ref(null)
const tcValues = ref([])

const poller = new DataPoller({ interval: intervalMs.value })

poller.onUpdate((data) => {
  payload.value = data
  connected.value = true
  residual.value = data.residual ?? null
  tcValues.value = data.tc_values ?? []
  lastUpdate.value = new Date(data.timestamp * 1000).toLocaleTimeString()
})

poller.onError(() => {
  connected.value = false
})

function togglePolling() {
  if (poller.running) {
    poller.stop()
    polling.value = false
  } else {
    poller.start()
    polling.value = true
  }
}

async function forceRefresh() {
  try {
    const data = await refreshInversion(lambda.value)
    payload.value = data
    connected.value = true
    residual.value = data.residual ?? null
    tcValues.value = data.tc_values ?? []
    lastUpdate.value = new Date(data.timestamp * 1000).toLocaleTimeString()
    poller.lastTimestamp = data.timestamp
  } catch {
    connected.value = false
  }
}

function onInterval(ms) {
  intervalMs.value = ms
  poller.setInterval(ms)
}

function onLambda(v) {
  lambda.value = v
}

onMounted(() => {
  poller.start()
  polling.value = true
})

onBeforeUnmount(() => poller.stop())
</script>

<style>
body {
  margin: 0;
  background: #0b0e14;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
}
.layout { padding: 16px 20px; }
header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  color: #e8ecf3;
}
header h1 { font-size: 20px; margin: 0 0 12px; }
header .tag { color: #7c8aa5; font-size: 13px; }
main {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 16px;
}
.chart-wrap {
  background: #10141c;
  border-radius: 10px;
  min-height: 600px;
}
@media (max-width: 900px) {
  main { grid-template-columns: 1fr; }
}
</style>
