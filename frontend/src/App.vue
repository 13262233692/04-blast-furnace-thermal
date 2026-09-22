<script setup>
// 高炉炉温场反演系统主界面。
import { onBeforeUnmount, ref } from 'vue'
import HeatmapView from './components/HeatmapView.vue'
import ControlPanel from './components/ControlPanel.vue'
import { DataPoller, thermalState } from './services/data_poller.js'

const poller = new DataPoller({ intervalMs: 5000 })
const polling = ref(false)
const lambda = ref(null)

function togglePolling() {
  if (polling.value) {
    poller.stop()
    polling.value = false
  } else {
    poller.start(() => lambda.value)
    polling.value = true
  }
}
function onIntervalChange(ms) {
  poller.setIntervalMs(ms)
}
function onLambdaChange(v) {
  lambda.value = v
  poller.pollOnce(lambda.value)
}
function refresh() {
  poller.pollOnce(lambda.value)
}

// 启动即拉一帧，便于首屏渲染
poller.pollOnce()

onBeforeUnmount(() => poller.stop())
</script>

<template>
  <div class="layout">
    <header>
      <h1>高炉炉温场反演系统</h1>
      <span class="badge" :class="{ live: polling }">
        {{ polling ? '实时轮询中' : '已暂停' }}
      </span>
    </header>
    <main>
      <section class="chart-area">
        <HeatmapView v-if="thermalState.field" />
        <div v-else class="placeholder">正在加载反演数据…</div>
      </section>
      <aside>
        <ControlPanel
          :polling="polling"
          @toggle-polling="togglePolling"
          @interval-change="onIntervalChange"
          @lambda-change="onLambdaChange"
          @refresh="refresh"
        />
      </aside>
    </main>
  </div>
</template>

<style scoped>
.layout { padding: 16px 24px; max-width: 1400px; margin: 0 auto; }
header { display: flex; align-items: center; gap: 12px; }
h1 { font-size: 20px; margin: 8px 0; }
.badge {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  background: #3a3f55;
}
.badge.live { background: #1f7a4d; }
main { display: grid; grid-template-columns: 1fr 300px; gap: 16px; margin-top: 8px; }
.chart-area {
  background: #141a2b;
  border-radius: 10px;
  min-height: 560px;
  display: flex;
}
.placeholder { margin: auto; color: #8fa3c8; }
@media (max-width: 960px) {
  main { grid-template-columns: 1fr; }
}
</style>
