"""炉温场有限元反演求解器。

物理模型：高炉某一横截面内的稳态导热反问题。
炉壁周向均布 32 支热电偶提供 Dirichlet 边界温度，
在圆截面上求解稳态热传导方程（Laplace 方程，假设截面内
等效导热系数均匀且无内热源），反演炉内温度场分布。

增量更新设计：
  1. 网格与刚度矩阵只装配一次（与温度数据无关），缓存复用；
  2. 新数据到达时仅需更新边界向量并重解线性系统；
  3. 输出网格的 IDW 插值权重同样预计算缓存。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class InversionResult:
    """反演输出：供 ECharts 热力图直接消费的笛卡尔网格数据。"""

    nx: int
    ny: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    values: List[Optional[float]]  # 长度 nx*ny（行优先），圆域外为 None
    t_min: float
    t_max: float
    boundary_temps: List[float]  # 32 支热电偶原始读数


class FemThermalSolver:
    """圆截面稳态导热 FEM 反演器。"""

    def __init__(
        self,
        radius: float = 5.0,
        n_rings: int = 14,
        n_angles: int = 64,
        n_sensors: int = 32,
        grid_n: int = 61,
    ) -> None:
        self.radius = radius
        self.n_rings = n_rings
        self.n_angles = n_angles
        self.n_sensors = n_sensors
        self.grid_n = grid_n

        # 构建极坐标三角网格（只做一次）
        self._nodes, self._elems = self._build_mesh()
        self.n_nodes = self._nodes.shape[0]
        # 外环节点即边界节点（最后 n_angles 个）
        self._boundary_idx = np.arange(self.n_nodes - n_angles, self.n_nodes)
        self._interior_idx = np.arange(0, self.n_nodes - n_angles)

        # 装配 Laplace 刚度矩阵（只做一次，增量复用）
        k = self._assemble_stiffness()
        self._k_uu = k[np.ix_(self._interior_idx, self._interior_idx)]
        self._k_ub = k[np.ix_(self._interior_idx, self._boundary_idx)]

        # 预计算热电偶 -> 边界节点的角度插值矩阵
        self._bc_interp = self._build_boundary_interp()

        # 预计算输出网格 IDW 插值权重
        self._grid_pts, self._grid_w, self._grid_mask = self._build_grid_interp()

    def _build_mesh(self) -> Tuple[np.ndarray, np.ndarray]:
        nodes: List[Tuple[float, float]] = [(0.0, 0.0)]  # 中心节点 0
        for i in range(1, self.n_rings + 1):
            r = self.radius * i / self.n_rings
            for j in range(self.n_angles):
                theta = 2.0 * math.pi * j / self.n_angles
                nodes.append((r * math.cos(theta), r * math.sin(theta)))
        elems: List[Tuple[int, int, int]] = []
        na = self.n_angles
        # 中心扇形
        for j in range(na):
            elems.append((0, 1 + j, 1 + (j + 1) % na))
        # 环带四边形剖分为两个三角形
        for i in range(1, self.n_rings):
            inner0 = 1 + (i - 1) * na
            outer0 = 1 + i * na
            for j in range(na):
                jn = (j + 1) % na
                elems.append((inner0 + j, outer0 + j, outer0 + jn))
                elems.append((inner0 + j, outer0 + jn, inner0 + jn))
        return np.array(nodes, dtype=float), np.array(elems, dtype=int)

    def _assemble_stiffness(self) -> np.ndarray:
        k = np.zeros((self.n_nodes, self.n_nodes))
        xy = self._nodes
        for tri in self._elems:
            p = xy[tri]  # 3x2
            x = p[:, 0]
            y = p[:, 1]
            area2 = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
            area = abs(area2) / 2.0
            if area <= 0.0:
                continue
            b = np.array([y[1] - y[2], y[2] - y[0], y[0] - y[1]])
            c = np.array([x[2] - x[1], x[0] - x[2], x[1] - x[0]])
            ke = (np.outer(b, b) + np.outer(c, c)) / (4.0 * area)
            for a in range(3):
                for d in range(3):
                    k[tri[a], tri[d]] += ke[a, d]
        return k

    def _build_boundary_interp(self) -> np.ndarray:
        """32 支热电偶读数 -> n_angles 个边界节点的线性角度插值矩阵。"""
        na = self.n_angles
        m = np.zeros((na, self.n_sensors))
        for j in range(na):
            theta = 2.0 * math.pi * j / na
            pos = theta / (2.0 * math.pi) * self.n_sensors
            k0 = int(math.floor(pos)) % self.n_sensors
            k1 = (k0 + 1) % self.n_sensors
            frac = pos - math.floor(pos)
            m[j, k0] = 1.0 - frac
            m[j, k1] = frac
        return m

    def _build_grid_interp(self):
        """预计算笛卡尔输出网格 -> FEM 节点的 IDW 权重（只算一次）。"""
        n = self.grid_n
        lin = np.linspace(-self.radius, self.radius, n)
        gx, gy = np.meshgrid(lin, lin)
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        r = np.hypot(pts[:, 0], pts[:, 1])
        mask = r <= self.radius * 1.0001
        valid = pts[mask]

        # IDW：对每个有效网格点取最近 6 个 FEM 节点
        k_near = 6
        diff = valid[:, None, :] - self._nodes[None, :, :]
        dist = np.sqrt((diff ** 2).sum(axis=2))
        idx = np.argpartition(dist, k_near, axis=1)[:, :k_near]
        d = np.take_along_axis(dist, idx, axis=1)
        d = np.maximum(d, 1e-9)
        w = 1.0 / (d ** 2)
        w /= w.sum(axis=1, keepdims=True)

        weights = np.zeros((valid.shape[0], self.n_nodes))
        rows = np.arange(valid.shape[0])[:, None]
        weights[rows, idx] = w
        return pts, weights, mask

    def solve(self, sensor_temps: List[float]) -> InversionResult:
        """增量求解：复用已装配的矩阵，仅更新边界条件并重解。"""
        sensor = np.asarray(sensor_temps, dtype=float)
        if sensor.shape[0] != self.n_sensors:
            raise ValueError(f"期望 {self.n_sensors} 支热电偶读数，收到 {sensor.shape[0]}")

        t_boundary = self._bc_interp @ sensor  # 边界节点温度
        rhs = -self._k_ub @ t_boundary
        t_interior = np.linalg.solve(self._k_uu, rhs)

        t_all = np.empty(self.n_nodes)
        t_all[self._interior_idx] = t_interior
        t_all[self._boundary_idx] = t_boundary

        grid_vals = self._grid_w @ t_all  # 有效网格点温度
        n = self.grid_n
        values: List[Optional[float]] = [None] * (n * n)
        valid_positions = np.flatnonzero(self._grid_mask)
        for pos, val in zip(valid_positions, grid_vals):
            values[int(pos)] = round(float(val), 2)

        return InversionResult(
            nx=n,
            ny=n,
            x_min=-self.radius,
            x_max=self.radius,
            y_min=-self.radius,
            y_max=self.radius,
            values=values,
            t_min=round(float(t_all.min()), 2),
            t_max=round(float(t_all.max()), 2),
            boundary_temps=[round(float(v), 2) for v in sensor],
        )
