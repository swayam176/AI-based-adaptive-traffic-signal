# AI-Based Adaptive Traffic Management System

A real-time four-way traffic intersection simulation with **Fixed-Time vs AI Adaptive** signal control comparison, live analytics dashboard, and CSV export.

---

## Features

| Feature | Description |
|---|---|
| **Four-way intersection** | Moving cars, buses, trucks, bikes with turning logic |
| **AI Adaptive Controller** | Dynamic green time based on waiting vehicle counts + starvation-prevention fairness |
| **Fixed-Time Controller** | Traditional round-robin, 20 s fixed green per direction |
| **Fair Comparison** | Identical traffic scenario (seed 42) replayed for both modes |
| **Live Analytics Panel** | Waiting time, queue length, throughput, per-direction breakdown |
| **Comparison Dashboard** | Side-by-side results table with percentage improvement |
| **CSV Export** | Summary CSV + time-series CSV saved to `results/` folder |

---

## Requirements

```
Python 3.10+
pygame
```

Install pygame if needed:
```bash
pip install pygame
```

---

## How to Launch

```bash
cd turns
python simulation.py
```

---

## Workflow: Running a Comparison

1. **Launch** — the Mode Selection screen appears.
2. **Select Fixed-Time Mode** → click **Start Simulation** → wait 120 s for the run to complete automatically.
3. Press **Back (Esc)** or the Back button to return to the menu.
4. **Select AI Adaptive Mode** → click **Start Simulation** → wait 120 s.
5. Click **Comparison Results** or press **Back** to the menu and click **Comparison Results**.
6. The results table shows both modes side by side with improvement percentages.

Both runs use **identical vehicle arrivals** (scenario seed 42), so the comparison is fair.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Pause / Resume |
| `R` | Reset to menu |
| `1` | Switch to Fixed-Time Mode (safe at green boundary) |
| `2` | Switch to AI Adaptive Mode (safe at green boundary) |
| `A` | Open Analytics Dashboard |
| `Esc` | Return to previous screen / exit |

---

## Buttons (Simulation Screen)

| Button | Action |
|---|---|
| Pause / Resume | Freeze / unfreeze simulation |
| Reset | Return to menu, clear all state |
| Fixed-Time (1) | Restart with fixed-time controller |
| AI Adaptive (2) | Restart with AI adaptive controller |
| Analytics (A) | Open live analytics dashboard |
| Results | Open fixed vs AI comparison table |
| Export CSV | Save summary + time-series CSVs to `results/` |
| Back (Esc) | Return to menu |

---

## Exporting Analytics

Click **Export CSV** during or after a run. Two files are saved to `results/`:

- `summary_<timestamp>.csv` — one row per completed mode, all key metrics
- `timeseries_<timestamp>.csv` — queue lengths and signal states sampled every 2 seconds

---

## Configuration (top of `simulation.py`)

| Constant | Default | Description |
|---|---|---|
| `FIXED_GREEN` | 20 s | Green duration for fixed-time mode |
| `MIN_GREEN` | 8 s | AI minimum green time |
| `MAX_GREEN` | 40 s | AI maximum green time |
| `PER_VEHICLE_SEC` | 2 s | Extra green per waiting vehicle |
| `SIM_DURATION` | 120 s | Duration of each test run |
| `SCENARIO_SEED` | 42 | Random seed for deterministic vehicle spawn replay |
| `defaultYellow` | 5 s | Yellow phase duration (always enforced) |

---

## Project Structure

```
turns/
├── simulation.py          # Main application (all logic)
├── images/
│   ├── intersection.png   # Background road image
│   ├── signals/           # red / yellow / green signal images
│   ├── right / down / left / up /   # vehicle sprites per direction
├── results/               # Auto-created; CSV exports go here
├── README.md
└── _verify.py             # Headless test script (run with: python _verify.py)
```

---

## Architecture Notes

- **Three threads**: AI/Fixed controller thread, scenario vehicle-generator thread, main Pygame render loop.
- **Pause-safe**: the sleep loop checks `sim_paused` every 50 ms and extends deadlines during pause so simulation-time metrics remain accurate.
- **One controller at a time**: `start_run()` stops existing threads before launching new ones.
- **Thread-safe stats**: vehicle generation/serving events accumulate stats atomically per-frame; no separate lock is needed for per-frame reads.
- **Deterministic replay**: `_generate_scenario()` uses `random.Random(SCENARIO_SEED)` and records all spawn events as a list, which is replayed in order by the generator thread.
