# 高炉炉温场反演系统

基于高炉炉壁 32 支热电偶（4 个轴向层 x 8 个周向方位）的测温数据，
通过有限元反演算法推算炉内温度场分布，并以 ECharts 热力图实时展示。

## 系统架构

```
热电偶 -> InfluxDB -> influx_client -> fem_solver -> api_router -> Vue3 + ECharts
                                        |
                                  cache_manager (缓存 + 增量更新)
```

- **backend/app/influx_client.py** — InfluxDB 数据拉取；未配置连接时自动切换
  模拟数据源（5 秒分桶，便于演示缓存命中）
- **backend/app/fem_solver.py** — 环形截面 Q4 有限元正演 + Tikhonov / 时序
  正则化反演，由壁面测温推算内表面温度分布及全场温度
- **backend/app/cache_manager.py** — 以数据时间戳为版本的缓存；数据更新时
  以上一时刻解为先验做增量反演
- **backend/app/api_router.py** — 反演查询 / 概览 / 参数调节 API
- **frontend/src/components/HeatmapView.vue** — 环形截面热力图（极坐标场
  重采样到笛卡尔网格）+ 热电偶标记
- **frontend/src/components/ControlPanel.vue** — 层切换、轮询控制、正则化
  参数调节、统计与传感器读数
- **frontend/src/composables/dataPoller.js** — 增量轮询（携带 since 时间戳，
  服务端返回 updated=false 时跳过重渲染）

## 物理模型

炉壁环形截面稳态导热: -div(k grad T) = 0

- 内表面: 未知温度分布 T_inner(theta)，待反演
- 外表面: 对流冷却 Robin 边界 -k dT/dn = h(T - T_amb)
- 逆问题: 传感器读数 t = G x + c（G 为影响矩阵，由单位激励正演构建），
  求解 min ||Gx - t||^2 + λ||Lx||^2 + μ||x - x_prev||^2

## 运行

后端（Python 3.9+）:

```bash
cd backend
pip install -r requirements.txt
# 可选: 接入真实 InfluxDB
export INFLUX_URL=http://localhost:8086 INFLUX_TOKEN=<token> INFLUX_ORG=steel-plant INFLUX_BUCKET=blast_furnace
uvicorn app.main:app --port 8000
```

前端（Node 18+）:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173，/api 已代理到 8000
```

未设置 INFLUX_URL 时系统自动使用模拟数据源，可直接演示完整流程。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/health | 健康检查与数据源 |
| GET | /api/inversion/field?level=0&since=<ts> | 指定层温度场；since 为客户端已持有版本，未更新返回 updated=false |
| GET | /api/inversion/overview | 各层统计与 32 支传感器读数 |
| POST | /api/inversion/params | 调节正则化参数 reg_lambda / reg_mu |

## InfluxDB 数据格式

measurement: thermocouple；tag: level (0-3), azimuth (0-7)；
field: temperature (float, °C)。
