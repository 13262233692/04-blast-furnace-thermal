/**
 * data_poller —— 反演结果轮询与增量同步。
 *
 * 增量更新协议：
 *   每次请求携带本地已持有的 version 作为 since_version；
 *   服务端版本未变时返回 { updated: false } 轻量响应，
 *   仅当 updated=true 时才替换温度场数据并触发视图更新。
 */
import { reactive, ref } from 'vue'

export function useDataPoller({ intervalMs = 2000 } = {}) {
  const running = ref(false)
  const loading = ref(false)
  const error = ref(null)
  const pollInterval = ref(intervalMs)

  const state = reactive({
    version: 0,          // 本地持有的反演结果版本
    field: null,         // 温度场网格数据（updated=true 时更新）
    timestamp: 0,        // 传感器数据时间戳
    source: '-',         // influxdb / mock
    cache: null,         // 服务端缓存统计
    lastUpdate: null,    // 最近一次收到新数据的时刻
    pollCount: 0,        // 轮询次数
    skipCount: 0,        // 增量跳过次数（updated=false）
  })

  let timer = null

  async function pollOnce() {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/thermal/field?since_version=${state.version}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      state.pollCount += 1
      state.cache = data.cache
      if (data.updated) {
        // 服务端有新版本：全量替换温度场
        state.version = data.version
        state.field = data.field
        state.timestamp = data.timestamp
        state.source = data.source
        state.lastUpdate = new Date()
      } else {
        // 版本未变：增量跳过，不触动温度场数据
        state.skipCount += 1
      }
    } catch (e) {
      error.value = `后端连接失败: ${e.message}`
    } finally {
      loading.value = false
    }
  }

  function start() {
    if (running.value) return
    running.value = true
    pollOnce()
    timer = setInterval(pollOnce, pollInterval.value)
  }

  function stop() {
    running.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function setIntervalMs(ms) {
    pollInterval.value = ms
    if (running.value) {
      stop()
      start()
    }
  }

  return {
    state,
    running,
    loading,
    error,
    pollInterval,
    start,
    stop,
    refresh: pollOnce,
    setIntervalMs,
  }
}
