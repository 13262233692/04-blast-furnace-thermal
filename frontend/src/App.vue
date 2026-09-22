<template>
  <div class="layout">
    <header>
      <h2>高炉炉温场反演系统</h2>
      <span class="badge" :class="{ live: state.polling }">
        {{ state.polling ? '实时轮询中' : '已暂停' }}
      </span>
    </header>
    <main>
      <HeatmapView :field="field" :level="state.level" />
      <ControlPanel
        :state="state"
        :overview="overview"
        :last-update="state.lastUpdate"
        @update:level="setLevel"
        @update:interval="setIntervalMs"
        @togglePolling="setPolling(!state.polling)"
        @refresh="refreshNow"
        @paramsApplied="refreshNow"
      />
    </main>
  </div>
</template>

<script setup>
import HeatmapView from './components/HeatmapView.vue'
import ControlPanel from './components/ControlPanel.vue'
import { useDataPoller } from './composables/dataPoller'

const {
  field,
  overview,
  state,
  setLevel,
  setIntervalMs,
  setPolling,
  refreshNow,
} = useDataPoller()
</script>

<style>
body {
  margin: 0;
  background: #141414;
  font-family: 'Helvetica Neue', Arial, sans-serif;
}
.layout {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px;
}
header {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #eee;
}
.badge {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: #555;
}
.badge.live {
  background: #2e7d32;
}
main {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
main > :first-child {
  flex: 1;
}
</style>
