<template>
  <div ref="chartEl" class="heatmap"></div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  payload: { type: Object, default: null },
})

const chartEl = ref(null)
let chart = null

function toHeatmapData(payload) {
  const { x, y, field } = payload
  const data = []
  for (let iy = 0; iy < y.length; iy++) {
    for (let ix = 0; ix < x.length; ix++) {
      const v = field[iy][ix]
      if (v !== null && v !== undefined) {
        data.push([x[ix], y[iy], v])
      }
    }
  }
  return data
}

function tcScatter(payload) {
  const r = 5.1 // thermocouple embedment radius (matches backend config)
  return payload.tc_theta.map((theta, i) => ({
    value: [r * Math.cos(theta), r * Math.sin(theta), payload.tc_values[i]],
  }))
}

function render(payload) {
  if (!chart || !payload || !payload.field) return
  const heat = toHeatmapData(payload)
  const values = heat.map((d) => d[2])
  const min = Math.floor(Math.min(...values) / 10) * 10
  const max = Math.ceil(Math.max(...values) / 10) * 10
  const lim = Math.max(...payload.x.map(Math.abs))

  chart.setOption(
    {
      backgroundColor: '#10141c',
      title: {
        text: '高炉横截面温度场反演',
        subtext: `快照时间 ${new Date(payload.timestamp * 1000).toLocaleTimeString()}  ·  拟合残差 ${(payload.residual * 100).toFixed(2)}%`,
        left: 'center',
        textStyle: { color: '#e8ecf3', fontSize: 16 },
        subtextStyle: { color: '#8a93a6' },
      },
      grid: { left: 60, right: 90, top: 70, bottom: 40 },
      xAxis: {
        type: 'value',
        min: -lim,
        max: lim,
        name: 'x / m',
        axisLine: { lineStyle: { color: '#556' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        min: -lim,
        max: lim,
        name: 'y / m',
        axisLine: { lineStyle: { color: '#556' } },
        splitLine: { show: false },
      },
      visualMap: {
        min,
        max,
        calculable: true,
        orient: 'vertical',
        right: 10,
        top: 'center',
        text: ['°C'],
        textStyle: { color: '#c6cdd9' },
        inRange: {
          color: ['#2c7bb6', '#00a6ca', '#00ccbc', '#90eb9d', '#ffff9d', '#f9d057', '#f29e2e', '#e76818', '#d7191c'],
        },
      },
      series: [
        {
          name: '温度场',
          type: 'heatmap',
          data: heat,
          pointSize: 6,
          blurSize: 10,
        },
        {
          name: '热电偶',
          type: 'scatter',
          symbol: 'triangle',
          symbolSize: 9,
          itemStyle: { color: '#fff', borderColor: '#000', borderWidth: 1 },
          data: tcScatter(payload),
          tooltip: {
            formatter: (p) => `热电偶<br/>温度: ${p.value[2].toFixed(1)} °C`,
          },
          z: 10,
        },
      ],
      tooltip: { trigger: 'item' },
    },
    { notMerge: false },
  )
}

watch(() => props.payload, (p) => render(p))

const onResize = () => chart && chart.resize()

onMounted(() => {
  chart = echarts.init(chartEl.value)
  if (props.payload) render(props.payload)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart && chart.dispose()
})
</script>

<style scoped>
.heatmap {
  width: 100%;
  height: 100%;
  min-height: 560px;
}
</style>
