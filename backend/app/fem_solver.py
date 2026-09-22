"""有限元炉温场反演求解器。

物理模型：炉壁横截面（r-z 平面）稳态导热  ∇·(k∇T) = 0
  - 热面（炉内侧）边界热流 q(z) 未知，为待反演量
  - 冷面（炉壳侧）对流换热边界（h, T_ambient 已知）
  - 上/下端面绝热

正问题：Q1 双线性四边形单元组装 K T = F(q)。
反问题：由 32 支壁内热电偶读数 d 反演热面热流 q，
  Tikhonov 正则化  min ||G q - d||^2 + λ ||L q||^2，
  法方程  A q = G^T d,  A = G^T G + λ L^T L。

缓存与增量更新：
  1. 结构矩阵 K、影响矩阵 G 仅组装一次（网格/物性不变时复用）；
  2. 法方程 A 的 Cholesky 分解按 λ 缓存；
  3. 测量值增量更新：q_new = q_prev + A^{-1} G^T (d_new - d_prev)，
     线性问题下该增量解精确，避免重复全量反演；
  4. 测量值未变化时直接命中结果缓存。
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class InversionResult:
    timestamp: float
    temperature: np.ndarray        # (n_axial+1, n_radial+1) 温度场 °C
    r_coords: np.ndarray           # 径向节点坐标
    z_coords: np.ndarray           # 轴向节点坐标
    hot_face_flux: np.ndarray      # 反演的热面热流 W/m^2
    hot_face_temp: np.ndarray      # 热面温度 °C
    sensor_residual: np.ndarray    # 各热电偶拟合残差 °C
    cache_hit: bool                # 是否命中结果缓存
    incremental: bool              # 是否走增量更新路径
    changed_sensors: list[int]     # 相对上一帧发生变化的热电偶索引
    solve_ms: float

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "r_coords": np.round(self.r_coords, 4).tolist(),
            "z_coords": np.round(self.z_coords, 4).tolist(),
            "temperature": np.round(self.temperature, 2).tolist(),
            "hot_face_flux": np.round(self.hot_face_flux, 1).tolist(),
            "hot_face_temp": np.round(self.hot_face_temp, 2).tolist(),
            "sensor_residual": np.round(self.sensor_residual, 3).tolist(),
            "cache_hit": self.cache_hit,
            "incremental": self.incremental,
            "changed_sensors": self.changed_sensors,
            "solve_ms": round(self.solve_ms, 2),
        }


@dataclass
class _MatrixCache:
    """结构矩阵缓存：网格与物性参数不变时全程复用。"""
    key: str = ""
    k_factor: object = None       # K 的稀疏 LU 分解
    g_matrix: np.ndarray = None   # 影响矩阵 G (32, n_inner)
    s_matrix: sp.csr_matrix = None
    b_matrix: sp.csr_matrix = None
    f_conv: np.ndarray = None     # 对流边界贡献


@dataclass
class _InverseCache:
    """法方程分解缓存：按正则化系数 λ 缓存。"""
    lam: float = -1.0
    a_cho: tuple = None           # Cholesky 分解 (c, lower)
    gt: np.ndarray = None


@dataclass
class _StateCache:
    """上一帧反演状态，用于增量更新与结果缓存。"""
    meas_hash: str = ""
    lam: float = -1.0
    measurements: np.ndarray = None
    q_prev: np.ndarray = None
    result: InversionResult = None
    result_at: float = 0.0


class FemInversionSolver:
    def __init__(self, config: AppConfig):
        self._cfg = config
        geo, fem = config.geometry, config.fem
        self._nr, self._nz = fem.n_radial, fem.n_axial
        self._r = np.linspace(geo.r_inner, geo.r_outer, self._nr + 1)
        self._z = np.linspace(geo.z_bottom, geo.z_top, self._nz + 1)
        self._n_nodes = (self._nr + 1) * (self._nz + 1)
        self._n_inner = self._nz + 1  # 热面未知热流参数数
        self._tc_positions = self._build_tc_positions()
        self._matrices = _MatrixCache()
        self._inverse = _InverseCache()
        self._state = _StateCache()
        self._result_ttl = config.cache.result_ttl_s
        self._incr_tol = config.cache.incremental_tol

    # ------------------------------------------------------------------ #
    # 网格与热电偶位置
    # ------------------------------------------------------------------ #
    def _node_id(self, iz: int, ir: int) -> int:
        return iz * (self._nr + 1) + ir

    def _build_tc_positions(self) -> np.ndarray:
        """32 支热电偶：tc_rows 个高度 x tc_cols 个埋深，按行优先展开。"""
        geo = self._cfg.geometry
        heights = np.linspace(
            geo.z_bottom + 0.75, geo.z_top - 0.75, geo.tc_rows
        )
        positions = [
            (d, z) for z in heights for d in geo.tc_depths
        ]
        return np.asarray(positions, dtype=float)  # (32, 2) -> (r, z)

    # ------------------------------------------------------------------ #
    # 正问题：矩阵组装（仅首次或参数变化时执行）
    # ------------------------------------------------------------------ #
    def _matrix_key(self) -> str:
        fem = self._cfg.fem
        raw = (
            f"{self._nr},{self._nz},{fem.conductivity},"
            f"{fem.h_outer},{fem.t_ambient}"
        )
        return hashlib.md5(raw.encode()).hexdigest()

    def _ensure_matrices(self) -> None:
        key = self._matrix_key()
        if self._matrices.key == key:
            return
        t0 = time.perf_counter()
        fem = self._cfg.fem
        k_cond = fem.conductivity

        rows, cols, data = [], [], []
        hr = self._r[1] - self._r[0]
        hz = self._z[1] - self._z[0]
        # Q1 单元 2x2 高斯积分
        gp = 1.0 / np.sqrt(3.0)
        gauss_pts = [(-gp, -gp), (gp, -gp), (gp, gp), (-gp, gp)]
        for iz in range(self._nz):
            for ir in range(self._nr):
                nodes = [
                    self._node_id(iz, ir),
                    self._node_id(iz, ir + 1),
                    self._node_id(iz + 1, ir + 1),
                    self._node_id(iz + 1, ir),
                ]
                ke = np.zeros((4, 4))
                for xi, eta in gauss_pts:
                    dN_dxi = 0.25 * np.array(
                        [-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)]
                    )
                    dN_deta = 0.25 * np.array(
                        [-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)]
                    )
                    J = np.diag([hr / 2.0, hz / 2.0])
                    detJ = np.linalg.det(J)
                    dN = np.linalg.solve(J, np.vstack([dN_dxi, dN_deta]))
                    ke += k_cond * (dN.T @ dN) * detJ
                for a in range(4):
                    for b in range(4):
                        rows.append(nodes[a])
                        cols.append(nodes[b])
                        data.append(ke[a, b])

        K = sp.csr_matrix(
            (data, (rows, cols)), shape=(self._n_nodes, self._n_nodes)
        )

        # 冷面（ir = nr）对流边界：K += h，F += h * T_ambient
        f_conv = np.zeros(self._n_nodes)
        outer_nodes = [self._node_id(iz, self._nr) for iz in range(self._nz + 1)]
        conv = sp.csr_matrix(
            (
                np.full(len(outer_nodes), fem.h_outer),
                (outer_nodes, outer_nodes),
            ),
            shape=K.shape,
        )
        K = K + conv
        f_conv[outer_nodes] = fem.h_outer * fem.t_ambient

        # 热面（ir = 0）未知热流参数 -> 载荷映射矩阵 B
        inner_nodes = [self._node_id(iz, 0) for iz in range(self._nz + 1)]
        B = sp.csr_matrix(
            (np.ones(self._n_inner), (inner_nodes, np.arange(self._n_inner))),
            shape=(self._n_nodes, self._n_inner),
        )

        # 热电偶观测矩阵 S：双线性插值取值
        S = self._build_observation_matrix()

        # 影响矩阵 G = S K^{-1} B：对 K 做一次稀疏 LU，多右端回代
        k_factor = spla.splu(K.tocsc())
        X = k_factor.solve(B.toarray())          # K X = B
        G = np.asarray(S @ X)

        self._matrices = _MatrixCache(
            key=key,
            k_factor=k_factor,
            g_matrix=np.asarray(G),
            s_matrix=S,
            b_matrix=B,
            f_conv=f_conv,
        )
        self._inverse = _InverseCache()  # 结构变了，法方程缓存失效
        logger.info(
            "FEM matrices assembled: %d nodes, G %s, %.1f ms",
            self._n_nodes, G.shape, (time.perf_counter() - t0) * 1e3,
        )

    def _build_observation_matrix(self) -> sp.csr_matrix:
        rows, cols, data = [], [], []
        for i, (r_pos, z_pos) in enumerate(self._tc_positions):
            ir = min(int((r_pos - self._r[0]) / (self._r[1] - self._r[0])),
                     self._nr - 1)
            iz = min(int((z_pos - self._z[0]) / (self._z[1] - self._z[0])),
                     self._nz - 1)
            xi = ((r_pos - self._r[ir]) / (self._r[ir + 1] - self._r[ir])) * 2 - 1
            eta = ((z_pos - self._z[iz]) / (self._z[iz + 1] - self._z[iz])) * 2 - 1
            weights = 0.25 * np.array([
                (1 - xi) * (1 - eta),
                (1 + xi) * (1 - eta),
                (1 + xi) * (1 + eta),
                (1 - xi) * (1 + eta),
            ])
            nodes = [
                self._node_id(iz, ir),
                self._node_id(iz, ir + 1),
                self._node_id(iz + 1, ir + 1),
                self._node_id(iz + 1, ir),
            ]
            for w, n in zip(weights, nodes):
                rows.append(i)
                cols.append(n)
                data.append(w)
        return sp.csr_matrix(
            (data, (rows, cols)), shape=(len(self._tc_positions), self._n_nodes)
        )

    # ------------------------------------------------------------------ #
    # 反问题：法方程缓存
    # ------------------------------------------------------------------ #
    def _ensure_inverse(self, lam: float) -> None:
        if self._inverse.lam == lam and self._inverse.a_cho is not None:
            return
        G = self._matrices.g_matrix
        # 一阶差分光滑算子 L
        L = np.diff(np.eye(self._n_inner), n=1, axis=0)
        A = G.T @ G + lam * (L.T @ L)
        self._inverse = _InverseCache(
            lam=lam,
            a_cho=sla.cho_factor(A, lower=True),
            gt=G.T,
        )

    # ------------------------------------------------------------------ #
    # 对外主入口：反演（含缓存与增量更新）
    # ------------------------------------------------------------------ #
    def invert(self, measurements: np.ndarray, timestamp: float,
               lam: float | None = None) -> InversionResult:
        t0 = time.perf_counter()
        lam = self._cfg.fem.reg_lambda if lam is None else float(lam)
        self._ensure_matrices()
        self._ensure_inverse(lam)

        meas = np.asarray(measurements, dtype=float)
        meas_hash = hashlib.md5(np.round(meas, 3).tobytes()).hexdigest()
        state = self._state

        # 1) 结果缓存命中：测量值与正则化系数均未变且未过期
        if (state.meas_hash == meas_hash and state.lam == lam
                and state.result is not None
                and time.time() - state.result_at < self._result_ttl):
            cached = state.result
            cached.cache_hit = True
            cached.incremental = False
            cached.solve_ms = (time.perf_counter() - t0) * 1e3
            return cached

        # 2) 增量更新：q_new = q_prev + A^{-1} G^T Δd
        incremental = False
        changed: list[int] = []
        # 增量公式 q += A^{-1} G^T Δd 仅在 λ 不变（A 一致）时成立
        if (state.q_prev is not None and state.measurements is not None
                and state.lam == lam):
            delta = meas - state.measurements
            rel = np.linalg.norm(delta) / max(np.linalg.norm(meas), 1e-9)
            changed = np.where(np.abs(delta) > 1e-9)[0].tolist()
            if rel < self._incr_tol:
                q = state.q_prev.copy()
                incremental = True
            else:
                dq = sla.cho_solve(
                    self._inverse.a_cho, self._inverse.gt @ delta
                )
                q = state.q_prev + dq
                incremental = True
        else:
            # 3) 首次全量反演
            q = sla.cho_solve(
                self._inverse.a_cho, self._inverse.gt @ meas
            )
            changed = list(range(len(meas)))

        # 由 q 重算全场温度（复用 K 的 LU 分解）
        F = self._matrices.f_conv + self._matrices.b_matrix @ q
        T = self._matrices.k_factor.solve(F)
        T_field = T.reshape(self._nz + 1, self._nr + 1)

        fitted = self._matrices.g_matrix @ q
        residual = meas - fitted
        hot_face_temp = T_field[:, 0].copy()

        result = InversionResult(
            timestamp=timestamp,
            temperature=T_field,
            r_coords=self._r,
            z_coords=self._z,
            hot_face_flux=q,
            hot_face_temp=hot_face_temp,
            sensor_residual=residual,
            cache_hit=False,
            incremental=incremental,
            changed_sensors=changed,
            solve_ms=(time.perf_counter() - t0) * 1e3,
        )

        self._state = _StateCache(
            meas_hash=meas_hash,
            lam=lam,
            measurements=meas,
            q_prev=q,
            result=result,
            result_at=time.time(),
        )
        return result

    # ------------------------------------------------------------------ #
    # 状态查询
    # ------------------------------------------------------------------ #
    def cache_stats(self) -> dict:
        return {
            "matrices_cached": self._matrices.key != "",
            "inverse_lambda": self._inverse.lam,
            "has_prev_solution": self._state.q_prev is not None,
            "last_result_age_s": (
                round(time.time() - self._state.result_at, 2)
                if self._state.result else None
            ),
            "grid": {
                "n_radial": self._nr,
                "n_axial": self._nz,
                "n_nodes": self._n_nodes,
            },
            "tc_positions": np.round(self._tc_positions, 3).tolist(),
        }
