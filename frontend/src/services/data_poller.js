/**
 * Polls the inversion API on an interval and emits incremental updates.
 *
 * The poller tracks the newest timestamp it has seen and passes it as the
 * `since` parameter, so unchanged snapshots cost only a tiny response.
 */
import { fetchLatestInversion } from '../api/client'

export class DataPoller {
  constructor({ interval = 3000 } = {}) {
    this.interval = interval
    this.timer = null
    this.lastTimestamp = null
    this.listeners = new Set()
    this.errorListeners = new Set()
    this._inflight = false
  }

  onUpdate(fn) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  onError(fn) {
    this.errorListeners.add(fn)
    return () => this.errorListeners.delete(fn)
  }

  setInterval(ms) {
    this.interval = ms
    if (this.timer) {
      this.stop()
      this.start()
    }
  }

  async tick() {
    if (this._inflight) return
    this._inflight = true
    try {
      const data = await fetchLatestInversion(this.lastTimestamp)
      if (data.updated || data.field) {
        this.lastTimestamp = data.timestamp
        this.listeners.forEach((fn) => fn(data))
      }
    } catch (err) {
      this.errorListeners.forEach((fn) => fn(err))
    } finally {
      this._inflight = false
    }
  }

  start() {
    if (this.timer) return
    this.tick()
    this.timer = setInterval(() => this.tick(), this.interval)
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  get running() {
    return this.timer !== null
  }
}
