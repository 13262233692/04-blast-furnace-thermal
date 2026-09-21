# 高炉炉温场反演系统

基于炉壁 32 支热电偶测温数据，通过有限元反演推算高炉炉内截面温度场分布，
并以 ECharts 热力图实时展示。

## 系统架构

```
热电偶(×32) → InfluxDB → FastAPI 反演服务 → Vue3 + ECharts 前端
                              │
                              ├─ influx_client  时序数据拉取（含模拟降级）
                              ├─ fem_solver     有限元温度场反演
                              └─ api_router     缓存 + 增量更新 API
```

## 反演模型

稳态导热反问题：在炉体横截面（圆域）上求解 Laplace 方程，
32 支热电偶读数经角度线性插值后作为 Dirichlet 边界条件，
FEM（线性三角形单元）求解内部温度场，再经 IDW 插值输出到
61×61 笛卡尔网格供热力图渲染。

## 缓存与增量更新

- **服务端缓存**：`InversionCache` 以传感器数据时间戳为键，
  数据未更新时直接命中缓存，不重新求解（`cache_hits` 统计可观测）。
- **增量求解**：网格、刚度矩阵、边界插值矩阵、IDW 权重均在
  启动时一次性装配，新数据到达仅需重解线性系统（约 15~20 ms）。
- **增量传输**：前端轮询携带 `since_version`，服务端版本未变时
  返回 `{updated: false}` 轻量响应，不重复传输温度场网格；
  前端仅在收到新版本时重绘图表。

## 目录结构

```
backend/
  main.py           FastAPI 应用入口（装配各模块）
  influx_client.py  InfluxDB 数据接入（含 MockThermocoupleGenerator 降级）
  fem_solver.py     FEM 温度场反演求解器
  api_router.py     反演 API 路由 + InversionCache
  seed_influx.py    采集模拟器（向 InfluxDB 写入 32 路温度）
frontend/
  src/
    App.vue                    应用组装
    components/heatmap_view.vue 温度场热力图 + 边界温度条形图
    components/control_panel.vue 轮询控制与缓存状态面板
    composables/data_poller.js  增量轮询 composable
```

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```

未配置 InfluxDB 时自动使用内置模拟数据源。接入真实 InfluxDB：

```bash
export INFLUX_URL=http://localhost:8086
export INFLUX_TOKEN=<token>
export INFLUX_ORG=steel
export INFLUX_BUCKET=blast_furnace
uvicorn main:app --port 8000
```

另开终端运行采集模拟器写入数据：`python seed_influx.py --interval 5`

### 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 ，已配置 /api 代理到 :8000
```

## API

| 端点 | 说明 |
| --- | --- |
| `GET /api/health` | 数据源与缓存状态 |
| `GET /api/thermal/raw` | 最新 32 支热电偶读数 |
| `GET /api/thermal/field?since_version=N` | 反演温度场；版本未变时返回 `updated:false` |
