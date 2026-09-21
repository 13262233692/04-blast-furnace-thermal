<template>
  <div class="app">
    <header class="header">
      <h1>高炉炉温场反演系统</h1>
      <span class="subtitle">32 热电偶 · FEM 反演 · InfluxDB · 增量更新</span>
    </header>
    <main class="main">
      <ControlPanel
        :state="poller.state"
        :running="poller.running.value"
        :loading="poller.loading.value"
        :error="poller.error.value"
        :poll-interval="poller.pollInterval.value"
        @start="poller.start"
        @stop="poller.stop"
        @refresh="poller.refresh"
        @interval="poller.setIntervalMs"
      />
      <div class="chart-area">
        <HeatmapView v-if="poller.state.field" :field="poller.state.field" />
        <div v-else class="placeholder">
          {{ poller.error.value || '等待数据… 请确认后端已启动（uvicorn main:app --port 8000）' }}
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import ControlPanel from './components/control_panel.vue'
import HeatmapView from './components/heatmap_view.vue'
import { useDataPoller } from './composables/data_poller'

const poller = useDataPoller({ intervalMs: 2000 })

onMounted(() => poller.start())
onBeforeUnmount(() => poller.stop())
</script>

<style>
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: #0d1424;
  font-family: 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.header {
  padding: 14px 24px;
  background: #101a30;
  border-bottom: 1px solid #22304d;
  display: flex;
  align-items: baseline;
  gap: 14px;
}
.header h1 {
  margin: 0;
  font-size: 19px;
  color: #dfe6f3;
}
.subtitle {
  color: #8fa1c0;
  font-size: 12px;
}
.main {
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 16px 24px;
}
.chart-area {
  flex: 1;
  background: #141d33;
  border-radius: 10px;
  padding: 8px;
  min-height: 560px;
  display: flex;
}
.placeholder {
  margin: auto;
  color: #8fa1c0;
}
</style>
