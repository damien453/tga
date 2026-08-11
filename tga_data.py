"""Load whitespace-delimited TGA/DSC text exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TgaDataset:
    """Parsed TGA/DSC table with named columns and units."""

    path: Path
    names: list[str]
    units: list[str]
    columns: dict[str, np.ndarray]

    def series(self, name: str) -> np.ndarray:
        key = name.casefold()
        for column_name, values in self.columns.items():
            if column_name.casefold() == key:
                return values
        available = ", ".join(self.names)
        raise KeyError(f"Unknown column {name!r}. Available: {available}")

    def label(self, name: str) -> str:
        key = name.casefold()
        for column_name, unit in zip(self.names, self.units):
            if column_name.casefold() == key:
                return f"{column_name} [{unit}]" if unit else column_name
        return name


def _split_fields(line: str) -> list[str]:
    return line.split()


def load_tga_file(path: str | Path) -> TgaDataset:
    """
    Parse a TGA text export.

    Expected layout:
      line 1: column names (e.g. Index Ts t HF Weight Tr)
      line 2: units        (e.g. [#] [°C] [s] [mW] [mg] [°C])
      line 3+: whitespace-separated scientific values
    """
    file_path = Path(path)
    # Instrument exports often use Latin-1 degree symbols (0xB0), not UTF-8.
    text = file_path.read_text(encoding="latin-1")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError(f"{file_path} needs a header, units row, and data.")

    names = _split_fields(lines[0])
    raw_units = _split_fields(lines[1])
    units = [unit.strip("[]") for unit in raw_units]

    if len(names) != len(units):
        raise ValueError(
            f"Header has {len(names)} names but units row has {len(units)} fields."
        )

    rows: list[list[float]] = []
    for line_no, line in enumerate(lines[2:], start=3):
        fields = _split_fields(line)
        # Skip metadata footers / partial trailing lines.
        if len(fields) != len(names):
            continue
        try:
            rows.append([float(value) for value in fields])
        except ValueError:
            continue

    if not rows:
        raise ValueError(f"{file_path}: no numeric data rows found.")

    array = np.asarray(rows, dtype=float)
    columns = {name: array[:, index] for index, name in enumerate(names)}
    return TgaDataset(path=file_path, names=names, units=units, columns=columns)
