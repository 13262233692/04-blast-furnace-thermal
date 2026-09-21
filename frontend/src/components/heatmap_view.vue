<template>
  <div class="heatmap-view">
    <div ref="heatmapEl" class="heatmap-chart"></div>
    <div ref="boundaryEl" class="boundary-chart"></div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  field: { type: Object, default: null }, // 反演温度场（InversionResult）
})

const heatmapEl = ref(null)
const boundaryEl = ref(null)
let heatmapChart = null
let boundaryChart = null

const N_SENSORS = 32

function buildHeatmapOption(field) {
  const { nx, ny, x_min, x_max, y_min, y_max, values, t_min, t_max, boundary_temps } = field
  const xCats = []
  const yCats = []
  for (let j = 0; j < nx; j++) xCats.push((x_min + ((x_max - x_min) * j) / (nx - 1)).toFixed(1))
  for (let i = 0; i < ny; i++) yCats.push((y_min + ((y_max - y_min) * i) / (ny - 1)).toFixed(1))

  // values 为行优先一维数组：values[i*nx + j] 对应 (x_j, y_i)
  const data = []
  for (let i = 0; i < ny; i++) {
    for (let j = 0; j < nx; j++) {
      const v = values[i * nx + j]
      if (v !== null && v !== undefined) data.push([j, i, v])
    }
  }

  // 32 支热电偶在炉壁圆周上的位置（散点覆盖层）。
  // 类目轴需使用索引坐标：物理坐标 -> 类目下标
  const radius = x_max
  const sensors = []
  for (let k = 0; k < N_SENSORS; k++) {
    const theta = (2 * Math.PI * k) / N_SENSORS
    const xIdx = ((radius * Math.cos(theta) - x_min) / (x_max - x_min)) * (nx - 1)
    const yIdx = ((radius * Math.sin(theta) - y_min) / (y_max - y_min)) * (ny - 1)
    sensors.push({
      value: [xIdx, yIdx],
      temp: boundary_temps[k],
      name: `TC${String(k).padStart(2, '0')}`,
    })
  }

  return {
    backgroundColor: 'transparent',
    title: {
      text: '炉内温度场反演（横截面）',
      subtext: `温度范围 ${t_min.toFixed(1)} ~ ${t_max.toFixed(1)} ℃`,
      left: 'center',
      textStyle: { color: '#dfe6f3', fontSize: 15 },
      subtextStyle: { color: '#8fa1c0' },
    },
    grid: { left: 60, right: 90, top: 60, bottom: 50 },
    xAxis: {
      type: 'category',
      data: xCats,
      name: 'x / m',
      axisLabel: { color: '#8fa1c0', interval: 9 },
      axisLine: { lineStyle: { color: '#3a4a6b' } },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: yCats,
      name: 'y / m',
      axisLabel: { color: '#8fa1c0', interval: 9 },
      axisLine: { lineStyle: { color: '#3a4a6b' } },
    },
    visualMap: {
      min: t_min,
      max: t_max,
      calculable: true,
      orient: 'vertical',
      right: 8,
      top: 'center',
      textStyle: { color: '#8fa1c0' },
      inRange: {
        color: ['#2c5aa0', '#3fa7d6', '#59c2a5', '#f6d55c', '#ed8936', '#d63031'],
      },
    },
    tooltip: {
      formatter: (p) => {
        if (p.seriesType === 'scatter') {
          return `${p.data.name}<br/>壁温: ${p.data.temp.toFixed(1)} ℃`
        }
        return `(${xCats[p.value[0]]}, ${yCats[p.value[1]]}) m<br/>温度: ${p.value[2].toFixed(1)} ℃`
      },
    },
    series: [
      {
        name: '温度场',
        type: 'heatmap',
        data,
        blur: 0.9,
        pointSize: 12,
        emphasis: { itemStyle: { borderColor: '#fff', borderWidth: 1 } },
      },
      {
        name: '热电偶',
        type: 'scatter',
        coordinateSystem: 'cartesian2d',
        data: sensors,
        symbolSize: 7,
        itemStyle: { color: '#ffffff', borderColor: '#222', borderWidth: 1 },
      },
    ],
  }
}

function buildBoundaryOption(field) {
  const temps = field.boundary_temps
  const labels = temps.map((_, k) => `TC${String(k).padStart(2, '0')}`)
  return {
    backgroundColor: 'transparent',
    title: {
      text: '炉壁 32 支热电偶实时读数',
      left: 'center',
      textStyle: { color: '#dfe6f3', fontSize: 13 },
    },
    grid: { left: 55, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { color: '#8fa1c0', interval: 3, fontSize: 9 },
      axisLine: { lineStyle: { color: '#3a4a6b' } },
    },
    yAxis: {
      type: 'value',
      name: '℃',
      axisLabel: { color: '#8fa1c0' },
      splitLine: { lineStyle: { color: '#22304d' } },
    },
    series: [
      {
        type: 'bar',
        data: temps,
        itemStyle: {
          color: (p) => {
            const ratio = (p.value - field.t_min) / Math.max(field.t_max - field.t_min, 1e-6)
            return ratio > 0.66 ? '#d63031' : ratio > 0.33 ? '#f6d55c' : '#3fa7d6'
          },
        },
        barWidth: '60%',
      },
    ],
  }
}

function render() {
  if (!props.field || !heatmapChart) return
  heatmapChart.setOption(buildHeatmapOption(props.field), { notMerge: true })
  boundaryChart.setOption(buildBoundaryOption(props.field), { notMerge: true })
}

const resizeHandler = () => {
  heatmapChart && heatmapChart.resize()
  boundaryChart && boundaryChart.resize()
}

onMounted(() => {
  heatmapChart = echarts.init(heatmapEl.value, null, { renderer: 'canvas' })
  boundaryChart = echarts.init(boundaryEl.value, null, { renderer: 'canvas' })
  window.addEventListener('resize', resizeHandler)
  render()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeHandler)
  heatmapChart && heatmapChart.dispose()
  boundaryChart && boundaryChart.dispose()
})

// 仅在 field 引用变化（即服务端 updated=true）时重绘，实现增量更新
watch(() => props.field, render)
</script>

<style scoped>
.heatmap-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 8px;
}
.heatmap-chart {
  flex: 3;
  min-height: 380px;
}
.boundary-chart {
  flex: 1;
  min-height: 160px;
}
</style>
