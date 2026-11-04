# Demo zadania 2 — kratka 5×5

Osobna wizualizacja (jak zadanie 3), ale na danych z `Filtr_2D.ipynb`.

## Uruchomienie

```text
python "Zaawansowana robotyka inteligentna/zadanie_2_filtr_2D/demo_filtr_2D_kratka.py"
```

## Co jest jak w notebooku

- mapa 5×5 (ściana / wolne / drzwi)
- cząsteczki `(x, y)` — bez θ
- sensor `p_hit` (domyślnie 0.8)
- resampling **tylko multinomial** (ruletka)
- ruch dyskretny **bez szumu** (trasa: prawo → prawo → dół → dół → lewo → lewo)
- błąd = `|Δx|+|Δy|`

## Sterowanie

Jak w demie zadania 3: Dalej / Wstecz / Auto / Tempo / Reset / N / Sensor  
(`spacja`, `←→`, `↑↓`, `r`, `+-`, `[]`, `q`)

Nie ma przycisku „Szum” ani przełączania resamplingu — w zadaniu 2 ich nie ma.
