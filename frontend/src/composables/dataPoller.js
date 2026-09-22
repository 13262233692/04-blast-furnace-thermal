import { onBeforeUnmount, reactive, ref } from 'vue'
import { fetchField, fetchOverview } from '../api/client'

/**
 * 数据轮询 composable。
 *
 * 增量更新: 每次请求携带已持有数据的 timestamp 作为 since，
 * 服务端返回 updated=false 时跳过重渲染，避免无效刷新。
 */
export function useDataPoller() {
  const field = ref(null)          // 当前层温度场
  const overview = ref(null)       // 各层统计与传感器读数
  const state = reactive({
    level: 0,
    intervalMs: 3000,
    timestamp: 0,
    lastUpdate: '',
    error: '',
    polling: true,
  })

  let timer = null
  let fetching = false

  async function pollOnce() {
    if (fetching) return
    fetching = true
    try {
      const resp = await fetchField(state.level, state.timestamp)
      if (resp.updated) {
        field.value = resp
        state.timestamp = resp.timestamp
        state.lastUpdate = new Date(resp.timestamp * 1000).toLocaleTimeString()
      }
      overview.value = await fetchOverview()
      state.error = ''
    } catch (err) {
      state.error = err.message || String(err)
    } finally {
      fetching = false
    }
  }

  function restart() {
    stop()
    if (state.polling) {
      timer = setInterval(pollOnce, state.intervalMs)
    }
  }

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function setLevel(level) {
    state.level = level
    state.timestamp = 0  // 切换层时强制全量拉取
    pollOnce()
  }

  function setIntervalMs(ms) {
    state.intervalMs = ms
    restart()
  }

  function setPolling(on) {
    state.polling = on
    restart()
  }

  async function refreshNow() {
    await pollOnce()
  }

  pollOnce()
  restart()
  onBeforeUnmount(stop)

  return {
    field,
    overview,
    state,
    setLevel,
    setIntervalMs,
    setPolling,
    refreshNow,
  }
}
