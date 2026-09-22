<script setup>
// 炉温场热力图：ECharts heatmap 渲染反演温度场，叠加热电偶测点。
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { thermalState } from '../services/data_poller.js'

const chartEl = ref(null)
let chart = null

function buildOption(field, cacheStats) {
  const { r_coords, z_coords, temperature } = field
  // temperature[iz][ir] -> heatmap 数据 [zIdx, rIdx, value]
  const data = []
  for (let iz = 0; iz < z_coords.length; iz++) {
    for (let ir = 0; ir < r_coords.length; ir++) {
      data.push([iz, ir, temperature[iz][ir]])
    }
  }
  const tMin = Math.min(...data.map(d => d[2]))
  const tMax = Math.max(...data.map(d => d[2]))

  // 热电偶测点散点（坐标映射到类目轴索引）
  const tcPoints = []
  if (cacheStats && cacheStats.tc_positions) {
    for (const [r, z] of cacheStats.tc_positions) {
      const zi = z_coords.findIndex(v => v >= z)
      const ri = r_coords.findIndex(v => v >= r)
      tcPoints.push([Math.max(zi, 0), Math.max(ri, 0)])
    }
  }

  return {
    backgroundColor: 'transparent',
    title: {
      text: '炉壁横截面温度场（反演）',
      subtext: `热面温度 ${Math.min(...field.hot_face_temp).toFixed(0)} ~ ${Math.max(...field.hot_face_temp).toFixed(0)} °C` +
        `  |  求解 ${field.solve_ms} ms` +
        (field.cache_hit ? '  |  缓存命中' : field.incremental ? '  |  增量更新' : '  |  全量反演'),
      left: 'center',
      textStyle: { color: '#dbe2ef', fontSize: 15 },
      subtextStyle: { color: '#8fa3c8' },
    },
    grid: { left: 90, right: 110, top: 80, bottom: 60 },
    tooltip: {
      formatter: p => p.seriesType === 'heatmap'
        ? `高度 ${z_coords[p.value[0]].toFixed(2)} m<br/>壁深 ${r_coords[p.value[1]].toFixed(2)} m<br/>温度 ${p.value[2].toFixed(1)} °C`
        : '热电偶测点',
    },
    xAxis: {
      type: 'category',
      name: '高度 z (m)',
      data: z_coords.map(v => v.toFixed(2)),
      axisLabel: { color: '#8fa3c8', interval: 5 },
      nameTextStyle: { color: '#8fa3c8' },
    },
    yAxis: {
      type: 'category',
      name: '壁深 r (m)',
      data: r_coords.map(v => v.toFixed(2)),
      axisLabel: { color: '#8fa3c8' },
      nameTextStyle: { color: '#8fa3c8' },
    },
    visualMap: {
      min: Math.floor(tMin),
      max: Math.ceil(tMax),
      calculable: true,
      orient: 'vertical',
      right: 10,
      top: 'center',
      text: ['°C'],
      textStyle: { color: '#8fa3c8' },
      inRange: {
        color: ['#1a2f6b', '#2060a8', '#2fa3c7', '#5ec962', '#fde725', '#f98e09', '#d93829'],
      },
    },
    series: [
      {
        type: 'heatmap',
        data,
        emphasis: { itemStyle: { borderColor: '#fff', borderWidth: 1 } },
        progressive: 2000,
      },
      {
        type: 'scatter',
        symbol: 'pin',
        symbolSize: 8,
        itemStyle: { color: '#ffffff', opacity: 0.7 },
        data: tcPoints,
        z: 5,
      },
    ],
  }
}

function render() {
  if (!chart || !thermalState.field) return
  chart.setOption(buildOption(thermalState.field, thermalState.cacheStats), {
    notMerge: true,
  })
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  render()
  window.addEventListener('resize', resize)
  watch(() => thermalState.field, render)
})

function resize() { chart && chart.resize() }

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
})
</script>

<template>
  <div ref="chartEl" class="heatmap"></div>
</template>

<style scoped>
.heatmap {
  width: 100%;
  height: 100%;
  min-height: 520px;
}
</style>
