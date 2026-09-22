# 高炉炉温场反演系统

基于炉壁 32 支热电偶（8 高度层 × 4 埋深）测温数据，通过有限元反演算法
推算炉内温度场分布，前端 ECharts 热力图实时展示。

## 架构

```
InfluxDB ──> influx_client ──> fem_solver ──> api_router ──> data_poller ──> HeatmapView
 (时序数据)     (数据接入)      (FEM 反演)      (FastAPI)      (前端轮询)      (ECharts)
```

- **后端** `backend/`：Python + FastAPI + NumPy/SciPy
  - `app/influx_client.py` — InfluxDB 2.x 数据接入，连接失败自动降级为内置炉温模拟器
  - `app/fem_solver.py` — Q1 四边形单元稳态导热正问题 + Tikhonov 正则化反演
  - `app/api_router.py` — REST API 路由
  - `app/config.py` — 几何 / 网格 / 物性 / 缓存配置（环境变量可覆盖）
- **前端** `frontend/`：Vue3 + Vite + ECharts
  - `src/components/HeatmapView.vue` — 温度场热力图 + 热电偶测点叠加
  - `src/components/ControlPanel.vue` — 轮询控制、正则化系数、缓存统计
  - `src/services/data_poller.js` — 轮询服务（指数退避、增量/缓存计数）

## 反演算法

- 正问题：炉壁横截面稳态导热 `∇·(k∇T)=0`，热面热流 q(z) 未知，
  冷面对流边界（h、T_ambient 已知），上下端面绝热。
- 反问题：`min ||Gq − d||² + λ||Lq||²`，G 为影响矩阵（热电偶对热面热流的响应），
  L 为一阶差分光滑算子，法方程 `A q = Gᵀd` 用 Cholesky 分解求解。

## 缓存与增量更新

1. **结构矩阵缓存**：K 的稀疏 LU、影响矩阵 G 仅组装一次（网格/物性不变时复用）；
2. **法方程缓存**：A 的 Cholesky 分解按 λ 缓存，λ 变化自动重建；
3. **增量更新**：测量帧变化时 `q_new = q_prev + A⁻¹GᵀΔd`（线性问题下精确），
   避免重复全量反演（实测全量 ~350 ms → 增量 ~1 ms）；
4. **结果缓存**：测量值与 λ 均未变时直接命中（TTL 30 s）；
5. **传感器缓存**：`/api/sensors/latest` 短 TTL（5 s），防止高频轮询打满 InfluxDB。

## 快速开始

```bash
# 后端（默认 INFLUX_MOCK=true，无需 InfluxDB 即可运行）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 前端
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 已代理到 :8000
```

## 接入真实 InfluxDB

```bash
export INFLUX_MOCK=false
export INFLUX_URL=http://<host>:8086
export INFLUX_TOKEN=<token>
export INFLUX_ORG=steel-plant
export INFLUX_BUCKET=blast-furnace
```

数据模型：measurement `thermocouple`，tag `sensor_id` = `tc_01`…`tc_32`，
field `temperature`（°C）。写入示例：

```python
from influxdb_client import InfluxDBClient, Point, WritePrecision
with InfluxDBClient(url=..., token=..., org=...) as c:
    with c.write_api() as w:
        w.write("blast-furnace", "steel-plant",
                Point("thermocouple").tag("sensor_id", "tc_01").field("temperature", 512.3))
```

## API

| 端点 | 说明 |
| --- | --- |
| `GET /api/health` | 服务与 InfluxDB 连接状态 |
| `GET /api/sensors/latest` | 32 通道最新温度（带 5 s 缓存） |
| `GET /api/thermal-field?lam=` | 反演温度场、热面热流/温度、缓存与增量标记 |
| `GET /api/cache/stats` | 矩阵/法方程/结果缓存状态 |
| `POST /api/inversion/config` | 更新反演参数（正则化系数） |
