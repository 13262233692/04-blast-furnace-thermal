# 高炉炉温场反演系统

基于高炉炉壁 32 支热电偶的测温数据，通过有限元反演算法推算炉内横截面温度场分布，并在前端以 ECharts 热力图实时展示。

## 系统架构

```
InfluxDB (时序数据库)
    │  32 通道热电偶温度
    ▼
FastAPI 后端
    ├─ influx_client.py     数据拉取（真实 InfluxDB / Mock 回退）
    ├─ fem_solver.py        有限元正问题 + Tikhonov 正则化反演
    ├─ inversion_service.py 结果缓存与增量更新（时间正则化暖启动）
    └─ api_router.py        REST API
    │  JSON (增量: since 参数)
    ▼
Vue3 前端
    ├─ components/HeatmapView.vue   ECharts 热力图渲染
    ├─ components/ControlPanel.vue  轮询/正则化控制、状态与读数
    └─ services/data_poller.js      增量轮询器
```

## 反演模型

- 炉壁简化为二维圆环域（r_inner=4.5m ~ r_outer=5.8m），P1 三角形线性单元，稳态导热方程 `-div(k·grad T) = 0`。
- 未知热面（内壁）温度 `g(θ)` 用截断 Fourier 级数参数化（8 阶，17 个未知数）。
- 正问题线性 ⇒ 热电偶读数 `T_tc = A·g + b`，灵敏度矩阵 A 预计算并稀疏分解。
- 反演求解 Tikhonov 正则化最小二乘：`min ||A·g − T_meas||² + λ||L·g||² + λ_t||g − g_prev||²`，
  其中时序项锚定上一帧解，实现增量更新的帧间连贯。
- 反演得到热面温度后正演全场，炉内区域（r < r_inner）用调和延拓填充，输出 121×121 笛卡尔网格。

## 缓存与增量更新

- 后端 `InversionService` 缓存最近一次反演；仅当新数据时间戳更新时才重算，且以上一帧 Fourier 解做时序正则化暖启动。
- 前端轮询携带 `since=<timestamp>`，数据未变化时响应不含温度场负载（`updated=false`），节省带宽。

## 快速开始

### 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh            # http://localhost:8000 ，默认 USE_MOCK_INFLUX=true 使用模拟数据
```

接入真实 InfluxDB：

```bash
export USE_MOCK_INFLUX=false INFLUX_URL=http://<host>:8086 \
       INFLUX_TOKEN=<token> INFLUX_ORG=<org> INFLUX_BUCKET=furnace
```

InfluxDB 数据约定：measurement `thermocouple`，field `temperature`，tag `channel`（0–31）。

### 前端

```bash
cd frontend
npm install
npm run dev         # http://localhost:5173 ，/api 已代理到 8000
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/inversion/latest?since=<ts>` | 最新反演结果；`since` 命中时仅返回时间戳 |
| POST | `/api/inversion/refresh?reg_lambda=<λ>` | 强制重算，可覆盖正则化系数 |
| GET | `/api/thermocouples` | 32 通道原始读数与角度位置 |

## 主要配置（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `USE_MOCK_INFLUX` | `true` | 无真实库时使用合成数据 |
| `REG_LAMBDA` | `5e-3` | 空间光滑正则化权重 |
| `TEMPORAL_LAMBDA` | `2e-2` | 时序（增量）正则化权重 |
| `QUERY_WINDOW_S` | `120` | InfluxDB 查询窗口 |
