"""TGA/DSC chart viewer with folder inputs, batch export, and multi-file overlays."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm

from tga_data import load_tga_file


DEFAULT_PLOTS = (
    ("Ts", "Weight"),
    ("Ts", "HF"),
    ("t", "Weight"),
    ("t", "HF"),
)
DEFAULT_OVERLAY = ("Ts", "Weight")
DATA_DIR = Path("data")
# Soft guidance only; large folders are supported.
WARN_TRACES = 25
MAX_POINTS_PER_TRACE = 4000
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
            "Chart TGA/DSC text exports. Pass files and/or directories. "
            "One file → multi-panel view; several files → overlay; "
            "use --batch to export one figure per file."
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
        help="Y-axis column (default for overlays: Weight).",
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


def plot_single(path: Path, x_name: str | None, y_name: str | None, output: str | None) -> None:
    dataset = load_tga_file(path)

    if x_name or y_name:
        if not x_name or not y_name:
            raise SystemExit("Both --x and --y are required for a custom plot.")
        pairs = ((x_name, y_name),)
        cols = 1
        rows = 1
    else:
        available = {name.casefold() for name in dataset.names}
        pairs = tuple(
            (x, y)
            for x, y in DEFAULT_PLOTS
            if x.casefold() in available and y.casefold() in available
        )
        if not pairs:
            raise SystemExit("No default column pairs found in this file.")
        cols = 2
        rows = (len(pairs) + 1) // 2

    fig, axes = plt.subplots(rows, cols, figsize=(11, 4.2 * rows), squeeze=False)
    fig.suptitle(display_name(path))

    for index, (x_col, y_col) in enumerate(pairs):
        ax = axes[index // cols][index % cols]
        x_vals, y_vals = _downsample(dataset.series(x_col), dataset.series(y_col))
        ax.plot(x_vals, y_vals, color=TRACE_COLORS[0], linewidth=1.1)
        ax.set_xlabel(dataset.label(x_col))
        ax.set_ylabel(dataset.label(y_col))
        ax.set_title(f"{y_col} vs {x_col}")
        ax.grid(True, alpha=0.3)

    for index in range(len(pairs), rows * cols):
        axes[index // cols][index % cols].set_visible(False)

    _finish_figure(fig, output)


def plot_overlay(paths: list[Path], x_name: str | None, y_name: str | None, output: str | None) -> None:
    x_col = x_name or DEFAULT_OVERLAY[0]
    y_col = y_name or DEFAULT_OVERLAY[1]
    if (x_name and not y_name) or (y_name and not x_name):
        raise SystemExit("Both --x and --y are required when overriding overlay axes.")

    if len(paths) > WARN_TRACES:
        print(
            f"Plotting {len(paths)} traces (large overlay). "
            "Consider --batch -o charts/ for individual figures.",
            file=sys.stderr,
        )

    fig_width = 12 if len(paths) <= 12 else 14
    fig, ax = plt.subplots(figsize=(fig_width, 7))
    label_x = None
    label_y = None
    # Prefer short labels; disambiguate duplicates with relative path.
    names = [short_label(path) for path in paths]
    if len(set(names)) != len(names):
        names = [display_name(path) for path in paths]

    for index, path in enumerate(paths):
        dataset = load_tga_file(path)
        x_vals, y_vals = _downsample(dataset.series(x_col), dataset.series(y_col))
        ax.plot(
            x_vals,
            y_vals,
            color=_trace_color(index, len(paths)),
            linewidth=1.1,
            label=names[index],
            alpha=0.9 if len(paths) < 20 else 0.75,
        )
        label_x = label_x or dataset.label(x_col)
        label_y = label_y or dataset.label(y_col)

    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    ax.set_title(f"{y_col} vs {x_col} ({len(paths)} runs)")
    ax.grid(True, alpha=0.3)

    legend_fontsize = 8 if len(paths) <= 15 else 6
    if len(paths) <= 8:
        ax.legend(fontsize=legend_fontsize, loc="best")
        fig.tight_layout()
    else:
        ax.legend(
            fontsize=legend_fontsize,
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            borderaxespad=0,
        )
        fig.tight_layout(rect=(0, 0, 0.78, 1))

    _finish_figure(fig, output)


def plot_batch(
    paths: list[Path],
    x_name: str | None,
    y_name: str | None,
    output_dir: Path,
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
        plot_single(path, x_name, y_name, str(out_path))
        plt.close("all")
    print(f"Saved {len(paths)} figure(s) under {output_dir}/")


def _finish_figure(fig, output: str | None) -> None:
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved {out_path}")
    else:
        plt.show()


def main() -> None:
    args = build_parser().parse_args()

    if args.list_files:
        files = discover_data_files()
        if not files:
            print(f"No .txt files found under {DATA_DIR}/", file=sys.stderr)
            raise SystemExit(1)
        for path in files:
            print(display_name(path))
        return

    paths = resolve_data_files(args.files, recursive=args.recursive)
    print(f"Selected {len(paths)} file(s).", file=sys.stderr)

    if args.list_columns:
        dataset = load_tga_file(paths[0])
        for name, unit in zip(dataset.names, dataset.units):
            safe_unit = unit.replace("\xb0", "deg ")
            print(f"{name}\t[{safe_unit}]")
        return

    if args.batch:
        if not args.output:
            raise SystemExit("--batch requires -o / --output directory (e.g. -o charts/).")
        output_dir = Path(args.output)
        if output_dir.exists() and output_dir.is_file():
            raise SystemExit(f"--batch output must be a directory, got file: {output_dir}")
        plot_batch(paths, args.x, args.y, output_dir)
        return

    if len(paths) == 1:
        plot_single(paths[0], args.x, args.y, args.output)
    else:
        plot_overlay(paths, args.x, args.y, args.output)


if __name__ == "__main__":
    main()
