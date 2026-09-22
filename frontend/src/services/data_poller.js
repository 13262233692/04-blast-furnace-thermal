// 数据轮询服务：定时拉取反演结果，支持增量标记、错误退避与手动刷新。
import { reactive } from 'vue'

export const thermalState = reactive({
  field: null,          // 最近一次 /api/thermal-field 响应
  sensors: null,        // 最近一次 /api/sensors/latest 响应
  cacheStats: null,     // /api/cache/stats
  polling: false,
  lastError: null,
  lastUpdateAt: null,   // Date.now()
  requestCount: 0,
  incrementalCount: 0,
  cacheHitCount: 0,
})

export class DataPoller {
  constructor({ intervalMs = 5000, baseUrl = '' } = {}) {
    this.baseUrl = baseUrl
    this.intervalMs = intervalMs
    this._timer = null
    this._failCount = 0
    this._inflight = false
  }

  async _get(path) {
    const resp = await fetch(`${this.baseUrl}${path}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status} ${path}`)
    return resp.json()
  }

  async pollOnce(lambda = null) {
    if (this._inflight) return
    this._inflight = true
    try {
      const query = lambda ? `?lam=${lambda}` : ''
      const [field, sensors, stats] = await Promise.all([
        this._get(`/api/thermal-field${query}`),
        this._get('/api/sensors/latest'),
        this._get('/api/cache/stats'),
      ])
      thermalState.field = field
      thermalState.sensors = sensors
      thermalState.cacheStats = stats
      thermalState.lastError = null
      thermalState.lastUpdateAt = Date.now()
      thermalState.requestCount += 1
      if (field.incremental) thermalState.incrementalCount += 1
      if (field.cache_hit) thermalState.cacheHitCount += 1
      this._failCount = 0
    } catch (err) {
      thermalState.lastError = String(err)
      this._failCount += 1
    } finally {
      this._inflight = false
    }
  }

  start(getLambda = () => null) {
    if (this._timer) return
    thermalState.polling = true
    const tick = async () => {
      await this.pollOnce(getLambda())
      // 指数退避：连续失败时拉长间隔，最多 10 倍
      const backoff = Math.min(2 ** this._failCount, 10)
      this._timer = setTimeout(tick, this.intervalMs * backoff)
    }
    tick()
  }

  stop() {
    thermalState.polling = false
    if (this._timer) {
      clearTimeout(this._timer)
      this._timer = null
    }
  }

  setIntervalMs(ms) {
    this.intervalMs = ms
    if (this._timer) {
      const wasRunning = true
      this.stop()
      if (wasRunning) this.start()
    }
  }
}
