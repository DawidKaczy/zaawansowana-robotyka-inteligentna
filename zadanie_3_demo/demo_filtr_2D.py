"""
Zadanie 3 — Demo krok po kroku: filtr cząsteczkowy 2D

Scenariusz z PDF:
  1. Wczytaj mapę 2D, wygeneruj rozkład cząsteczek.
  2. W pętli: sense → normalize → resample → move.
  3. Po każdym kroku: chmura (x,y) + estymata (średnia ważona).
  4. Zmiana parametrów: N, dokładność sensora, wariant resamplingu, szum ruchu.

Uruchomienie:
    python "Zaawansowana robotyka inteligentna/zadanie_3_demo/demo_filtr_2D.py"

Start = KROK 0 (mapa + chmura). Dalej klikasz „Dalej” / → albo włącz Autoplay.
Fazy: sense → normalize → resample → move → sense → …
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.colors import ListedColormap
from matplotlib.patches import FancyArrowPatch
from matplotlib.widgets import Button

AUTOPLAY_MS = (900, 550, 320, 180)  # wolniej → szybciej

ROOT = Path(__file__).resolve().parent
LIB = ROOT.parent / "zadanie_2_filtr_2D"
for p in (ROOT, LIB):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from particle_filter_2d import (  # noqa: E402
    DOOR,
    FREE,
    NAZWY,
    RESAMPLE_METHODS,
    WALL,
    cell_type,
    estimate,
    init_particles,
    make_default_map,
    move_particles,
    normalize_weights,
    resample,
    sense_weights_raw,
)

# kolejność faz w jednym cyklu filtru
PHASES = ("init", "sense", "normalize", "resample", "move")

PHASE_TITLE = {
    "init": "KROK 0 — Inicjalizacja",
    "sense": "Faza SENSE — pomiar",
    "normalize": "Faza NORMALIZE — wagi → prawdopodobieństwa",
    "resample": "Faza RESAMPLE — ruletka",
    "move": "Faza MOVE — ruch robota i chmury",
}


class StepDemo:
    def __init__(self):
        # --- parametry z treści zadania ---
        self.n_particles = 400
        self.p_hit = 0.85
        self.noise_level = 1.0
        self.resample_i = 0
        self.base_sigma_d = 0.08
        self.base_sigma_theta = np.deg2rad(8)

        self.mapa = make_default_map(20, 20)
        self.rng = np.random.default_rng(3)
        self.cmap = ListedColormap(["#ececec", "#2b2b2b", "#e09f3e"])

        self.history: list[dict] = []
        self.hist_i = 0
        self.max_history = 500

        # stan roboczy (bieżący)
        self.particles = init_particles(self.mapa, self.n_particles, self.rng)
        self.weights = np.ones(self.n_particles) / self.n_particles
        free = np.argwhere(self.mapa != WALL)
        y0, x0 = free[len(free) // 3]
        self.robot = np.array([x0 + 0.5, y0 + 0.5, 0.0], dtype=float)
        self.raw_weights: np.ndarray | None = None
        self.pomiar = int(cell_type(self.mapa, self.robot[0], self.robot[1]))
        self.cycle = 0  # numer pełnego cyklu sense..move
        self.pending_phase = "sense"  # następna faza po init
        self.autoplay = False
        self.speed_i = 1  # indeks w AUTOPLAY_MS

        self._build_ui()
        self._push_snapshot(
            phase="init",
            opis=self._opis_init(),
        )
        self._redraw()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.fig = plt.figure(figsize=(13.5, 8.5))
        self.fig.canvas.manager.set_window_title("Zadanie 3 — filtr 2D (krok po kroku)")
        self.fig.subplots_adjust(top=0.92, bottom=0.08)
        gs = self.fig.add_gridspec(
            3, 2, height_ratios=[3.2, 1.7, 0.55], width_ratios=[1.35, 1.0], hspace=0.40, wspace=0.30
        )
        self.ax = self.fig.add_subplot(gs[0, 0])
        self.ax_err = self.fig.add_subplot(gs[0, 1])
        self.ax_desc = self.fig.add_subplot(gs[1, :])
        self.ax_desc.axis("off")
        self.ax_btns = self.fig.add_subplot(gs[2, :])
        self.ax_btns.axis("off")

        h, w = self.mapa.shape
        # extent: komórka i zajmuje [i, i+1) — tak samo jak floor(x) w filtrze
        self.ax.imshow(
            self.mapa,
            cmap=self.cmap,
            origin="lower",
            vmin=0,
            vmax=2,
            extent=(0, w, 0, h),
            interpolation="nearest",
        )
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.set_xticks(np.arange(0, w + 1, 1))
        self.ax.set_yticks(np.arange(0, h + 1, 1))
        self.ax.grid(True, which="major", color="#6c757d", lw=0.45, alpha=0.55)
        self.ax.set_axisbelow(False)  # siatka nad mapą, pod punktami
        self.sc_part = self.ax.scatter([], [], s=8, c="#c1121f", alpha=0.45, label="cząsteczki", zorder=3)
        self.sc_robot = self.ax.scatter(
            [], [], s=130, c="#80ed99", edgecolors="k", zorder=5, label="robot"
        )
        self.sc_est = self.ax.scatter(
            [], [], s=110, c="#00b4d8", marker="x", zorder=6, label="estymata"
        )
        (self.line_robot,) = self.ax.plot([], [], color="#80ed99", lw=1.6, alpha=0.85, label="tor robota", zorder=4)
        (self.line_est,) = self.ax.plot(
            [], [], color="#00b4d8", lw=1.3, alpha=0.85, ls="--", label="tor estymaty", zorder=4
        )
        self.arrow = None
        self.ax.set_xlabel("x")
        self.ax.set_ylabel("y")
        self.ax.set_aspect("equal")
        # legenda nad całą figurą — nie zasłania mapy
        handles, labels = self.ax.get_legend_handles_labels()
        self.fig.legend(
            handles,
            labels,
            loc="upper center",
            ncol=5,
            fontsize=8,
            frameon=False,
            bbox_to_anchor=(0.5, 0.995),
        )

        (self.line_err,) = self.ax_err.plot([], [], color="#1d3557", lw=1.8)
        self.ax_err.set_title("Jakość lokalizacji (błąd)")
        self.ax_err.set_xlabel("nr cyklu")
        self.ax_err.set_ylabel("błąd [komórki]")
        self.ax_err.grid(True, alpha=0.3)
        self.ax_err.set_xlim(0, 20)
        self.ax_err.set_ylim(0, 12)

        # status + opis POD mapą (mapa zostaje czysta)
        self.hud = self.ax_desc.text(
            0.01,
            0.98,
            "",
            transform=self.ax_desc.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            family="monospace",
            bbox=dict(boxstyle="round", facecolor="#eef2ff", edgecolor="#94a3b8", alpha=1.0),
        )
        self.desc_text = self.ax_desc.text(
            0.01,
            0.55,
            "",
            transform=self.ax_desc.transAxes,
            va="top",
            ha="left",
            fontsize=10,
            family="sans-serif",
            wrap=True,
        )

        # przyciski
        labels = [
            ("Wstecz", self.on_back),
            ("Dalej", self.on_next),
            ("Auto/Pauza", self.on_toggle_autoplay),
            ("Tempo+", self.on_faster),
            ("Tempo-", self.on_slower),
            ("Reset", self.on_reset),
            ("N −", self.on_n_minus),
            ("N +", self.on_n_plus),
            ("Sensor−", self.on_sensor_minus),
            ("Sensor+", self.on_sensor_plus),
            ("Szum−", self.on_noise_minus),
            ("Szum+", self.on_noise_plus),
            ("Resample", self.on_resample_cycle),
        ]
        self.buttons = []
        self.btn_auto = None
        n = len(labels)
        width = 0.068
        gap = 0.006
        total = n * width + (n - 1) * gap
        x0 = 0.5 - total / 2
        for i, (lab, cb) in enumerate(labels):
            axb = self.fig.add_axes([x0 + i * (width + gap), 0.015, width, 0.045])
            color = "#d8f3dc" if lab == "Auto/Pauza" else "#e9ecef"
            btn = Button(axb, lab, color=color, hovercolor="#ced4da")
            btn.on_clicked(cb)
            self.buttons.append(btn)
            if lab == "Auto/Pauza":
                self.btn_auto = btn

        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.anim = FuncAnimation(
            self.fig,
            self._autoplay_tick,
            interval=AUTOPLAY_MS[self.speed_i],
            blit=False,
            cache_frame_data=False,
        )

    # -------------------------------------------------------------- stan / historia
    def _sigma(self):
        return self.base_sigma_d * self.noise_level, self.base_sigma_theta * self.noise_level

    def _est(self):
        return estimate(self.particles, self.weights)

    def _error(self, est=None):
        if est is None:
            est = self._est()
        return float(np.linalg.norm(est[:2] - self.robot[:2]))

    def _opis_init(self) -> str:
        return (
            "① Wczytano mapę 2D (szare=wolne, czarne=ściana, pomarańcz=drzwi).\n"
            f"② Wygenerowano N={self.n_particles} cząsteczek — hipotezy pozycji (x, y, θ) "
            "na polach niebędących ścianą.\n"
            "③ Zielony punkt = prawdziwy robot (filtr go nie zna — widzi tylko pomiary).\n"
            "④ Cyan X = estymata = średnia ważona chmury (na starcie wagi równe).\n\n"
            "Kliknij DALEJ (jedna faza) albo Auto/Pauza / spacja (leci samo).\n"
            "Parametry: N, sensor, szum, resample — przyciski na dole."
        )

    def _opis_sense(self, pomiar: int, hit_ok: bool) -> str:
        ok = "poprawny" if hit_ok else "BŁĘDNY (szum sensora!)"
        return (
            f"SENSE — robot „patrzy” na typ komórki pod sobą.\n"
            f"• Prawdziwy typ / pomiar: {NAZWY[pomiar]}  ({ok})\n"
            f"• Dokładność sensora p_hit = {self.p_hit:.2f} "
            f"(z prawdopodobieństwem 1−p_hit pomiar jest zły).\n"
            f"• Każda cząsteczka dostaje surową wagę: p_hit jeśli jej komórka = pomiar, "
            f"inaczej (1−p_hit)/2.\n\n"
            "Dalej → NORMALIZE (podzielimy wagi przez sumę S)."
        )

    def _opis_normalize(self, S: float, err: float) -> str:
        return (
            "NORMALIZE — z surowych wag robimy rozkład prawdopodobieństwa.\n"
            f"• S = suma surowych wag = {S:.2f}\n"
            f"• w'ᵢ = wᵢ / S   (suma w' = 1)\n"
            f"• Estymata = średnia WAŻONA pozycji → błąd względem robota ≈ {err:.2f} komórki.\n"
            "  (cyan X przesuwa się w stronę hipotez z dużą wagą)\n\n"
            "Dalej → RESAMPLE (ruletka powieli dobre hipotezy)."
        )

    def _opis_resample(self) -> str:
        method = RESAMPLE_METHODS[self.resample_i]
        return (
            "RESAMPLE — ruletka według wag w'.\n"
            f"• Wariant: {method}\n"
            "  – multinomial = klasyczna ruletka (jak w zadaniu 1)\n"
            "  – systematic = równomierne punkty na [0,1)\n"
            "  – residual = część klonów na sztywno + reszta losowo\n"
            "• Hipotezy z dużą wagą dostają wiele kopii, słabe znikają.\n"
            "• Po resamplingiu wagi wracają do równych 1/N.\n\n"
            "Dalej → MOVE (robot i chmura jadą z szumem)."
        )

    def _opis_move(self, err: float) -> str:
        sd, st = self._sigma()
        return (
            "MOVE — ta sama komenda ruchu dla robota i każdej cząsteczki + szum.\n"
            f"• Poziom szumu ruchu ×{self.noise_level:.2f}  "
            f"(σ_d≈{sd:.3f}, σ_θ≈{np.rad2deg(st):.1f}°)\n"
            "• Szum = losowy błąd odometrii (nie jedziesz idealnie prosto).\n"
            f"• Po ruchu błąd estymaty (na razie ze starych wag) / pozycja robota się zmienia.\n"
            f"  Aktualny błąd pozycji chmury vs robot ≈ {err:.2f}.\n\n"
            f"Koniec cyklu nr {self.cycle}. Dalej → znowu SENSE (kolejny pomiar)."
        )

    def _push_snapshot(self, phase: str, opis: str, **extra):
        est = self._est()
        frame = {
            "phase": phase,
            "cycle": self.cycle,
            "robot": self.robot.copy(),
            "particles": self.particles.copy(),
            "weights": self.weights.copy(),
            "raw": None if self.raw_weights is None else self.raw_weights.copy(),
            "estimate": est.copy(),
            "pomiar": int(self.pomiar),
            "error": self._error(est),
            "opis": opis,
            "pending_phase": self.pending_phase,
            "n": self.n_particles,
            "p_hit": self.p_hit,
            "noise": self.noise_level,
            "resample_i": self.resample_i,
            **extra,
        }
        if self.hist_i < len(self.history) - 1:
            self.history = self.history[: self.hist_i + 1]
        self.history.append(frame)
        if len(self.history) > self.max_history:
            drop = len(self.history) - self.max_history
            self.history = self.history[drop:]
            self.hist_i = max(0, self.hist_i - drop)
        self.hist_i = len(self.history) - 1

    def _restore(self, frame: dict):
        self.robot = frame["robot"].copy()
        self.particles = frame["particles"].copy()
        self.weights = frame["weights"].copy()
        self.raw_weights = None if frame["raw"] is None else frame["raw"].copy()
        self.pomiar = frame["pomiar"]
        self.cycle = frame["cycle"]
        self.pending_phase = frame["pending_phase"]
        self.n_particles = frame["n"]
        # parametry UI zostawiamy aktualne — snapshot trzyma stan chmury

    # -------------------------------------------------------------- fazy
    def advance_phase(self):
        """Wykonaj następną fazę (sense → normalize → resample → move → …)."""
        phase = self.pending_phase

        if phase == "sense":
            true_t = cell_type(self.mapa, self.robot[0], self.robot[1])
            hit_ok = self.rng.random() <= self.p_hit
            if hit_ok:
                self.pomiar = true_t
            else:
                others = [FREE, WALL, DOOR]
                others.remove(true_t)
                self.pomiar = int(self.rng.choice(others))
            self.raw_weights = sense_weights_raw(
                self.particles, self.pomiar, self.mapa, self.p_hit
            )
            self.pending_phase = "normalize"
            self._push_snapshot(phase="sense", opis=self._opis_sense(self.pomiar, hit_ok))

        elif phase == "normalize":
            raw = self.raw_weights if self.raw_weights is not None else np.ones(self.n_particles)
            S = float(raw.sum())
            self.weights = normalize_weights(raw)
            err = self._error()
            self.pending_phase = "resample"
            self._push_snapshot(phase="normalize", opis=self._opis_normalize(S, err), S=S)

        elif phase == "resample":
            method = RESAMPLE_METHODS[self.resample_i]
            self.particles = resample(self.particles, self.weights, self.rng, method=method)
            self.weights = np.ones(len(self.particles)) / len(self.particles)
            self.raw_weights = None
            self.pending_phase = "move"
            self._push_snapshot(phase="resample", opis=self._opis_resample())

        elif phase == "move":
            sd, st = self._sigma()
            self.robot = move_particles(
                self.robot.reshape(1, 3),
                self.mapa,
                sigma_d=sd,
                sigma_theta=st,
                rng=self.rng,
                policy="robot",
            )[0]
            self.particles = move_particles(
                self.particles,
                self.mapa,
                sigma_d=sd,
                sigma_theta=st,
                rng=self.rng,
                policy="particles",
            )
            self.cycle += 1
            self.pending_phase = "sense"
            err = self._error()
            self._push_snapshot(phase="move", opis=self._opis_move(err))

        self._redraw()

    def go_back(self):
        if self.hist_i > 0:
            self.hist_i -= 1
            self._restore(self.history[self.hist_i])
            self._redraw()

    def reset(self):
        self.rng = np.random.default_rng(int(np.random.randint(0, 10_000)))
        self.particles = init_particles(self.mapa, self.n_particles, self.rng)
        self.weights = np.ones(self.n_particles) / self.n_particles
        free = np.argwhere(self.mapa != WALL)
        y0, x0 = free[len(free) // 3]
        self.robot = np.array([x0 + 0.5, y0 + 0.5, 0.0], dtype=float)
        self.raw_weights = None
        self.pomiar = int(cell_type(self.mapa, self.robot[0], self.robot[1]))
        self.cycle = 0
        self.pending_phase = "sense"
        self.history.clear()
        self.hist_i = 0
        self._push_snapshot(phase="init", opis=self._opis_init())
        self._redraw()

    # -------------------------------------------------------------- rysowanie
    def _redraw(self):
        frame = self.history[self.hist_i]
        parts = frame["particles"]
        robot = frame["robot"]
        est = frame["estimate"]

        self.sc_part.set_offsets(parts[:, :2])
        self.sc_robot.set_offsets([robot[:2]])
        self.sc_est.set_offsets([est[:2]])

        # tory: po zakończonych cyklach MOVE
        moves = [f for f in self.history[: self.hist_i + 1] if f["phase"] == "move"]
        if moves:
            rx = [f["robot"][0] for f in moves]
            ry = [f["robot"][1] for f in moves]
            ex = [f["estimate"][0] for f in moves]
            ey = [f["estimate"][1] for f in moves]
            self.line_robot.set_data(rx, ry)
            self.line_est.set_data(ex, ey)
            errs = [f["error"] for f in moves]
            self.line_err.set_data(np.arange(1, len(errs) + 1), errs)
            self.ax_err.set_xlim(0, max(20, len(errs) + 3))
            self.ax_err.set_ylim(0, max(3.0, max(errs) * 1.2))
        else:
            self.line_robot.set_data([], [])
            self.line_est.set_data([], [])
            self.line_err.set_data([], [])

        if self.arrow is not None:
            self.arrow.remove()
        x, y, th = robot
        self.arrow = FancyArrowPatch(
            (x, y),
            (x + 0.9 * np.cos(th), y + 0.9 * np.sin(th)),
            arrowstyle="-|>",
            mutation_scale=14,
            color="#1b4332",
            lw=2,
            zorder=7,
        )
        self.ax.add_patch(self.arrow)

        method = RESAMPLE_METHODS[self.resample_i]
        title = PHASE_TITLE.get(frame["phase"], frame["phase"])
        self.ax.set_title(f"{title}   |   cykl={frame['cycle']}")
        play = "AUTOPLAY" if self.autoplay else "PAUZA"
        tempo = AUTOPLAY_MS[self.speed_i]
        self.hud.set_text(
            f"[{play}] historia {self.hist_i}/{len(self.history)-1}   tempo={tempo} ms   |   "
            f"N={self.n_particles}   p_hit={self.p_hit:.2f}   "
            f"szum×{self.noise_level:.2f}   resample={method}\n"
            f"pomiar={NAZWY.get(frame['pomiar'], frame['pomiar'])}   "
            f"błąd≈{frame['error']:.2f}   następna: {self.pending_phase}   "
            f"(spacja=auto  ←→=krok)"
        )
        self.desc_text.set_text(frame["opis"])
        self.fig.canvas.draw_idle()

    def _autoplay_tick(self, _frame):
        if self.autoplay:
            self.on_next()
        return []

    def _sync_auto_button(self):
        if self.btn_auto is None:
            return
        if self.autoplay:
            self.btn_auto.label.set_text("Pauza")
            self.btn_auto.color = "#ffd6a5"
            self.btn_auto.hovercolor = "#ffb703"
        else:
            self.btn_auto.label.set_text("Auto")
            self.btn_auto.color = "#d8f3dc"
            self.btn_auto.hovercolor = "#95d5b2"
        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------- handlery
    def on_next(self, _event=None):
        # jeśli jesteśmy w środku historii — idź do przodu po snapshotach
        if self.hist_i < len(self.history) - 1:
            self.hist_i += 1
            self._restore(self.history[self.hist_i])
            self._redraw()
        else:
            self.advance_phase()

    def on_back(self, _event=None):
        self.autoplay = False
        self._sync_auto_button()
        self.go_back()

    def on_toggle_autoplay(self, _event=None):
        self.autoplay = not self.autoplay
        self._sync_auto_button()
        self._redraw()

    def on_faster(self, _event=None):
        self.speed_i = min(len(AUTOPLAY_MS) - 1, self.speed_i + 1)
        if self.anim.event_source is not None:
            self.anim.event_source.interval = AUTOPLAY_MS[self.speed_i]
        self._redraw()

    def on_slower(self, _event=None):
        self.speed_i = max(0, self.speed_i - 1)
        if self.anim.event_source is not None:
            self.anim.event_source.interval = AUTOPLAY_MS[self.speed_i]
        self._redraw()

    def on_reset(self, _event=None):
        self.autoplay = False
        self._sync_auto_button()
        self.reset()

    def on_n_plus(self, _event=None):
        self.n_particles = min(2000, self.n_particles + 100)
        self.reset()

    def on_n_minus(self, _event=None):
        self.n_particles = max(50, self.n_particles - 100)
        self.reset()

    def on_sensor_plus(self, _event=None):
        self.p_hit = min(0.99, round(self.p_hit + 0.05, 2))
        self._redraw()

    def on_sensor_minus(self, _event=None):
        self.p_hit = max(0.40, round(self.p_hit - 0.05, 2))
        self._redraw()

    def on_noise_plus(self, _event=None):
        self.noise_level = min(4.0, round(self.noise_level + 0.25, 2))
        self._redraw()

    def on_noise_minus(self, _event=None):
        self.noise_level = max(0.0, round(self.noise_level - 0.25, 2))
        self._redraw()

    def on_resample_cycle(self, _event=None):
        self.resample_i = (self.resample_i + 1) % len(RESAMPLE_METHODS)
        self._redraw()

    def on_key(self, event):
        key = event.key
        if key in (" ", "space"):
            self.on_toggle_autoplay()
        elif key in ("right", "n"):
            self.autoplay = False
            self._sync_auto_button()
            self.on_next()
        elif key in ("left", "p"):
            self.on_back()
        elif key in ("up",):
            self.on_faster()
        elif key in ("down",):
            self.on_slower()
        elif key == "r":
            self.on_reset()
        elif key in ("+", "="):
            self.on_n_plus()
        elif key in ("-", "_"):
            self.on_n_minus()
        elif key == "]":
            self.on_sensor_plus()
        elif key == "[":
            self.on_sensor_minus()
        elif key == ".":
            self.on_noise_plus()
        elif key == ",":
            self.on_noise_minus()
        elif key == "v":
            self.on_resample_cycle()
        elif key in ("q", "escape"):
            plt.close(self.fig)

    def run(self):
        plt.show()


if __name__ == "__main__":
    StepDemo().run()
