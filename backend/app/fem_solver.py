"""有限元温度场反演求解器。

物理模型: 高炉炉壁环形横截面内的稳态导热
    -div(k * grad T) = 0        (炉壁域内)
    T = T_inner(theta)          (内表面, 未知, 待反演)
    -k dT/dn = h (T - T_amb)    (外表面, 对流冷却, 已知)

反演思路(线性逆问题):
    传感器读数 t 与未知内表面温度 x 满足线性关系 t = G x + c，
    其中影响矩阵 G 通过对有限元方程逐列求解单位内边界激励得到。
    采用 Tikhonov 平滑正则化 + 时序增量正则化(相对上一时刻解)
    求闭式最小二乘解，再回代得到全场温度分布。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .config import settings


@dataclass
class InversionResult:
    """单层截面的反演结果。"""

    level: int
    timestamp: float
    r: np.ndarray            # 径向节点坐标, shape (nr+1,)
    theta: np.ndarray        # 周向节点坐标, shape (nt,)
    field: np.ndarray        # 温度场, shape (nr+1, nt)
    inner_temp: np.ndarray   # 反演得到的内表面温度, shape (nt,)
    sensor_fit: np.ndarray   # 正演复核的传感器温度, shape (n_azimuth,)
    residual: float          # 传感器拟合残差 (RMS)


class FemSolver:
    """环形截面有限元正反演求解器(所有层共用同一网格与算子)。"""

    def __init__(self, n_radial: int = 16, n_theta: int = 72) -> None:
        self.nr = n_radial
        self.nt = n_theta
        self.n_nodes = (n_radial + 1) * n_theta

        self.r = np.linspace(settings.r_inner, settings.r_outer, n_radial + 1)
        self.theta = np.arange(n_theta) * 2.0 * math.pi / n_theta

        self._build_operators()

    # ------------------------------------------------------------------ #
    # 网格与算子装配
    # ------------------------------------------------------------------ #
    def _nid(self, i: int, j: int) -> int:
        return i * self.nt + (j % self.nt)

    def _build_operators(self) -> None:
        k_cond = settings.conductivity
        h = settings.conv_coeff
        dtheta = 2.0 * math.pi / self.nt

        rows, cols, vals = [], [], []
        rhs = np.zeros(self.n_nodes)

        gauss_pts = [-1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0)]

        def add_ke(nids, ke):
            for a in range(4):
                for b in range(4):
                    rows.append(nids[a])
                    cols.append(nids[b])
                    vals.append(ke[a, b])

        # Q4 双线性单元装配
        for i in range(self.nr):
            for j in range(self.nt):
                nids = [
                    self._nid(i, j),
                    self._nid(i, j + 1),
                    self._nid(i + 1, j + 1),
                    self._nid(i + 1, j),
                ]
                coords = np.array([
                    [self.r[i] * math.cos(self.theta[j]), self.r[i] * math.sin(self.theta[j])],
                    [self.r[i] * math.cos(self.theta[(j + 1) % self.nt]),
                     self.r[i] * math.sin(self.theta[(j + 1) % self.nt])],
                    [self.r[i + 1] * math.cos(self.theta[(j + 1) % self.nt]),
                     self.r[i + 1] * math.sin(self.theta[(j + 1) % self.nt])],
                    [self.r[i + 1] * math.cos(self.theta[j]), self.r[i + 1] * math.sin(self.theta[j])],
                ])
                ke = np.zeros((4, 4))
                for gx in gauss_pts:
                    for gy in gauss_pts:
                        dN = 0.25 * np.array([
                            [-(1 - gy), -(1 - gx)],
                            [(1 - gy), -(1 + gx)],
                            [(1 + gy), (1 + gx)],
                            [-(1 + gy), (1 - gx)],
                        ])
                        jac = dN.T @ coords  # jac[a,b] = dx_b/dxi_a
                        det_j = abs(np.linalg.det(jac))
                        dNxy = np.linalg.solve(jac, dN.T).T  # shape (4, 2)
                        ke += k_cond * (dNxy @ dNxy.T) * det_j
                add_ke(nids, ke)

        # 外表面 Robin 边界(一维线单元)
        edge_len = settings.r_outer * dtheta
        ke_r = h * edge_len / 6.0 * np.array([[2.0, 1.0], [1.0, 2.0]])
        fe_r = h * settings.ambient_temp * edge_len / 2.0 * np.ones(2)
        for j in range(self.nt):
            nids = [self._nid(self.nr, j), self._nid(self.nr, j + 1)]
            for a in range(2):
                for b in range(2):
                    rows.append(nids[a])
                    cols.append(nids[b])
                    vals.append(ke_r[a, b])
                rhs[nids[a]] += fe_r[a]

        K = sp.csr_matrix((vals, (rows, cols)), shape=(self.n_nodes, self.n_nodes))

        # 自由度划分: 内表面节点为狄利克雷未知量，其余自由
        inner = np.array([self._nid(0, j) for j in range(self.nt)])
        rest = np.array([n for n in range(self.n_nodes) if n >= self.nt])

        self._inner = inner
        self._rest = rest
        self._K_RR = K[rest][:, rest].tocsc()
        self._K_RI = K[rest][:, inner].tocsr()
        self._F_R = rhs[rest]
        self._lu = spla.splu(self._K_RR)

        self._S = self._build_sensor_interp()
        self._G, self._c = self._build_influence()
        self._L = self._build_smoothness()

    def _build_sensor_interp(self) -> sp.csr_matrix:
        """传感器位置的双线性插值矩阵 S, t_sensor = S @ T_nodes。"""
        r_s = settings.r_inner + settings.sensor_radius_ratio * (
            settings.r_outer - settings.r_inner
        )
        n_az = settings.n_azimuth
        S = sp.lil_matrix((n_az, self.n_nodes))
        dr = self.r[1] - self.r[0]
        dtheta = self.theta[1] - self.theta[0]
        for s in range(n_az):
            th = s * 2.0 * math.pi / n_az
            i0 = min(int((r_s - settings.r_inner) / dr), self.nr - 1)
            j0 = int(th / dtheta) % self.nt
            fr = (r_s - self.r[i0]) / dr
            ft = (th - self.theta[j0]) / dtheta
            for (i, j, w) in (
                (i0, j0, (1 - fr) * (1 - ft)),
                (i0, j0 + 1, (1 - fr) * ft),
                (i0 + 1, j0, fr * (1 - ft)),
                (i0 + 1, j0 + 1, fr * ft),
            ):
                S[s, self._nid(i, j)] += w
        return S.tocsr()

    def _build_influence(self):
        """影响矩阵 G 与常值项 c: t_sensor = G @ T_inner + c * T_amb 贡献。"""
        G = np.zeros((settings.n_azimuth, self.nt))
        for j in range(self.nt):
            col = np.zeros(self.nt)
            col[j] = 1.0
            t_rest = self._lu.solve(-(self._K_RI @ col))
            full = np.zeros(self.n_nodes)
            full[self._inner] = col
            full[self._rest] = t_rest
            G[:, j] = self._S @ full
        # 环境温度( Robin 载荷 )单独正演一次
        t_rest = self._lu.solve(self._F_R)
        full = np.zeros(self.n_nodes)
        full[self._rest] = t_rest
        c = self._S @ full
        return G, c

    def _build_smoothness(self) -> np.ndarray:
        """周期二阶差分平滑算子。"""
        L = np.zeros((self.nt, self.nt))
        for j in range(self.nt):
            L[j, (j - 1) % self.nt] = 1.0
            L[j, j] = -2.0
            L[j, (j + 1) % self.nt] = 1.0
        return L

    # ------------------------------------------------------------------ #
    # 反演与正演
    # ------------------------------------------------------------------ #
    def invert(
        self,
        level: int,
        sensor_values: np.ndarray,
        timestamp: float,
        prev_inner: Optional[np.ndarray] = None,
        reg_lambda: Optional[float] = None,
        reg_mu: Optional[float] = None,
    ) -> InversionResult:
        """由一层 8 支热电偶读数反演该层截面温度场。

        prev_inner 非空时启用时序增量正则化，实现相邻时刻解的平滑更新。
        """
        lam = settings.reg_lambda if reg_lambda is None else reg_lambda
        mu = settings.reg_mu if reg_mu is None else reg_mu

        target = sensor_values - self._c
        A = self._G.T @ self._G + lam * (self._L.T @ self._L)
        b = self._G.T @ target
        if prev_inner is not None and mu > 0.0:
            A = A + mu * np.eye(self.nt)
            b = b + mu * prev_inner
        inner_temp = np.linalg.solve(A, b)

        field = self.forward(inner_temp)
        sensor_fit = self._G @ inner_temp + self._c
        residual = float(np.sqrt(np.mean((sensor_fit - sensor_values) ** 2)))
        return InversionResult(
            level=level,
            timestamp=timestamp,
            r=self.r.copy(),
            theta=self.theta.copy(),
            field=field,
            inner_temp=inner_temp,
            sensor_fit=sensor_fit,
            residual=residual,
        )

    def forward(self, inner_temp: np.ndarray) -> np.ndarray:
        """给定内表面温度分布，正演全场温度。"""
        t_rest = self._lu.solve(self._F_R - self._K_RI @ inner_temp)
        full = np.empty(self.n_nodes)
        full[self._inner] = inner_temp
        full[self._rest] = t_rest
        return full.reshape(self.nr + 1, self.nt)
