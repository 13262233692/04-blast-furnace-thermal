<template>
  <div class="heatmap-wrapper">
    <div ref="chartEl" class="heatmap-chart"></div>
    <div v-if="!field" class="heatmap-empty">等待数据...</div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  field: { type: Object, default: null },
  level: { type: Number, default: 0 },
})

const chartEl = ref(null)
let chart = null

const GRID_N = 120 // 笛卡尔重采样分辨率

/** 将极坐标温度场双线性插值到笛卡尔网格，生成环形截面热力数据。 */
function resample(fieldData) {
  const rArr = fieldData.r
  const thArr = fieldData.theta
  const values = fieldData.field
  const nr = rArr.length - 1
  const nt = thArr.length
  const rIn = rArr[0]
  const rOut = rArr[nr]
  const dr = (rOut - rIn) / nr
  const dth = (2 * Math.PI) / nt

  const data = []
  let vMin = Infinity
  let vMax = -Infinity
  const step = (2 * rOut) / GRID_N
  for (let ix = 0; ix < GRID_N; ix++) {
    const x = -rOut + (ix + 0.5) * step
    for (let iy = 0; iy < GRID_N; iy++) {
      const y = -rOut + (iy + 0.5) * step
      const rr = Math.sqrt(x * x + y * y)
      if (rr < rIn || rr > rOut) continue
      let th = Math.atan2(y, x)
      if (th < 0) th += 2 * Math.PI
      const fi = Math.min((rr - rIn) / dr, nr - 1e-9)
      const fj = (th / dth) % nt
      const i0 = Math.floor(fi)
      const j0 = Math.floor(fj)
      const fr = fi - i0
      const ft = fj - j0
      const j1 = (j0 + 1) % nt
      const v =
        values[i0][j0] * (1 - fr) * (1 - ft) +
        values[i0][j1] * (1 - fr) * ft +
        values[i0 + 1][j0] * fr * (1 - ft) +
        values[i0 + 1][j1] * fr * ft
      data.push([ix, iy, Math.round(v * 10) / 10])
      if (v < vMin) vMin = v
      if (v > vMax) vMax = v
    }
  }
  return { data, vMin, vMax, step, rOut }
}

/** 热电偶标记点(周向 8 支，埋于炉壁内)。 */
function sensorMarkers(fieldData, step, rOut) {
  const rArr = fieldData.r
  const rIn = rArr[0]
  const rS = rIn + 0.7 * (rArr[rArr.length - 1] - rIn)
  const fit = fieldData.sensor_fit || []
  const pts = []
  for (let s = 0; s < 8; s++) {
    const th = (s * 2 * Math.PI) / 8
    const x = rS * Math.cos(th)
    const y = rS * Math.sin(th)
    const ix = (x + rOut) / step - 0.5
    const iy = (y + rOut) / step - 0.5
    pts.push({ value: [ix, iy], temp: fit[s] != null ? fit[s].toFixed(1) : '-' })
  }
  return pts
}

function render() {
  if (!chart || !props.field || !props.field.field) return
  const { data, vMin, vMax, step, rOut } = resample(props.field)
  const sensors = sensorMarkers(props.field, step, rOut)
  const cats = Array.from({ length: GRID_N }, function (_, i) { return i })

  chart.setOption(
    {
      title: {
        text: '第 ' + (props.level + 1) + ' 层截面温度场',
        left: 'center',
        textStyle: { color: '#ddd', fontSize: 14 },
      },
      tooltip: {
        formatter: function (p) {
          if (p.seriesType === 'scatter') {
            return '热电偶: ' + p.data.temp + ' °C'
          }
          return '温度: ' + p.value[2] + ' °C'
        },
      },
      grid: { left: 30, right: 30, top: 40, bottom: 60 },
      xAxis: { type: 'category', data: cats, show: false },
      yAxis: { type: 'category', data: cats, show: false },
      visualMap: {
        min: Math.floor(vMin),
        max: Math.ceil(vMax),
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 5,
        textStyle: { color: '#ccc' },
        inRange: {
          color: ['#2b5c9e', '#3fa7a3', '#e8c14a', '#d9534f', '#7e1e1e'],
        },
      },
      series: [
        {
          type: 'heatmap',
          data: data,
          blur: 0.9,
          pointSize: 6,
          progressive: 4000,
        },
        {
          type: 'scatter',
          data: sensors,
          symbolSize: 9,
          itemStyle: { color: '#fff', borderColor: '#222', borderWidth: 1 },
          z: 10,
        },
      ],
    },
    { notMerge: true }
  )
}

onMounted(function () {
  chart = echarts.init(chartEl.value, 'dark')
  render()
  window.addEventListener('resize', resize)
})

function resize() {
  if (chart) chart.resize()
}

onBeforeUnmount(function () {
  window.removeEventListener('resize', resize)
  if (chart) chart.dispose()
})

watch(function () { return props.field }, render, { deep: false })
</script>

<style scoped>
.heatmap-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.heatmap-chart {
  width: 100%;
  height: 100%;
  min-height: 480px;
}
.heatmap-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #888;
}
</style>
