# Lab: TGA Charting CLI

Hands-on walkthrough of the `chart.py` command-line tool for plotting TGA/DSC instrument text exports.

## Goals

By the end of this lab you will be able to:

1. Set up the Python environment
2. Discover sample files under `data/`
3. Inspect column names and units
4. Plot a single run (default multi-panel or custom axes)
5. Overlay multiple runs on one chart
6. Save figures to disk instead of opening a window

## Prerequisites

- Python 3.10+ recommended
- Repository checked out with the tracked `data/` exports present

## Part 0 — Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Confirm the CLI is available:

```bash
python chart.py --help
```

You should see options for `-x` / `-y`, `-o`, `--list-files`, and `--list-columns`.

> Tip: On headless machines (CI, SSH without a display), always pass `-o some.png` so Matplotlib does not try to open a GUI window. You can also set `MPLBACKEND=Agg`.

## Part 1 — Explore the sample data

All instrument exports live under `data/` and are **tracked in git** so everyone works from the same files.

List every available `.txt` file (recursive, including subfolders such as `EC Hold checks/`):

```bash
python chart.py --list-files
```

You should see on the order of ~100 files. Paths are printed relative to `data/`.

Pick one file and inspect its columns:

```bash
python chart.py WJM260723.txt --list-columns
```

Expected columns (names and units may vary slightly by export):

```text
Index   [#]
Ts      [deg C]
t       [s]
HF      [mW]
Weight  [mg]
Tr      [deg C]
```

### Checkpoint

- [ ] `--list-files` prints paths under `data/` including at least one `EC Hold checks/...` entry
- [ ] `--list-columns` shows `Ts`, `t`, `HF`, and `Weight`

## Part 2 — Single-file default charts

With one file and no `-x`/`-y`, the tool draws a 2×2 panel of the default pairs that exist in the file:

- Weight vs Ts
- HF vs Ts
- Weight vs t
- HF vs t

```bash
python chart.py WJM260723.txt -o lab_default.png
```

Open `lab_default.png` and confirm four panels with the sample name in the figure title.

Bare filenames are resolved recursively under `data/`. These are equivalent when the name is unique:

```bash
python chart.py WJM260723.txt -o lab_default.png
python chart.py data/WJM260723.txt -o lab_default.png
```

### Checkpoint

- [ ] `lab_default.png` was written
- [ ] The figure title matches the file name

## Part 3 — Custom axes

Plot a single series by choosing both axes:

```bash
python chart.py WJM260723.txt -x Ts -y Weight -o lab_weight_vs_ts.png
python chart.py WJM260723.txt -x t -y HF -o lab_hf_vs_time.png
```

Both `--x` and `--y` are required together. Column names are case-insensitive.

### Checkpoint

- [ ] `lab_weight_vs_ts.png` shows Weight decreasing as sample temperature rises
- [ ] Omitting one of `-x` / `-y` exits with an error asking for both

Try it:

```bash
python chart.py WJM260723.txt -x Ts
```

## Part 4 — Multi-file overlays

Pass two or more files to overlay traces on one chart. Overlay mode defaults to **Weight vs Ts** unless you override with `-x` / `-y`. At most **10** traces are allowed.

```bash
python chart.py WJM260723.txt VRD-637-1A.txt -o lab_overlay.png
```

Compare heat-flow instead of weight:

```bash
python chart.py WJM260723.txt VRD-637-1A.txt -x Ts -y HF -o lab_overlay_hf.png
```

Each trace is labeled with its path relative to `data/`.

### Checkpoint

- [ ] `lab_overlay.png` has a legend with both file names
- [ ] Passing more than 10 files is rejected

## Part 5 — Ambiguous names and subfolders

Some basenames appear in more than one place (root `data/` and `data/EC Hold checks/`). A bare name then fails with the matching paths:

```bash
python chart.py O2tests_GM3-607-13_240C.txt
```

Disambiguate with a path relative to `data/` or an explicit file path:

```bash
python chart.py "EC Hold checks/O2tests_GM3-607-13_240C.txt" -o lab_hold.png
python chart.py data/O2tests_GM3-607-13_240C.txt -o lab_root.png
```

Names with spaces must be quoted:

```bash
python chart.py "Barrel EC_O2.txt" -o lab_barrel.png
```

### Checkpoint

- [ ] The ambiguous basename prints both candidate paths
- [ ] Specifying `EC Hold checks/...` successfully saves a figure

## Part 6 — Data format (optional reading)

Exports are whitespace-delimited text:

1. Line 1 — column names (`Index Ts t HF Weight Tr`)
2. Line 2 — units in brackets (`[#] [°C] [s] [mW] [mg] [°C]`)
3. Remaining lines — scientific-notation values

Files are read as Latin-1 so degree symbols from the instrument software parse correctly. Trailing metadata or incomplete rows are skipped. Parsing lives in `tga_data.py` (`load_tga_file`).

## Quick reference

| Task | Command |
| --- | --- |
| Help | `python chart.py --help` |
| List samples | `python chart.py --list-files` |
| List columns | `python chart.py FILE --list-columns` |
| Default 4-panel | `python chart.py FILE -o out.png` |
| Custom axes | `python chart.py FILE -x Ts -y Weight -o out.png` |
| Overlay runs | `python chart.py FILE1 FILE2 -o out.png` |
| Overlay custom | `python chart.py FILE1 FILE2 -x t -y HF -o out.png` |

Generated `*.png` files are gitignored; keep them local or attach them outside the repo.

## Wrap-up

You should now be able to discover tracked sample data, inspect columns, plot single and overlaid TGA/DSC runs, and export PNGs for reports. For further experiments, try overlaying a hold-temperature series from `EC Hold checks/` or comparing sonicated vs non-sonicated WJM runs.
