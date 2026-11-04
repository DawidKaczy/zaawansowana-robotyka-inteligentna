# Zadanie 3 — Demo krok po kroku (opis działania)

## Scenariusz (z PDF)

1. Wczytaj mapę 2D, wygeneruj rozkład cząsteczek.
2. W pętli: **sense → normalize → resample → move**.
3. Po każdym kroku: chmura `(x, y)` + estymata (średnia ważona).
4. Zmiana parametrów: **N**, dokładność sensora, wariant resamplingu, szum ruchu.

## Uruchomienie

```text
python "Zaawansowana robotyka inteligentna/zadanie_3_demo/demo_filtr_2D.py"
```

(aktywne `.venv`, okno matplotlib)

## Jak korzystać (od kroku 0)

Start = **KROK 0** (mapa + chmura), **pauza** — samo nie leci, dopóki nie włączysz Auto.

| Przycisk / klawisz | Działanie |
|--------------------|-----------|
| **Auto/Pauza** / `spacja` | autoplay włącz / wyłącz |
| **Tempo+ / Tempo−** / `↑` `↓` | szybciej / wolniej autoplay |
| **Dalej** / `→` / `n` | następna faza (ręcznie) |
| **Wstecz** / `←` / `p` | poprzednia faza (historia) |
| **Reset** / `r` | nowa chmura od kroku 0 |
| **N + / N −** / `+` `-` | liczba cząsteczek (z resetem) |
| **Sensor+ / Sensor−** / `]` `[` | dokładność sensora `p_hit` |
| **Szum+ / Szum−** / `.` `,` | poziom szumu ruchu |
| **Resample** / `v` | multinomial → systematic → residual |
| `q` | wyjście |

### Kolejność faz (przeklikujesz jedną po drugiej)

```text
0 INIT  →  SENSE  →  NORMALIZE  →  RESAMPLE  →  MOVE  →  SENSE  →  …
```

Na dole okna: **pasek statusu** (N, p_hit, szum, resampling, błąd) + **opis fazy** po polsku.

## Co widać

| Element | Znaczenie |
|---------|-----------|
| Lewy panel | mapa + siatka + czerwona chmura + zielony robot (ze strzałką θ) + cyan estymata + tory |
| Prawy panel | błąd lokalizacji po kolejnych cyklach MOVE |
| Legenda | nad oknem (nie na mapie) |
| Dolny tekst | status parametrów + wyjaśnienie bieżącej fazy |

## Parametry z treści zadania

- **N** — ile hipotez; za mało → słaba lokalizacja; za dużo → wolniej, stabilniej.
- **Dokładność sensora (`p_hit`)** — jak często pomiar jest prawdziwy.
- **Wariant resamplingu** — multinomial (ruletka jak w zad. 2) / systematic / residual.
- **Szum ruchu** — losowy błąd odometrii przy MOVE (tego nie ma w zad. 2).

## Związek z zadaniem 2

W `Filtr_2D.ipynb` liczyłeś wagi / S / ruletkę ręcznie na małej siatce.  
Tu ten sam cykl widać na większej mapie, faza po fazie, z θ, szumem ruchu i przełączaniem resamplingu.
