"""Finite-element inverse solver for the furnace temperature field.

Model
-----
Steady-state heat conduction in the furnace wall, treated as a 2-D annulus
(r_inner .. r_outer) with linear (P1) triangular elements:

    -div(k grad T) = 0        in the wall
    T = g(theta)              on the hot face r = r_inner   (unknown)
    -k dT/dn = h (T - T_amb)  on the outer shell r = r_outer

The unknown hot-face temperature g(theta) is parameterised by a truncated
Fourier series. Because the forward problem is linear in g, the thermocouple
readings are a linear map of the Fourier coefficients:

    T_tc = A g + b

The inverse problem is solved as a Tikhonov-regularised least-squares system
with an optional temporal term anchoring the solution to the previous
estimate (used by the incremental-update path):

    min_g ||A g - T_meas||^2 + lambda ||L g||^2 + lambda_t ||g - g_prev||^2

The reconstructed hot-face temperature is then used to solve the forward
problem once more, and the interior (r < r_inner) is filled by harmonic
extension, yielding the full cross-section field on a Cartesian grid.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from scipy import sparse
from scipy.sparse import linalg as spla

from .config import settings


@dataclass
class InversionResult:
    timestamp: float
    grid_n: int
    x: List[float]              # Cartesian grid axes (metres)
    y: List[float]
    field: List[List[Optional[float]]]  # row-major [ny][nx], None outside furnace
    hot_face: List[float]       # reconstructed hot-face temperature vs theta
    theta: List[float]
    tc_theta: List[float]       # thermocouple angular positions
    tc_values: List[float]      # measured thermocouple temperatures
    residual: float             # relative fit residual at thermocouples


class FemInversionSolver:
    """Builds the FEM operators once, then solves per-snapshot inversions."""

    def __init__(self) -> None:
        s = settings
        self.r_in, self.r_tc, self.r_out = s.r_inner, s.r_tc, s.r_outer
        self.nr, self.nt = s.mesh_nr, s.mesh_nt
        self.n_modes = s.n_fourier_modes
        self.n_params = 2 * self.n_modes + 1
        self.k_wall = 2.3       # refractory conductivity W/(m K)
        self.h_out = 15.0       # outer shell convection W/(m^2 K)
        self.t_amb = 40.0
        self._build_mesh()
        self._assemble()
        self._build_fourier_basis()
        self._build_inversion_operators()

    # ------------------------------------------------------------------ mesh
    def _build_mesh(self) -> None:
        nr, nt = self.nr, self.nt
        radii = np.linspace(self.r_in, self.r_out, nr + 1)
        nodes = []
        for r in radii:
            for j in range(nt):
                theta = 2.0 * math.pi * j / nt
                nodes.append((r * math.cos(theta), r * math.sin(theta)))
        self.nodes = np.array(nodes)                    # (nn, 2)
        self.radii = radii

        elems = []
        for i in range(nr):
            for j in range(nt):
                j2 = (j + 1) % nt
                a = i * nt + j
                b = i * nt + j2
                c = (i + 1) * nt + j
                d = (i + 1) * nt + j2
                elems.append((a, c, d))
                elems.append((a, d, b))
        self.elems = np.array(elems)                    # (ne, 3)
        self.nn = len(nodes)
        self.inner_nodes = np.arange(0, nt)             # first radial layer
        self.outer_nodes = np.arange(nr * nt, (nr + 1) * nt)
        # Thermocouple interpolation weights (nearest radial layer + angular lerp)
        i_tc = int(np.argmin(np.abs(radii - self.r_tc)))
        self.tc_row_idx = i_tc * nt + np.arange(settings.n_thermocouples) * 0  # placeholder
        tc_theta = 2.0 * math.pi * np.arange(settings.n_thermocouples) / settings.n_thermocouples
        self.tc_theta = tc_theta
        pos = tc_theta / (2.0 * math.pi) * nt
        j0 = np.floor(pos).astype(int) % nt
        w = pos - np.floor(pos)
        j1 = (j0 + 1) % nt
        self.tc_rows = np.vstack([i_tc * nt + j0, i_tc * nt + j1])
        self.tc_w = np.vstack([1.0 - w, w])

    # ----------------------------------------------------------- FEM assembly
    def _assemble(self) -> None:
        """Stiffness matrix for unit conductivity plus outer Robin terms."""
        rows, cols, vals = [], [], []
        for tri in self.elems:
            xy = self.nodes[tri]                        # (3, 2)
            mat = np.ones((3, 3))
            mat[:, :2] = xy
            det = np.linalg.det(mat)
            area = abs(det) / 2.0
            if area < 1e-14:
                continue
            b = np.array([xy[1, 1] - xy[2, 1], xy[2, 1] - xy[0, 1], xy[0, 1] - xy[1, 1]]) / det
            c = np.array([xy[2, 0] - xy[1, 0], xy[0, 0] - xy[2, 0], xy[1, 0] - xy[0, 0]]) / det
            ke = self.k_wall * area * (np.outer(b, b) + np.outer(c, c))
            for a in range(3):
                for d in range(3):
                    rows.append(tri[a])
                    cols.append(tri[d])
                    vals.append(ke[a, d])
        K = sparse.coo_matrix((vals, (rows, cols)), shape=(self.nn, self.nn)).tocsr()

        # Robin (convection) boundary on the outer shell
        nt = self.nt
        edge_len = 2.0 * math.pi * self.r_out / nt
        robin = self.h_out * edge_len / 6.0 * np.array([[2.0, 1.0], [1.0, 2.0]])
        rows, cols, vals = [], [], []
        for j in range(nt):
            n0 = self.outer_nodes[j]
            n1 = self.outer_nodes[(j + 1) % nt]
            for a, na in enumerate((n0, n1)):
                for d, nb in enumerate((n0, n1)):
                    rows.append(na)
                    cols.append(nb)
                    vals.append(robin[a, d])
        K = K + sparse.coo_matrix((vals, (rows, cols)), shape=(self.nn, self.nn))
        self.K = K.tocsc()

        # Constant part of the RHS from the Robin ambient term
        f = np.zeros(self.nn)
        f_amb = self.h_out * self.t_amb * edge_len / 2.0
        for j in self.outer_nodes:
            f[j] += f_amb
        self.f_base = f

        # Free = everything except the inner (Dirichlet) ring
        mask = np.ones(self.nn, dtype=bool)
        mask[self.inner_nodes] = False
        self.free = np.where(mask)[0]
        self.K_ff = self.K[self.free][:, self.free].tocsc()
        self.K_fi = self.K[self.free][:, self.inner_nodes].tocsc()
        self._factor = spla.factorized(self.K_ff)

    # -------------------------------------------------- parameterisation of g
    def _build_fourier_basis(self) -> None:
        nt = self.nt
        theta = 2.0 * math.pi * np.arange(nt) / nt
        cols = [np.ones(nt)]
        for m in range(1, self.n_modes + 1):
            cols.append(np.cos(m * theta))
            cols.append(np.sin(m * theta))
        self.B = np.column_stack(cols)                  # (nt, n_params)
        # Second-derivative (smoothness) regularisation on Fourier coeffs
        d = [0.0]
        for m in range(1, self.n_modes + 1):
            d.extend([m ** 4, m ** 4])
        self.L = np.diag(np.array(d))

    def _build_inversion_operators(self) -> None:
        """Precompute A and b such that T_tc ~= A g + b (linear map)."""
        # Influence of each Fourier basis function on the free nodes:
        # K_ff T = f - K_fi (B g)  =>  T = T0 + M g
        M_free = self._factor(-self.K_fi @ self.B)      # (n_free, n_params)
        T0_free = self._factor(self.f_base[self.free])
        # Scatter back to full node vectors
        M_full = np.zeros((self.nn, self.n_params))
        M_full[self.free] = M_free
        T0_full = np.zeros(self.nn)
        T0_full[self.free] = T0_free
        # Thermocouple sampling: bilinear-in-angle interpolation
        self.A = (self.tc_w[0][:, None] * M_full[self.tc_rows[0]]
                  + self.tc_w[1][:, None] * M_full[self.tc_rows[1]])
        self.b = (self.tc_w[0] * T0_full[self.tc_rows[0]]
                  + self.tc_w[1] * T0_full[self.tc_rows[1]])
        # Normal equations with smoothness regularisation
        self.AtA = self.A.T @ self.A
        self.reg = settings.reg_lambda * self.L

    # ---------------------------------------------------------------- solving
    def invert(
        self,
        tc_values: np.ndarray,
        timestamp: float,
        g_prev: Optional[np.ndarray] = None,
        reg_lambda: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Solve for Fourier coefficients; returns (g, hot_face, residual)."""
        lam = settings.reg_lambda if reg_lambda is None else reg_lambda
        lhs = self.AtA + lam * self.L
        rhs = self.A.T @ (np.asarray(tc_values) - self.b)
        if g_prev is not None:
            lhs = lhs + settings.temporal_lambda * np.eye(self.n_params)
            rhs = rhs + settings.temporal_lambda * g_prev
        g = np.linalg.solve(lhs, rhs)
        fit = self.A @ g + self.b
        denom = max(np.linalg.norm(tc_values), 1e-9)
        residual = float(np.linalg.norm(fit - tc_values) / denom)
        hot_face = self.B @ g
        return g, hot_face, residual

    def reconstruct_field(self, hot_face: np.ndarray) -> np.ndarray:
        """Forward solve with the inverted hot-face Dirichlet condition."""
        rhs = self.f_base[self.free] - self.K_fi @ hot_face
        T = np.zeros(self.nn)
        T[self.inner_nodes] = hot_face
        T[self.free] = self._factor(rhs)
        return T

    # ------------------------------------------------------------- heatmap out
    def to_grid(self, T_wall: np.ndarray, hot_face: np.ndarray) -> Tuple[list, list, list]:
        """Sample the field on a Cartesian grid; harmonic fill for r < r_in."""
        n = settings.grid_n
        lim = self.r_out * 1.02
        xs = np.linspace(-lim, lim, n)
        ys = np.linspace(-lim, lim, n)
        field: List[List[Optional[float]]] = []

        # Fourier coefficients of the hot-face temperature for the inner fill
        theta_h = 2.0 * math.pi * np.arange(self.nt) / self.nt
        a0 = float(np.mean(hot_face))
        amps = []
        for m in range(1, self.n_modes + 1):
            am = 2.0 * float(np.mean(hot_face * np.cos(m * theta_h)))
            bm = 2.0 * float(np.mean(hot_face * np.sin(m * theta_h)))
            amps.append((am, bm))

        # Fast lookup for wall temperatures by (radial layer, angle)
        T_layers = T_wall.reshape(self.nr + 1, self.nt)
        radii = self.radii

        for y in ys:
            row: List[Optional[float]] = []
            for x in xs:
                r = math.hypot(x, y)
                if r > self.r_out:
                    row.append(None)
                    continue
                th = math.atan2(y, x) % (2.0 * math.pi)
                if r <= self.r_in:
                    # Harmonic extension into the furnace interior
                    rho = r / self.r_in
                    val = a0
                    for m, (am, bm) in enumerate(amps, start=1):
                        val += (rho ** m) * (am * math.cos(m * th) + bm * math.sin(m * th))
                    row.append(round(val, 2))
                else:
                    # Bilinear interpolation in (r, theta) on the FEM layers
                    pos_r = (r - self.r_in) / (self.r_out - self.r_in) * self.nr
                    i0 = min(int(pos_r), self.nr - 1)
                    wr = pos_r - i0
                    pos_t = th / (2.0 * math.pi) * self.nt
                    j0 = int(pos_t) % self.nt
                    j1 = (j0 + 1) % self.nt
                    wt = pos_t - int(pos_t)
                    v00 = T_layers[i0, j0] * (1 - wt) + T_layers[i0, j1] * wt
                    v10 = T_layers[i0 + 1, j0] * (1 - wt) + T_layers[i0 + 1, j1] * wt
                    row.append(round(v00 * (1 - wr) + v10 * wr, 2))
            field.append(row)
        return [round(float(v), 3) for v in xs], [round(float(v), 3) for v in ys], field

    # ------------------------------------------------------------ full pipeline
    def solve(
        self,
        tc_values: List[float],
        timestamp: float,
        g_prev: Optional[np.ndarray] = None,
        reg_lambda: Optional[float] = None,
    ) -> Tuple[InversionResult, np.ndarray]:
        tc = np.asarray(tc_values, dtype=float)
        g, hot_face, residual = self.invert(tc, timestamp, g_prev, reg_lambda)
        T_wall = self.reconstruct_field(hot_face)
        xs, ys, field = self.to_grid(T_wall, hot_face)
        result = InversionResult(
            timestamp=timestamp,
            grid_n=settings.grid_n,
            x=xs,
            y=ys,
            field=field,
            hot_face=[round(float(v), 2) for v in hot_face],
            theta=[round(2.0 * math.pi * i / self.nt, 4) for i in range(self.nt)],
            tc_theta=[round(float(v), 4) for v in self.tc_theta],
            tc_values=[round(float(v), 2) for v in tc],
            residual=round(residual, 5),
        )
        return result, g
