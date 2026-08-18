# Lab: TGA Charting CLI

Hands-on walkthrough of `chart.py` for plotting TGA/DSC instrument text exports.

Work from the **repository root**. On Windows, quote any path that contains a space.

## Goals

1. Set up the Python environment
2. Discover files under `data/`
3. Inspect columns
4. Plot one run (default 4-panel or custom axes)
5. Overlay several runs
6. Plot a whole folder (overlay or batch)
7. Mark mass-loss onset, DTG peak, and cutoff with `--stats`
8. Save PNGs instead of opening a window

## Prerequisites

- Conda, with the `pytga` environment (Python 3.10+)
- This repo checked out on `main`, with `data/` present

## Layout

Instrument exports live under `data/` and are tracked in git.

| Folder | What is in it |
| --- | --- |
| `data/EC/` | Barrel, Sigma, and pure EC ramps (use these for `--stats`) |
| `data/GrEC-Standard/` | Standard GrEC set (~169 runs) |
| `data/EC Hold checks/` | Hold-temperature series |
| `data/GL6/`, `data/VXGr Annealing Study/`, `data/SORTING/` | Other studies and copies |

The same basename can appear in more than one folder. Prefer a path (`data/EC/...`) over a bare filename.

## Part 0 — Setup

This project uses the conda environment `pytga`, not a `.venv`.

Create it once if it does not exist:

```bash
conda create -n pytga python=3.13
```

Activate it (every session):

```bash
conda activate pytga
```

Then install dependencies and confirm the CLI:

```bash
pip install -r requirements.txt
python chart.py --help
```

You should see `-x` / `-y`, `-o`, `--batch`, `--recursive`, `--list-files`, `--list-columns`, and `--stats`.

On a machine without a display, always pass `-o some.png`, or set `MPLBACKEND=Agg`. Generated PNGs are gitignored.

## Part 1 — Explore the data

```bash
python chart.py --list-files
```

Paths print relative to `data/`. You should see `EC/`, `GrEC-Standard/`, and `EC Hold checks/`.

Inspect columns on a unique path:

```bash
python chart.py "data/EC/Sigma EC_O2.txt" --list-columns
```

Typical columns:

```text
Index   [#]
Ts      [deg C]
t       [s]
HF      [mW]
Weight  [mg]
Tr      [deg C]
```

`--list-columns` uses the first selected file.

### Checkpoint

- [ ] `--list-files` includes `EC/Sigma EC_O2.txt` and `GrEC-Standard/...`
- [ ] `--list-columns` shows `Ts`, `t`, `HF`, and `Weight`

## Part 2 — Single-file default charts

With one file and no `-x`/`-y`, the tool draws a 2×2 panel of pairs that exist in the file:

- Weight vs Ts
- HF vs Ts
- Weight vs t
- HF vs t

```bash
python chart.py "data/EC/Sigma EC_O2.txt" -o lab_default.png
```

Open `lab_default.png`. The figure title is the path relative to `data/`.

An absolute path also works:

```bash
python chart.py "C:\dev\tga\data\EC\Sigma EC_O2.txt" -o lab_default.png
```

### Checkpoint

- [ ] `lab_default.png` was written
- [ ] The title includes `EC/Sigma EC_O2.txt`

## Part 3 — Custom axes

Both `--x` and `--y` are required together. Names are case-insensitive.

```bash
python chart.py "data/EC/Sigma EC_O2.txt" -x Ts -y Weight -o lab_weight_vs_ts.png
python chart.py "data/EC/Sigma EC_O2.txt" -x t -y HF -o lab_hf_vs_time.png
```

Omitting only one axis is an error:

```bash
python chart.py "data/EC/Sigma EC_O2.txt" -x Ts
```

### Checkpoint

- [ ] `lab_weight_vs_ts.png` shows weight falling as Ts rises
- [ ] `-x Ts` alone exits asking for both `--x` and `--y`

## Part 4 — Overlays

Two or more files (or a folder) overlay on **Weight vs Ts** unless you set `-x` / `-y`.

```bash
python chart.py "data/EC/Barrel EC_O2.txt" "data/EC/Sigma EC_O2.txt" -o lab_overlay.png
python chart.py "data/EC/Barrel EC_O2.txt" "data/EC/Sigma EC_O2.txt" -x Ts -y HF -o lab_overlay_hf.png
```

Legends use the file name. If two files share a name, the legend uses the path relative to `data/`.

### Checkpoint

- [ ] `lab_overlay.png` has a legend with both names

## Part 5 — A whole folder

Pass a directory to select every `.txt` in it (not subfolders unless you add `-r`). Folder names under `data/` match with spaces, hyphens, or underscores: `GrEC-Standard` and `"GrEC Standard"` are the same folder.

**One overlay chart** for the folder:

```bash
python chart.py EC -o ec_overlay.png
python chart.py GrEC-Standard -o grec_overlay.png
python chart.py "EC Hold checks" -o ec_hold_overlay.png
```

A large overlay (more than 25 traces) prints a hint to use `--batch` instead. `GrEC-Standard` is in that range.

**Batch mode** writes one figure per file into a directory (`-o` is required):

```bash
python chart.py EC --batch -o ec_charts/
python chart.py EC --batch --stats -o ec_charts/
python chart.py "EC Hold checks" --batch -o ec_hold_charts/
```

Add `-r` / `--recursive` only when you want `.txt` files in subfolders of the directory you passed.

### Checkpoint

- [ ] `EC -o ec_overlay.png` is one PNG with one legend entry per EC run
- [ ] `EC --batch -o ec_charts/` creates one PNG per file in that folder

## Part 6 — Ambiguous names

Bare filenames are resolved by searching all of `data/`. If the name exists twice, the tool lists the matches and exits:

```bash
python chart.py WJM260723.txt
python chart.py "Sigma EC_O2.txt"
```

Disambiguate with a path:

```bash
python chart.py data/GrEC-Standard/WJM260723.txt -o lab_grec_wjm.png
python chart.py "data/EC/Sigma EC_O2.txt" -o lab_sigma.png
python chart.py "EC Hold checks/O2tests_GM3-607-13_240C.txt" -o lab_hold.png
```

### Checkpoint

- [ ] `WJM260723.txt` with no path prints more than one candidate
- [ ] `data/EC/Sigma EC_O2.txt` saves a figure

## Part 7 — Onset and cutoff (`--stats`)

`--stats` prints mass-loss temperatures and, on a **single-file** chart, draws them on any panel whose x-axis is `Ts`.

Use matched **ramps** when comparing samples. Do not compare a 310 °C hold to an 800 °C ramp.

### What the numbers mean

| Label | On the chart | Meaning |
| --- | --- | --- |
| T5 | green dotted | Temperature at 5% of the observed mass-loss step |
| Onset | in the box | Extrapolated tangent onset at the main DTG peak |
| DTG peak | orange dashed | Steepest mass-loss rate during the main step |
| Cutoff | red dash-dot | Extrapolated tangent endset of that step |
| T95 | in the box | 95% of the total mass-loss step (includes the slow tail) |

The main DTG peak is taken while residual mass is still 12–90%, so a late residue burnout is not treated as the EC step.

### One file, Weight vs Ts

```bash
python chart.py "data/EC/Barrel EC_O2.txt" -x Ts -y Weight --stats -o barrel_stats.png
python chart.py "data/EC/Sigma EC_O2.txt" -x Ts -y Weight --stats -o sigma_stats.png
python chart.py data/EC/2023_04_24_EC_Pure.txt -x Ts -y Weight --stats -o pure_stats.png
```

Omit `-o` to open a window instead of saving.

The terminal prints the table at 0.1 °C. Copy that into a notebook. Example for Barrel:

```text
EC/Barrel EC_O2.txt
  T5 onset               193.9 C
  Tangent onset          267.5 C
  T50                    293.1 C
  DTG peak               303.6 C
  Main-step cutoff       312.4 C
  T95                    451.3 C
  Mass loss               99.6 %
  Final residual          -0.1 %
  Heating rate            5.00 C/min
```

A slightly negative residual is an instrument zero after complete volatilization; treat it as ~0%.

On the 5 °C/min ramps, expected T5 is about **Barrel 194 °C**, **Sigma 224 °C**, **Pure (24 Apr) 259 °C**.

### Default 4-panel with stats

Markers go on every panel that uses `Ts`:

```bash
python chart.py "data/EC/Barrel EC_O2.txt" --stats -o barrel_panels.png
```

### Overlay: numbers in the terminal only

With several files, `--stats` still prints one table per run. Vertical lines are only drawn on single-file charts.

```bash
python chart.py "data/EC/Barrel EC_O2.txt" "data/EC/Sigma EC_O2.txt" data/EC/2023_04_24_EC_Pure.txt --stats -o ec_overlay.png
```

### Holds are flagged

A hold file still prints temperatures, but they are not comparable to a ramp:

```bash
python chart.py data/EC/2023-04-26_EC_pure_anneal.txt --stats -o anneal_stats.png
```

```text
  Note: furnace is a hold (heating rate ~0). Temperature statistics are not comparable to a ramp.
```

### Checkpoint

- [ ] `barrel_stats.png` has Weight vs Ts, three vertical lines, a legend, and a stats box
- [ ] Terminal T5 is near 194 °C (Barrel), 224 °C (Sigma), 259 °C (Pure, 24 Apr)
- [ ] The anneal hold prints the isothermal note

## Part 8 — Data format (optional)

Exports are whitespace-delimited text:

1. Line 1 — column names (`Index Ts t HF Weight Tr`)
2. Line 2 — units in brackets (`[#] [°C] [s] [mW] [mg] [°C]`), **or** data if the export has no units row
3. Remaining lines — scientific-notation values

Files are read as Latin-1 so degree symbols from the instrument software parse. Trailing metadata and incomplete rows are skipped.

Parsing: `tga_data.py` (`load_tga_file`). Statistics: `tga_stats.py` (`mass_loss_stats`).

## Quick reference

| Task | Command |
| --- | --- |
| Help | `python chart.py --help` |
| List samples | `python chart.py --list-files` |
| List columns | `python chart.py FILE --list-columns` |
| Default 4-panel | `python chart.py FILE -o out.png` |
| Custom axes | `python chart.py FILE -x Ts -y Weight -o out.png` |
| Stats on one file | `python chart.py FILE -x Ts -y Weight --stats -o out.png` |
| Overlay files | `python chart.py FILE1 FILE2 -o out.png` |
| Folder overlay | `python chart.py EC -o out.png` |
| Folder batch | `python chart.py EC --batch -o charts/` |
| Folder batch + stats | `python chart.py EC --batch --stats -o charts/` |

Quote paths with spaces. Prefer `data/EC/...` or `data/GrEC-Standard/...` over a bare filename.

## Wrap-up

You can list the library, plot one run or a folder, overlay traces, mark onset/cutoff with `--stats`, and export PNGs. Next: batch-export `GrEC-Standard`, overlay `EC Hold checks/`, or compare a GrEC run to the EC ramps in `data/EC/`.
