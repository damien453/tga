"""Simple TGA/DSC chart viewer with multi-file overlays."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from tga_data import load_tga_file


DEFAULT_PLOTS = (
    ("Ts", "Weight"),
    ("Ts", "HF"),
    ("t", "Weight"),
    ("t", "HF"),
)
DEFAULT_OVERLAY = ("Ts", "Weight")
DATA_DIR = Path("data")
MAX_TRACES = 10
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
        return path.relative_to(DATA_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_one(file_arg: str) -> Path:
    path = Path(file_arg)

    # Explicit relative/absolute paths win as-is.
    if path.exists():
        return path.resolve()

    under_data = DATA_DIR / file_arg
    if under_data.exists() and ("/" in file_arg or "\\" in file_arg):
        return under_data.resolve()

    # Bare filenames are matched recursively under data/.
    matches = [candidate for candidate in discover_data_files() if candidate.name == path.name]
    if len(matches) == 1:
        return matches[0].resolve()
    if len(matches) > 1:
        options = "\n".join(f"  - {display_name(match)}" for match in matches)
        raise SystemExit(
            f"Ambiguous file name {path.name!r}. Specify a path:\n{options}"
        )
    if under_data.exists():
        return under_data.resolve()
    raise SystemExit(f"File not found: {file_arg}")


def resolve_data_files(file_args: list[str]) -> list[Path]:
    if not file_args:
        raise SystemExit(
            "Specify one or more data files.\n"
            "Examples:\n"
            "  python chart.py data/WJM260723.txt\n"
            "  python chart.py WJM260723.txt VRD-637-1A.txt -x Ts -y Weight\n"
            "  python chart.py --list-files"
        )

    resolved: list[Path] = []
    seen: set[Path] = set()
    for file_arg in file_args:
        path = resolve_one(file_arg)
        if path in seen:
            continue
        seen.add(path)
        resolved.append(path)

    if len(resolved) > MAX_TRACES:
        raise SystemExit(f"At most {MAX_TRACES} traces can be plotted (got {len(resolved)}).")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Chart TGA/DSC text exports. Pass one file for the default multi-panel view, "
            f"or up to {MAX_TRACES} files to overlay traces on one chart."
        )
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="TGA text file paths, or names under data/ (recursive).",
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
        help="Save the figure to this path instead of opening a window.",
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
        ax.plot(dataset.series(x_col), dataset.series(y_col), color=TRACE_COLORS[0], linewidth=1.1)
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

    fig, ax = plt.subplots(figsize=(11, 6))
    label_x = None
    label_y = None

    for index, path in enumerate(paths):
        dataset = load_tga_file(path)
        ax.plot(
            dataset.series(x_col),
            dataset.series(y_col),
            color=TRACE_COLORS[index % len(TRACE_COLORS)],
            linewidth=1.2,
            label=display_name(path),
        )
        label_x = label_x or dataset.label(x_col)
        label_y = label_y or dataset.label(y_col)

    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    ax.set_title(f"{y_col} vs {x_col}")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    _finish_figure(fig, output)


def _finish_figure(fig, output: str | None) -> None:
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved {output}")
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

    paths = resolve_data_files(args.files)

    if args.list_columns:
        dataset = load_tga_file(paths[0])
        for name, unit in zip(dataset.names, dataset.units):
            safe_unit = unit.replace("\xb0", "deg ")
            print(f"{name}\t[{safe_unit}]")
        return

    if len(paths) == 1:
        plot_single(paths[0], args.x, args.y, args.output)
    else:
        plot_overlay(paths, args.x, args.y, args.output)


if __name__ == "__main__":
    main()
