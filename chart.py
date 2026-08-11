"""Simple interactive TGA/DSC chart viewer."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from tga_data import load_tga_file


DEFAULT_PLOTS = (
    ("Ts", "Weight"),
    ("Ts", "HF"),
    ("t", "Weight"),
    ("t", "HF"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chart TGA/DSC data from whitespace-delimited text exports."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="data/WJM260723.txt",
        help="Path to a TGA text file (default: data/WJM260723.txt)",
    )
    parser.add_argument(
        "-x",
        "--x",
        default=None,
        help="X-axis column name (e.g. Ts, t). Implies a single custom plot with -y.",
    )
    parser.add_argument(
        "-y",
        "--y",
        default=None,
        help="Y-axis column name (e.g. Weight, HF).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Save the figure to this path instead of opening a window.",
    )
    parser.add_argument(
        "--list-columns",
        action="store_true",
        help="Print available columns and exit.",
    )
    return parser


def plot_dataset(path: Path, x_name: str | None, y_name: str | None, output: str | None) -> None:
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
    fig.suptitle(path.name)

    for index, (x_col, y_col) in enumerate(pairs):
        ax = axes[index // cols][index % cols]
        x = dataset.series(x_col)
        y = dataset.series(y_col)
        ax.plot(x, y, color="#1f4e79", linewidth=1.1)
        ax.set_xlabel(dataset.label(x_col))
        ax.set_ylabel(dataset.label(y_col))
        ax.set_title(f"{y_col} vs {x_col}")
        ax.grid(True, alpha=0.3)

    for index in range(len(pairs), rows * cols):
        axes[index // cols][index % cols].set_visible(False)

    fig.tight_layout()

    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved {output}")
    else:
        plt.show()


def main() -> None:
    args = build_parser().parse_args()
    path = Path(args.file)

    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    if args.list_columns:
        dataset = load_tga_file(path)
        for name, unit in zip(dataset.names, dataset.units):
            safe_unit = unit.replace("\xb0", "deg ")
            print(f"{name}\t[{safe_unit}]")
        return

    plot_dataset(path, args.x, args.y, args.output)


if __name__ == "__main__":
    main()
