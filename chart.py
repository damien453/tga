"""TGA/DSC chart viewer with folder inputs, batch export, and multi-file overlays."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm

from tga_data import DERIVED_WEIGHT_PCT, load_tga_file
from tga_stats import format_stats, mass_loss_stats


DEFAULT_PLOTS = (
    ("Ts", "Weight%"),
    ("Ts", "HF"),
    ("t", "Weight%"),
    ("t", "HF"),
)
DATA_DIR = Path("data")
# Soft guidance only; large folders are supported.
WARN_TRACES = 25
MAX_POINTS_PER_TRACE = 4000
_GUI_CHILD_ENV = "TGA_CHART_GUI"
TRACE_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def discover_data_files(data_dir: Path = DATA_DIR) -> list[Path]:
    if not data_dir.is_dir():
        return []
    return sorted(path for path in data_dir.rglob("*.txt") if path.is_file())


def display_name(path: Path) -> str:
    try:
        return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def short_label(path: Path) -> str:
    """Prefer basename for legends; keep parent when needed for uniqueness."""
    return path.name


def _normalize_key(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", text.casefold())


def _list_txt_in_dir(directory: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.txt" if recursive else "*.txt"
    return sorted(path for path in directory.glob(pattern) if path.is_file())


def resolve_directory(directory: Path, recursive: bool) -> list[Path]:
    files = _list_txt_in_dir(directory, recursive=recursive)
    if not files:
        raise SystemExit(f"No .txt files found in directory: {directory}")
    return [path.resolve() for path in files]


def _match_data_subdir(name: str) -> Path | None:
    """Match a folder under data/, allowing hyphen/space/underscore differences."""
    if not DATA_DIR.is_dir():
        return None
    wanted = _normalize_key(name)
    matches = [
        path
        for path in DATA_DIR.iterdir()
        if path.is_dir() and _normalize_key(path.name) == wanted
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_one(file_arg: str, recursive: bool) -> list[Path]:
    path = Path(file_arg)

    if path.exists():
        resolved = path.resolve()
        if resolved.is_dir():
            return resolve_directory(resolved, recursive=recursive)
        if resolved.is_file():
            return [resolved]
        raise SystemExit(f"Not a file or directory: {file_arg}")

    under_data = DATA_DIR / file_arg
    if under_data.exists():
        resolved = under_data.resolve()
        if resolved.is_dir():
            return resolve_directory(resolved, recursive=recursive)
        return [resolved]

    # Folder aliases: GrEC-Standard -> data/GrEC Standard
    subdir = _match_data_subdir(file_arg)
    if subdir is not None:
        return resolve_directory(subdir, recursive=recursive)

    # Bare filenames are matched recursively under data/.
    matches = [candidate for candidate in discover_data_files() if candidate.name == path.name]
    if len(matches) == 1:
        return [matches[0].resolve()]
    if len(matches) > 1:
        options = "\n".join(f"  - {display_name(match)}" for match in matches)
        raise SystemExit(
            f"Ambiguous file name {path.name!r}. Specify a path:\n{options}"
        )
    raise SystemExit(f"File or directory not found: {file_arg}")


def resolve_data_files(file_args: list[str], recursive: bool) -> list[Path]:
    if not file_args:
        raise SystemExit(
            "Specify one or more data files or directories.\n"
            "Examples:\n"
            "  python chart.py data/WJM260723.txt\n"
            "  python chart.py \"GrEC Standard\" -o grec_overlay.png\n"
            "  python chart.py \"GrEC Standard\" --batch -o charts/\n"
            "  python chart.py --list-files"
        )

    resolved: list[Path] = []
    seen: set[Path] = set()
    for file_arg in file_args:
        for path in resolve_one(file_arg, recursive=recursive):
            if path in seen:
                continue
            seen.add(path)
            resolved.append(path)
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Chart TGA/DSC text exports. Default is a 4-panel window "
            "(Weight% and HF vs Ts and vs time) with mass-loss stats marked. "
            "Several files overlay on those same panels. "
            "Use --batch to export one figure per file."
        )
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="TGA text files and/or directories (names under data/ are OK).",
    )
    parser.add_argument(
        "-x",
        "--x",
        default=None,
        help="X-axis column (default for overlays: Ts).",
    )
    parser.add_argument(
        "-y",
        "--y",
        default=None,
        help="Y-axis column (default 4-panel uses Weight%; custom overlay default is Weight%).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Save figure path, or with --batch an output directory.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Plot each selected file separately (requires -o directory).",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="When a directory is given, include .txt files in subfolders.",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List available data/**/*.txt files and exit.",
    )
    parser.add_argument(
        "--list-columns",
        action="store_true",
        help="Print available columns for the first selected file and exit.",
    )
    parser.add_argument(
        "--list-duplicates",
        action="store_true",
        help=(
            "List duplicate .txt files under data/ (or given folders): "
            "same filename in multiple places, and identical contents."
        ),
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help=(
            "Keep this process open until the chart window is closed "
            "(default: the window stays open and the terminal returns)."
        ),
    )
    parser.set_defaults(stats=True)
    parser.add_argument(
        "--stats",
        dest="stats",
        action="store_true",
        help="Print mass-loss stats and mark early onset / DTG peak / cutoff on Ts panels (default).",
    )
    parser.add_argument(
        "--no-stats",
        dest="stats",
        action="store_false",
        help="Disable mass-loss tables and chart markers.",
    )
    return parser


def _trace_color(index: int, total: int):
    if total <= len(TRACE_COLORS):
        return TRACE_COLORS[index]
    return cm.turbo(index / max(total - 1, 1))


def _downsample(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(x) <= MAX_POINTS_PER_TRACE:
        return x, y
    stride = int(np.ceil(len(x) / MAX_POINTS_PER_TRACE))
    return x[::stride], y[::stride]


STAT_MARKERS = (
    ("t_early_c", "Early", "#2ca02c", ":"),
    ("t_peak_c", "DTG peak", "#ff7f0e", "--"),
    ("t_cutoff_c", "Cutoff", "#d62728", "-."),
)


def _has_series(dataset, name: str) -> bool:
    key = name.casefold()
    if key in DERIVED_WEIGHT_PCT:
        return any(column.casefold() == "weight" for column in dataset.names)
    return any(column.casefold() == key for column in dataset.names)


def _trace_names(paths: list[Path]) -> list[str]:
    names = [short_label(path) for path in paths]
    if len(set(names)) != len(names):
        return [display_name(path) for path in paths]
    return names


def _print_stats(path: Path, dataset) -> object | None:
    try:
        stats = mass_loss_stats(dataset)
    except (KeyError, ValueError) as exc:
        print(f"{display_name(path)}: could not compute stats ({exc})", file=sys.stderr)
        return None
    print(format_stats(display_name(path), stats))
    return stats


def _annotate_ts_stats(
    ax,
    stats,
    *,
    color: str | None = None,
    show_box: bool = True,
    labeled: bool = False,
) -> None:
    if stats is None:
        return
    for attr, label, marker_color, style in STAT_MARKERS:
        value = getattr(stats, attr)
        if not np.isfinite(value):
            continue
        ax.axvline(
            value,
            color=color or marker_color,
            linestyle=style,
            linewidth=1.0 if color else 1.1,
            alpha=0.8,
            label=label if labeled else None,
        )
    if not show_box:
        return
    box_rows = []
    for attr, name in (
        ("t_early_c", "Early"),
        ("t1_c", "T1"),
        ("t_onset_c", "Onset"),
        ("t_peak_c", "DTG peak"),
        ("t_cutoff_c", "Cutoff"),
    ):
        value = getattr(stats, attr)
        if np.isfinite(value):
            box_rows.append(f"{name} {value:.0f} C")
    if stats.isothermal:
        box_rows.append("hold: T cutoff n/a")
        box_rows.append(f"residual {stats.mass_final_pct:.1f} %")
    if box_rows:
        ax.text(
            0.98,
            0.97,
            "\n".join(box_rows),
            transform=ax.transAxes,
            va="top",
            ha="right",
            fontsize=8,
            family="monospace",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.9},
        )


def plot_charts(
    paths: list[Path],
    x_name: str | None,
    y_name: str | None,
    output: str | None,
    show_stats: bool = True,
) -> None:
    datasets = [load_tga_file(path) for path in paths]
    names = _trace_names(paths)

    if x_name or y_name:
        if not x_name or not y_name:
            raise SystemExit("Both --x and --y are required for a custom plot.")
        pairs = ((x_name, y_name),)
    else:
        pairs = tuple(
            (x_col, y_col)
            for x_col, y_col in DEFAULT_PLOTS
            if all(_has_series(dataset, x_col) and _has_series(dataset, y_col) for dataset in datasets)
        )
        if not pairs:
            raise SystemExit("No default column pairs found in these files.")

    n_panel = len(pairs)
    cols = 1 if n_panel == 1 else 2
    rows = (n_panel + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(12, 4.1 * rows), squeeze=False)
    fig.suptitle(display_name(paths[0]) if len(paths) == 1 else f"{len(paths)} runs")

    if len(paths) > WARN_TRACES:
        print(
            f"Plotting {len(paths)} traces (large overlay). "
            "Consider --batch -o charts/ for individual figures.",
            file=sys.stderr,
        )

    stats_list = [_print_stats(path, dataset) if show_stats else None for path, dataset in zip(paths, datasets)]
    alpha = 0.9 if len(paths) < 20 else 0.75
    single = len(paths) == 1

    for index, (x_col, y_col) in enumerate(pairs):
        ax = axes[index // cols][index % cols]
        label_x = None
        label_y = None
        for trace_i, dataset in enumerate(datasets):
            color = _trace_color(trace_i, len(paths))
            x_vals, y_vals = _downsample(dataset.series(x_col), dataset.series(y_col))
            ax.plot(
                x_vals,
                y_vals,
                color=color,
                linewidth=1.1,
                alpha=alpha,
                label=names[trace_i] if index == 0 else None,
            )
            label_x = label_x or dataset.label(x_col)
            label_y = label_y or dataset.label(y_col)
            if stats_list[trace_i] is not None and x_col.casefold() == "ts":
                _annotate_ts_stats(
                    ax,
                    stats_list[trace_i],
                    color=None if single else color,
                    show_box=single,
                    labeled=single,
                )
        ax.set_xlabel(label_x)
        ax.set_ylabel(label_y)
        ax.set_title(f"{y_col} vs {x_col}")
        ax.grid(True, alpha=0.3)
        if single and show_stats and x_col.casefold() == "ts":
            ax.legend(fontsize=8, loc="lower left", framealpha=0.9)

    for index in range(n_panel, rows * cols):
        axes[index // cols][index % cols].set_visible(False)

    if not single:
        handles, labels = axes[0][0].get_legend_handles_labels()
        legend_fontsize = 8 if len(paths) <= 15 else 6
        if len(paths) <= 8:
            fig.legend(
                handles,
                labels,
                loc="lower center",
                ncol=min(len(paths), 4),
                fontsize=legend_fontsize,
                bbox_to_anchor=(0.5, 0.01),
            )
            fig.tight_layout(rect=(0, 0.08, 1, 0.96))
        else:
            fig.legend(
                handles,
                labels,
                loc="center left",
                bbox_to_anchor=(1.02, 0.5),
                fontsize=legend_fontsize,
            )
            fig.tight_layout(rect=(0, 0, 0.78, 0.96))
    else:
        fig.tight_layout()

    _finish_figure(fig, output)


def plot_single(
    path: Path,
    x_name: str | None,
    y_name: str | None,
    output: str | None,
    show_stats: bool = True,
) -> None:
    plot_charts([path], x_name, y_name, output, show_stats=show_stats)


def plot_batch(
    paths: list[Path],
    x_name: str | None,
    y_name: str | None,
    output_dir: Path,
    show_stats: bool = True,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    for path in paths:
        stem = path.stem
        # Avoid collisions when the same basename appears in multiple folders.
        candidate = f"{stem}.png"
        if candidate in used_names:
            parent = path.parent.name.replace(" ", "_")
            candidate = f"{parent}__{stem}.png"
        used_names.add(candidate)
        out_path = output_dir / candidate
        print(f"Plotting {display_name(path)} -> {out_path}")
        plot_single(path, x_name, y_name, str(out_path), show_stats=show_stats)
        plt.close("all")
    print(f"Saved {len(paths)} figure(s) under {output_dir}/")


def collect_txt_files(file_args: list[str]) -> list[Path]:
    if not file_args:
        return discover_data_files()
    files: list[Path] = []
    seen: set[Path] = set()
    for file_arg in file_args:
        path = Path(file_arg)
        if not path.exists():
            under = DATA_DIR / file_arg
            path = under if under.exists() else path
        if path.is_dir():
            candidates = sorted(p for p in path.rglob("*.txt") if p.is_file())
        elif path.is_file():
            candidates = [path]
        else:
            raise SystemExit(f"File or directory not found: {file_arg}")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return files


def list_duplicates(files: list[Path]) -> None:
    if not files:
        print("No .txt files to compare.", file=sys.stderr)
        raise SystemExit(1)

    by_name: dict[str, list[Path]] = defaultdict(list)
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        by_name[path.name].append(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        by_hash[digest].append(path)

    name_groups = [paths for paths in by_name.values() if len(paths) > 1]
    hash_groups = [paths for paths in by_hash.values() if len(paths) > 1]

    print(f"Same filename ({len(name_groups)} groups)")
    if not name_groups:
        print("  none")
    else:
        for paths in sorted(name_groups, key=lambda group: group[0].name.casefold()):
            print(f"  {paths[0].name}  ({len(paths)} copies)")
            for path in paths:
                print(f"    {display_name(path)}")

    print()
    print(f"Identical contents ({len(hash_groups)} groups)")
    if not hash_groups:
        print("  none")
    else:
        for paths in sorted(hash_groups, key=lambda group: (-len(group), display_name(group[0]))):
            print(f"  {len(paths)} copies")
            for path in paths:
                print(f"    {display_name(path)}")


def _finish_figure(fig, output: str | None) -> None:
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved {out_path}")
        plt.close(fig)
    else:
        plt.show(block=True)


def _spawn_chart_window() -> None:
    """Start a child that owns the GUI so this process can exit."""
    env = os.environ.copy()
    env[_GUI_CHILD_ENV] = "1"
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, *sys.argv], env=env, **kwargs)
    print("Opened a chart window. Close that window when you are done.", file=sys.stderr)


def main() -> None:
    args = build_parser().parse_args()

    showing_window = (
        not args.output
        and not args.batch
        and not args.list_files
        and not args.list_columns
        and not args.list_duplicates
        and not args.wait
        and bool(args.files)
    )
    if showing_window and os.environ.get(_GUI_CHILD_ENV) != "1":
        _spawn_chart_window()
        return

    if args.list_files:
        files = discover_data_files()
        if not files:
            print(f"No .txt files found under {DATA_DIR}/", file=sys.stderr)
            raise SystemExit(1)
        for path in files:
            print(display_name(path))
        return

    if args.list_duplicates:
        files = collect_txt_files(args.files)
        list_duplicates(files)
        return

    paths = resolve_data_files(args.files, recursive=args.recursive)
    print(f"Selected {len(paths)} file(s).", file=sys.stderr)

    if args.list_columns:
        dataset = load_tga_file(paths[0])
        for name, unit in zip(dataset.names, dataset.units):
            safe_unit = unit.replace("\xb0", "deg ")
            print(f"{name}\t[{safe_unit}]")
        print("Weight%\t[% of initial]")
        return

    if args.batch:
        if not args.output:
            raise SystemExit("--batch requires -o / --output directory (e.g. -o charts/).")
        output_dir = Path(args.output)
        if output_dir.exists() and output_dir.is_file():
            raise SystemExit(f"--batch output must be a directory, got file: {output_dir}")
        plot_batch(paths, args.x, args.y, output_dir, show_stats=args.stats)
        return

    plot_charts(paths, args.x, args.y, args.output, show_stats=args.stats)


if __name__ == "__main__":
    main()
