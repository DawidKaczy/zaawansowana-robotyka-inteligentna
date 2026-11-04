"""
Filtr cząsteczkowy 2D do lokalizacji robota na siatce.

Cząsteczka = (x, y, theta) — pozycja ciągła + orientacja.
Mapa = siatka komórek: 0=wolne, 1=ściana, 2=drzwi.

Pętla (jak w scenariuszu zadania 3):
    sense → normalize → resample → move
"""

from __future__ import annotations

import numpy as np

FREE = 0
WALL = 1
DOOR = 2

NAZWY = {FREE: "wolne", WALL: "ściana", DOOR: "drzwi"}
RESAMPLE_METHODS = ("multinomial", "systematic", "residual")


def make_default_map(h: int = 20, w: int = 20) -> np.ndarray:
    """Prosta mapa z korytarzem i kilkoma drzwiami."""
    m = np.full((h, w), FREE, dtype=int)
    m[0, :] = WALL
    m[-1, :] = WALL
    m[:, 0] = WALL
    m[:, -1] = WALL
    m[5, 2:10] = WALL
    m[5, 12:18] = WALL
    m[10, 2:8] = WALL
    m[10, 10:18] = WALL
    m[15, 4:16] = WALL
    m[5, 10] = DOOR
    m[5, 11] = DOOR
    m[10, 8] = DOOR
    m[10, 9] = DOOR
    m[15, 8] = DOOR
    m[15, 9] = DOOR
    return m


def _inset_in_cell(cell: int, u: float, margin: float = 0.18) -> float:
    """Losowy offset w komórce, z marginesem od krawędzi (żeby nie „wsiadać” na ścianę)."""
    return cell + margin + (1.0 - 2.0 * margin) * float(u)


def clamp_to_free(mapa: np.ndarray, x: float, y: float) -> tuple[float, float]:
    """Jeśli punkt wpadł w ścianę / poza mapę, wraca do wnętrza najbliższego wolnego."""
    h, w = mapa.shape
    xi = int(np.clip(np.floor(x), 0, w - 1))
    yi = int(np.clip(np.floor(y), 0, h - 1))
    if mapa[yi, xi] != WALL:
        # trzymamy się środkowej części komórki
        return _inset_in_cell(xi, np.clip(x - xi, 0.0, 1.0)), _inset_in_cell(
            yi, np.clip(y - yi, 0.0, 1.0)
        )
    for r in range(1, max(h, w)):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                nx, ny = xi + dx, yi + dy
                if 0 <= nx < w and 0 <= ny < h and mapa[ny, nx] != WALL:
                    return nx + 0.5, ny + 0.5
    return w / 2, h / 2


def cell_type(mapa: np.ndarray, x: float, y: float) -> int:
    h, w = mapa.shape
    xi = int(np.clip(np.floor(x), 0, w - 1))
    yi = int(np.clip(np.floor(y), 0, h - 1))
    return int(mapa[yi, xi])


def init_particles(mapa: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Losowe cząsteczki tylko na polach wolnych / drzwi. Shape (n, 3): x,y,theta."""
    free = np.argwhere(mapa != WALL)
    pick = rng.integers(0, len(free), size=n)
    # margines od krawędzi komórki → nie nachodzą wizualnie na ściany
    ys = np.array([_inset_in_cell(int(free[i, 0]), u) for i, u in zip(pick, rng.random(n))])
    xs = np.array([_inset_in_cell(int(free[i, 1]), u) for i, u in zip(pick, rng.random(n))])
    thetas = rng.uniform(0, 2 * np.pi, size=n)
    return np.column_stack([xs, ys, thetas])


def move_particles(
    particles: np.ndarray,
    mapa: np.ndarray,
    d: float = 0.8,
    sigma_d: float = 0.08,
    sigma_theta: float = np.deg2rad(8),
    rng: np.random.Generator | None = None,
    policy: str = "robot",
) -> np.ndarray:
    """
    Model ruchu:
    - z p=0.7 idź prosto o d
    - z p=0.2 skręć w prawo 90° i idź
    - z p=0.1 skręć w lewo 90° i idź
    + szum Gaussa na dystansie i kącie.
    """
    if rng is None:
        rng = np.random.default_rng()
    out = particles.copy()
    for i in range(len(out)):
        r = rng.random()
        if policy == "robot":
            turn = 0.0
            if r < 0.15:
                turn = -np.pi / 2
            elif r < 0.25:
                turn = np.pi / 2
        else:
            if r < 0.7:
                turn = 0.0
            elif r < 0.9:
                turn = np.pi / 2
            else:
                turn = -np.pi / 2
        out[i, 2] = (out[i, 2] + turn + rng.normal(0, sigma_theta)) % (2 * np.pi)
        step = d + rng.normal(0, sigma_d)
        nx = out[i, 0] + step * np.cos(out[i, 2])
        ny = out[i, 1] + step * np.sin(out[i, 2])
        out[i, 0], out[i, 1] = clamp_to_free(mapa, nx, ny)
    return out


def sense_weights_raw(
    particles: np.ndarray,
    pomiar: int,
    mapa: np.ndarray,
    p_hit: float = 0.85,
) -> np.ndarray:
    """Surowe wagi (przed normalizacją)."""
    p_miss = (1.0 - p_hit) / 2.0
    w = np.empty(len(particles))
    for i, (x, y, _) in enumerate(particles):
        typ = cell_type(mapa, x, y)
        w[i] = p_hit if typ == pomiar else p_miss
    return w


def normalize_weights(weights: np.ndarray) -> np.ndarray:
    s = float(weights.sum())
    if s <= 0:
        return np.ones(len(weights)) / len(weights)
    return weights / s


def sense_weights(
    particles: np.ndarray,
    pomiar: int,
    mapa: np.ndarray,
    p_hit: float = 0.85,
) -> np.ndarray:
    """Wagi po sense + normalize (kompatybilność wsteczna)."""
    return normalize_weights(sense_weights_raw(particles, pomiar, mapa, p_hit))


def resample_multinomial(
    particles: np.ndarray, weights: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Ruletka / multinomial (jak w 1D)."""
    cdf = np.cumsum(weights)
    u = rng.random(len(particles))
    idx = np.searchsorted(cdf, u, side="left")
    idx = np.clip(idx, 0, len(particles) - 1)
    return particles[idx].copy()


def resample_systematic(
    particles: np.ndarray, weights: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Systematic resampling — równomierne u_i na [0,1)."""
    n = len(particles)
    cdf = np.cumsum(weights)
    u0 = rng.random() / n
    u = u0 + np.arange(n) / n
    idx = np.searchsorted(cdf, u, side="left")
    idx = np.clip(idx, 0, n - 1)
    return particles[idx].copy()


def resample_residual(
    particles: np.ndarray, weights: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Residual resampling — część deterministyczna + reszta multinomial."""
    n = len(particles)
    counts = np.floor(weights * n).astype(int)
    out_idx: list[int] = []
    for i, c in enumerate(counts):
        out_idx.extend([i] * int(c))
    leftover = n - len(out_idx)
    if leftover > 0:
        residual = weights * n - counts
        residual = residual / residual.sum() if residual.sum() > 0 else np.ones(n) / n
        extra = rng.choice(n, size=leftover, p=residual)
        out_idx.extend(extra.tolist())
    return particles[np.array(out_idx[:n])].copy()


def resample(
    particles: np.ndarray,
    weights: np.ndarray,
    rng: np.random.Generator,
    method: str = "multinomial",
) -> np.ndarray:
    method = method.lower()
    if method == "systematic":
        return resample_systematic(particles, weights, rng)
    if method == "residual":
        return resample_residual(particles, weights, rng)
    return resample_multinomial(particles, weights, rng)


def estimate(particles: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """Estymata pozycji: średnia ważona (x, y) + średnia kątowa θ."""
    if weights is None:
        weights = np.ones(len(particles)) / len(particles)
    w = weights / weights.sum()
    xy = (particles[:, :2] * w[:, None]).sum(axis=0)
    th = np.arctan2(
        (np.sin(particles[:, 2]) * w).sum(),
        (np.cos(particles[:, 2]) * w).sum(),
    )
    return np.array([xy[0], xy[1], th])


class ParticleFilter2D:
    """Pełna pętla lokalizacji 2D: sense → normalize → resample → move."""

    def __init__(
        self,
        mapa: np.ndarray,
        n_particles: int = 400,
        seed: int = 42,
        p_hit: float = 0.85,
        sigma_d: float = 0.08,
        sigma_theta: float = np.deg2rad(8),
        resample_method: str = "multinomial",
    ):
        self.mapa = mapa
        self.n = n_particles
        self.rng = np.random.default_rng(seed)
        self.p_hit = float(np.clip(p_hit, 0.34, 0.99))
        self.sigma_d = max(0.0, float(sigma_d))
        self.sigma_theta = max(0.0, float(sigma_theta))
        self.resample_method = resample_method if resample_method in RESAMPLE_METHODS else "multinomial"
        self.particles = init_particles(mapa, n_particles, self.rng)
        self.weights = np.ones(n_particles) / n_particles
        free = np.argwhere(mapa != WALL)
        y0, x0 = free[len(free) // 3]
        self.robot = np.array([x0 + 0.5, y0 + 0.5, 0.0], dtype=float)

    def step(self) -> dict:
        """Jeden krok: sense → normalize → resample → move."""
        # --- sense ---
        pomiar = cell_type(self.mapa, self.robot[0], self.robot[1])
        if self.rng.random() > self.p_hit:
            others = [FREE, WALL, DOOR]
            others.remove(pomiar)
            pomiar = int(self.rng.choice(others))
        raw = sense_weights_raw(self.particles, pomiar, self.mapa, self.p_hit)

        # --- normalize ---
        self.weights = normalize_weights(raw)

        # estymata ze średniej ważonej (przed resamplingiem)
        est = estimate(self.particles, self.weights)
        err = float(np.linalg.norm(est[:2] - self.robot[:2]))

        # --- resample ---
        self.particles = resample(
            self.particles, self.weights, self.rng, method=self.resample_method
        )
        self.weights = np.ones(self.n) / self.n

        # --- move (robot + chmura) ---
        self.robot = move_particles(
            self.robot.reshape(1, 3),
            self.mapa,
            sigma_d=self.sigma_d,
            sigma_theta=self.sigma_theta,
            rng=self.rng,
            policy="robot",
        )[0]
        self.particles = move_particles(
            self.particles,
            self.mapa,
            sigma_d=self.sigma_d,
            sigma_theta=self.sigma_theta,
            rng=self.rng,
            policy="particles",
        )

        return {
            "robot": self.robot.copy(),
            "particles": self.particles.copy(),
            "weights": self.weights.copy(),
            "estimate": est,
            "pomiar": pomiar,
            "error": err,
        }
