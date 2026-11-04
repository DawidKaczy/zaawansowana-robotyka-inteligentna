"""
Demo wizualizacji dla ZADANIA 2 (kratka 5×5) — osobny plik.

Dane jak w Filtr_2D.ipynb:
  - mapa 5×5 (ściana / wolne / drzwi)
  - cząsteczki = (x, y) całkowite
  - sensor p_poprawny / p_bledny
  - resampling = ruletka multinomial (jedyny wariant)
  - ruch dyskretny BEZ szumu (prawo/dół/lewo/góra)

NIE korzysta z particle_filter_2d.py (to jest wersja z zadania 3).

Uruchomienie:
    python "Zaawansowana robotyka inteligentna/zadanie_2_filtr_2D/demo_filtr_2D_kratka.py"
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.colors import ListedColormap
from matplotlib.widgets import Button

SCIANA, WOLNE, DRZWI = 0, 1, 2
NAZWY = {SCIANA: "ściana", WOLNE: "wolne", DRZWI: "drzwi"}
AUTOPLAY_MS = (900, 550, 320, 180)

MAPA = np.array(
    [
        [SCIANA, SCIANA, SCIANA, SCIANA, SCIANA],
        [SCIANA, WOLNE, DRZWI, WOLNE, SCIANA],
        [SCIANA, WOLNE, SCIANA, WOLNE, SCIANA],
        [SCIANA, WOLNE, DRZWI, WOLNE, SCIANA],
        [SCIANA, SCIANA, SCIANA, SCIANA, SCIANA],
    ],
    dtype=int,
)

# trasa jak w notebooku (krok 14)
TRASA = [(1, 0), (1, 0), (0, 1), (0, 1), (-1, 0), (-1, 0)]
KIER = {(1, 0): "prawo", (-1, 0): "lewo", (0, 1): "dół", (0, -1): "góra"}

PHASE_TITLE = {
    "init": "KROK 0 — Inicjalizacja (zadanie 2)",
    "sense": "Faza SENSE — pomiar",
    "normalize": "Faza NORMALIZE — wagi / S",
    "resample": "Faza RESAMPLE — ruletka (multinomial)",
    "move": "Faza MOVE — ruch dyskretny (bez szumu)",
}


def wolne_komorki(mapa: np.ndarray) -> list[tuple[int, int]]:
    return [(x, y) for y in range(mapa.shape[0]) for x in range(mapa.shape[1]) if mapa[y, x] != SCIANA]


def idz(x: int, y: int, dx: int, dy: int, mapa: np.ndarray) -> tuple[int, int]:
    nx, ny = x + dx, y + dy
    if 0 <= nx < mapa.shape[1] and 0 <= ny < mapa.shape[0] and mapa[ny, nx] != SCIANA:
        return nx, ny
    return x, y


def sense_raw(cz: np.ndarray, pomiar: int, mapa: np.ndarray, p_hit: float) -> np.ndarray:
    p_miss = 1.0 - p_hit
    w = np.empty(len(cz), dtype=float)
    for i, (x, y) in enumerate(cz):
        w[i] = p_hit if mapa[y, x] == pomiar else p_miss
    return w


def resample_multinomial(cz: np.ndarray, w_prim: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    cdf = np.cumsum(w_prim)
    cdf[-1] = 1.0
    u = rng.random(len(cz))
    idx = np.clip(np.searchsorted(cdf, u, side="left"), 0, len(cz) - 1)
    return cz[idx].copy()


class DemoZadanie2:
    def __init__(self):
        self.mapa = MAPA.copy()
        self.n_particles = 12
        self.p_hit = 0.8  # jak p_poprawny w notebooku
        self.rng = np.random.default_rng(7)
        self.cmap = ListedColormap(["#333333", "#e8e8e8", "#f4a261"])

        self.history: list[dict] = []
        self.hist_i = 0
        self.cycle = 0
        self.trasa_i = 0
        self.pending_phase = "sense"
        self.raw_weights: np.ndarray | None = None
        self.pomiar = WOLNE
        self.autoplay = False
        self.speed_i = 1

        self._reset_state(seed=7)
        self._build_ui()
        self._push("init", self._opis_init())
        self._redraw()

    def _reset_state(self, seed: int | None = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        free = wolne_komorki(self.mapa)
        # dokładnie jak w Filtr_2D.ipynb (N=12 → estymata (1.9167, 2.0))
        start_nb = np.array(
            [
                [1, 1], [2, 1], [3, 1],
                [1, 2],         [3, 2],
                [1, 3], [2, 3], [3, 3],
                [1, 1], [2, 1], [3, 3], [1, 3],  # powtórki z notebooka
            ],
            dtype=int,
        )
        if self.n_particles <= len(start_nb):
            self.czasteczki = start_nb[: self.n_particles].copy()
        else:
            extra = [free[i % len(free)] for i in range(self.n_particles - len(start_nb))]
            self.czasteczki = np.vstack([start_nb, np.array(extra, dtype=int)])
        self.weights = np.ones(self.n_particles) / self.n_particles
        self.robot = np.array([1, 1], dtype=int)
        self.raw_weights = None
        self.pomiar = int(self.mapa[self.robot[1], self.robot[0]])
        self.cycle = 0
        self.trasa_i = 0
        self.pending_phase = "sense"

    # --- UI ---
    def _build_ui(self):
        self.fig = plt.figure(figsize=(12.5, 7.8))
        self.fig.canvas.manager.set_window_title("Zadanie 2 — demo kratka 5×5")
        self.fig.subplots_adjust(top=0.92, bottom=0.09)
        gs = self.fig.add_gridspec(
            3, 2, height_ratios=[3.0, 1.6, 0.5], width_ratios=[1.1, 1.0], hspace=0.4, wspace=0.3
        )
        self.ax = self.fig.add_subplot(gs[0, 0])
        self.ax_err = self.fig.add_subplot(gs[0, 1])
        self.ax_desc = self.fig.add_subplot(gs[1, :])
        self.ax_desc.axis("off")

        h, w = self.mapa.shape
        self.ax.imshow(
            self.mapa,
            cmap=self.cmap,
            origin="upper",
            vmin=0,
            vmax=2,
            extent=(-0.5, w - 0.5, h - 0.5, -0.5),
            interpolation="nearest",
        )
        self.ax.set_xticks(range(w))
        self.ax.set_yticks(range(h))
        self.ax.grid(True, color="#6c757d", lw=0.6, alpha=0.7)
        self.ax.set_xlim(-0.5, w - 0.5)
        self.ax.set_ylim(h - 0.5, -0.5)
        self.ax.set_xlabel("x")
        self.ax.set_ylabel("y")
        self.ax.set_aspect("equal")

        self.sc_part = self.ax.scatter([], [], s=80, c="#c1121f", alpha=0.75, label="cząsteczki", zorder=3)
        self.sc_robot = self.ax.scatter(
            [], [], s=180, c="#80ed99", edgecolors="k", zorder=5, label="robot"
        )
        self.sc_est = self.ax.scatter(
            [], [], s=140, c="#00b4d8", marker="x", zorder=6, label="estymata"
        )
        (self.line_err_seg,) = self.ax.plot([], [], color="#7b2cbf", lw=2, ls="--", zorder=4, label="błąd")
        handles, labels = self.ax.get_legend_handles_labels()
        self.fig.legend(handles, labels, loc="upper center", ncol=4, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 0.995))

        (self.line_err,) = self.ax_err.plot([], [], "o-", color="#1d3557", lw=1.8)
        self.ax_err.set_title("Błąd (|Δx|+|Δy|)")
        self.ax_err.set_xlabel("cykl MOVE")
        self.ax_err.set_ylabel("błąd")
        self.ax_err.grid(True, alpha=0.3)
        self.ax_err.set_xlim(0, 10)
        self.ax_err.set_ylim(0, 6)

        self.hud = self.ax_desc.text(
            0.01, 0.98, "", transform=self.ax_desc.transAxes, va="top", ha="left",
            fontsize=9, family="monospace",
            bbox=dict(boxstyle="round", facecolor="#eef2ff", edgecolor="#94a3b8"),
        )
        self.desc = self.ax_desc.text(
            0.01, 0.52, "", transform=self.ax_desc.transAxes, va="top", ha="left", fontsize=10
        )

        labels_btn = [
            ("Wstecz", self.on_back),
            ("Dalej", self.on_next),
            ("Auto/Pauza", self.on_toggle_auto),
            ("Tempo+", self.on_faster),
            ("Tempo-", self.on_slower),
            ("Reset", self.on_reset),
            ("N −", self.on_n_minus),
            ("N +", self.on_n_plus),
            ("Sensor−", self.on_sensor_minus),
            ("Sensor+", self.on_sensor_plus),
        ]
        self.buttons = []
        self.btn_auto = None
        n = len(labels_btn)
        width, gap = 0.085, 0.008
        total = n * width + (n - 1) * gap
        x0 = 0.5 - total / 2
        for i, (lab, cb) in enumerate(labels_btn):
            axb = self.fig.add_axes([x0 + i * (width + gap), 0.015, width, 0.045])
            color = "#d8f3dc" if lab == "Auto/Pauza" else "#e9ecef"
            btn = Button(axb, lab, color=color, hovercolor="#ced4da")
            btn.on_clicked(cb)
            self.buttons.append(btn)
            if lab == "Auto/Pauza":
                self.btn_auto = btn

        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.anim = FuncAnimation(
            self.fig, self._tick, interval=AUTOPLAY_MS[self.speed_i], blit=False, cache_frame_data=False
        )

    def _est(self) -> np.ndarray:
        return self.czasteczki.mean(axis=0)

    def _blad(self, est=None) -> float:
        if est is None:
            est = self._est()
        return float(abs(est[0] - self.robot[0]) + abs(est[1] - self.robot[1]))

    def _opis_init(self) -> str:
        return (
            "Zadanie 2 — mała kratka 5×5 (jak w Filtr_2D.ipynb).\n"
            f"• N={self.n_particles} cząsteczek (x, y) całkowite — BEZ kąta θ.\n"
            f"• Sensor: p_hit={self.p_hit:.2f} (w notebooku 0.8 / 0.2).\n"
            "• Resampling: tylko multinomial (ruletka CDF).\n"
            "• Ruch: dyskretny prawo/dół/lewo — BEZ szumu ruchu.\n\n"
            "Dalej → SENSE   |   Auto/Pauza / spacja = leci samo."
        )

    def _push(self, phase: str, opis: str):
        est = self._est()
        frame = {
            "phase": phase,
            "cycle": self.cycle,
            "robot": self.robot.copy(),
            "czasteczki": self.czasteczki.copy(),
            "weights": self.weights.copy(),
            "estimate": est.copy(),
            "pomiar": int(self.pomiar),
            "error": self._blad(est),
            "opis": opis,
            "pending": self.pending_phase,
            "trasa_i": self.trasa_i,
            "n": self.n_particles,
            "p_hit": self.p_hit,
        }
        if self.hist_i < len(self.history) - 1:
            self.history = self.history[: self.hist_i + 1]
        self.history.append(frame)
        self.hist_i = len(self.history) - 1

    def _restore(self, f: dict):
        self.robot = f["robot"].copy()
        self.czasteczki = f["czasteczki"].copy()
        self.weights = f["weights"].copy()
        self.pomiar = f["pomiar"]
        self.cycle = f["cycle"]
        self.pending_phase = f["pending"]
        self.trasa_i = f["trasa_i"]
        self.n_particles = f["n"]

    def advance(self):
        phase = self.pending_phase
        if phase == "sense":
            true_t = int(self.mapa[self.robot[1], self.robot[0]])
            ok = self.rng.random() <= self.p_hit
            if ok:
                self.pomiar = true_t
            else:
                others = [WOLNE, DRZWI, SCIANA]
                others.remove(true_t)
                self.pomiar = int(self.rng.choice(others))
            self.raw_weights = sense_raw(self.czasteczki, self.pomiar, self.mapa, self.p_hit)
            self.pending_phase = "normalize"
            self._push(
                "sense",
                f"SENSE — pomiar typu komórki pod robotem.\n"
                f"• Robot na {tuple(self.robot)} → prawdziwy typ: {NAZWY[true_t]}\n"
                f"• Pomiar = {NAZWY[self.pomiar]} ({'OK' if ok else 'błędny sensor'})\n"
                f"• p_hit={self.p_hit:.2f}: waga {self.p_hit:.2f} jeśli komórka cząsteczki = pomiar, "
                f"inaczej {1 - self.p_hit:.2f}.\n\nDalej → NORMALIZE.",
            )
        elif phase == "normalize":
            raw = self.raw_weights if self.raw_weights is not None else np.ones(len(self.czasteczki))
            S = float(raw.sum())
            self.weights = raw / S if S > 0 else np.ones(len(raw)) / len(raw)
            err = self._blad()
            est = self._est()
            self.pending_phase = "resample"
            self._push(
                "normalize",
                f"NORMALIZE — jak w notebooku krok 2.\n"
                f"• S = {S:.2f}\n"
                f"• w' = w / S  (suma ≈ 1)\n"
                f"• estymata (średnia) ≈ ({est[0]:.4f}, {est[1]:.4f})\n"
                f"• błąd = |Δx|+|Δy| ≈ {err:.4f}\n\nDalej → RESAMPLE (ruletka).",
            )
        elif phase == "resample":
            self.czasteczki = resample_multinomial(self.czasteczki, self.weights, self.rng)
            self.weights = np.ones(len(self.czasteczki)) / len(self.czasteczki)
            self.raw_weights = None
            self.pending_phase = "move"
            self._push(
                "resample",
                "RESAMPLE — multinomial / ruletka CDF (jedyny wariant w zadaniu 2).\n"
                "• Losowe u na [0,1) → indeks z CDF → powielenie dobrych hipotez.\n"
                "• Po resamplingiu wagi = 1/N.\n\n"
                "Dalej → MOVE (bez szumu).",
            )
        elif phase == "move":
            dx, dy = TRASA[self.trasa_i % len(TRASA)]
            nazwa = KIER[(dx, dy)]
            self.robot = np.array(idz(int(self.robot[0]), int(self.robot[1]), dx, dy, self.mapa))
            self.czasteczki = np.array(
                [idz(int(x), int(y), dx, dy, self.mapa) for x, y in self.czasteczki], dtype=int
            )
            self.trasa_i += 1
            self.cycle += 1
            self.pending_phase = "sense"
            err = self._blad()
            self._push(
                "move",
                f"MOVE — wszyscy dostają tę samą komendę: {nazwa} (dx={dx}, dy={dy}).\n"
                "• Brak szumu ruchu (różnica vs zadanie 3).\n"
                f"• Robot teraz: {tuple(self.robot)} → {NAZWY[int(self.mapa[self.robot[1], self.robot[0]])]}\n"
                f"• Błąd ≈ {err:.2f}\n\n"
                f"Koniec cyklu {self.cycle}. Dalej → znowu SENSE.",
            )
        self._redraw()

    def _jitter(self, pts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        j = (rng.random(pts.shape) - 0.5) * 0.35
        return pts.astype(float) + j

    def _redraw(self):
        f = self.history[self.hist_i]
        rng = np.random.default_rng(self.hist_i + 99)
        pts = self._jitter(f["czasteczki"], rng)
        self.sc_part.set_offsets(pts)
        self.sc_robot.set_offsets([f["robot"]])
        est = f["estimate"]
        self.sc_est.set_offsets([est])
        self.line_err_seg.set_data([f["robot"][0], est[0]], [f["robot"][1], est[1]])

        moves = [x for x in self.history[: self.hist_i + 1] if x["phase"] == "move"]
        if moves:
            errs = [x["error"] for x in moves]
            self.line_err.set_data(np.arange(1, len(errs) + 1), errs)
            self.ax_err.set_xlim(0, max(10, len(errs) + 2))
            self.ax_err.set_ylim(0, max(3.0, max(errs) * 1.2 + 0.5))
        else:
            self.line_err.set_data([], [])

        play = "AUTOPLAY" if self.autoplay else "PAUZA"
        self.ax.set_title(f"{PHASE_TITLE[f['phase']]}  |  cykl={f['cycle']}")
        self.hud.set_text(
            f"[{play}] historia {self.hist_i}/{len(self.history)-1}   tempo={AUTOPLAY_MS[self.speed_i]} ms\n"
            f"N={self.n_particles}   p_hit={self.p_hit:.2f}   resample=multinomial   szum=BRAK\n"
            f"est=({f['estimate'][0]:.4f}, {f['estimate'][1]:.4f})   "
            f"pomiar={NAZWY.get(f['pomiar'], f['pomiar'])}   błąd≈{f['error']:.4f}   "
            f"następna={self.pending_phase}"
        )
        self.desc.set_text(f["opis"])
        self.fig.canvas.draw_idle()

    def _tick(self, _):
        if self.autoplay:
            self.on_next()
        return []

    def on_next(self, _=None):
        if self.hist_i < len(self.history) - 1:
            self.hist_i += 1
            self._restore(self.history[self.hist_i])
            self._redraw()
        else:
            self.advance()

    def on_back(self, _=None):
        self.autoplay = False
        self._sync_auto()
        if self.hist_i > 0:
            self.hist_i -= 1
            self._restore(self.history[self.hist_i])
            self._redraw()

    def on_toggle_auto(self, _=None):
        self.autoplay = not self.autoplay
        self._sync_auto()
        self._redraw()

    def _sync_auto(self):
        if self.btn_auto is None:
            return
        self.btn_auto.label.set_text("Pauza" if self.autoplay else "Auto")
        self.btn_auto.color = "#ffd6a5" if self.autoplay else "#d8f3dc"

    def on_faster(self, _=None):
        self.speed_i = min(len(AUTOPLAY_MS) - 1, self.speed_i + 1)
        if self.anim.event_source:
            self.anim.event_source.interval = AUTOPLAY_MS[self.speed_i]
        self._redraw()

    def on_slower(self, _=None):
        self.speed_i = max(0, self.speed_i - 1)
        if self.anim.event_source:
            self.anim.event_source.interval = AUTOPLAY_MS[self.speed_i]
        self._redraw()

    def on_reset(self, _=None):
        self.autoplay = False
        self._sync_auto()
        self.history.clear()
        self.hist_i = 0
        self._reset_state(seed=int(self.rng.integers(0, 10_000)))
        self._push("init", self._opis_init())
        self._redraw()

    def on_n_plus(self, _=None):
        self.n_particles = min(48, self.n_particles + 4)
        self.on_reset()

    def on_n_minus(self, _=None):
        self.n_particles = max(4, self.n_particles - 4)
        self.on_reset()

    def on_sensor_plus(self, _=None):
        self.p_hit = min(0.95, round(self.p_hit + 0.05, 2))
        self._redraw()

    def on_sensor_minus(self, _=None):
        self.p_hit = max(0.55, round(self.p_hit - 0.05, 2))
        self._redraw()

    def on_key(self, event):
        k = event.key
        if k in (" ", "space"):
            self.on_toggle_auto()
        elif k in ("right", "n"):
            self.autoplay = False
            self._sync_auto()
            self.on_next()
        elif k in ("left", "p"):
            self.on_back()
        elif k in ("up",):
            self.on_faster()
        elif k in ("down",):
            self.on_slower()
        elif k == "r":
            self.on_reset()
        elif k in ("+", "="):
            self.on_n_plus()
        elif k in ("-", "_"):
            self.on_n_minus()
        elif k == "]":
            self.on_sensor_plus()
        elif k == "[":
            self.on_sensor_minus()
        elif k in ("q", "escape"):
            plt.close(self.fig)

    def run(self):
        plt.show()


if __name__ == "__main__":
    DemoZadanie2().run()
