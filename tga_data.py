"""Load whitespace-delimited TGA/DSC text exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


DERIVED_WEIGHT_PCT = frozenset({"weight%", "mass%", "masspct", "weightpct"})


@dataclass(frozen=True)
class TgaDataset:
    """Parsed TGA/DSC table with named columns and units."""

    path: Path
    names: list[str]
    units: list[str]
    columns: dict[str, np.ndarray]

    def _column(self, name: str) -> np.ndarray:
        key = name.casefold()
        for column_name, values in self.columns.items():
            if column_name.casefold() == key:
                return values
        available = ", ".join(self.names)
        raise KeyError(f"Unknown column {name!r}. Available: {available}")

    def initial_weight_mg(self) -> float:
        """Median of the first 50 Weight points (same baseline as --stats)."""
        weight = self._column("Weight")
        w0 = float(np.median(weight[: min(50, len(weight))]))
        if w0 == 0:
            w0 = float(weight[0])
        if w0 == 0:
            raise ValueError(f"{self.path}: initial mass is zero.")
        return w0

    def series(self, name: str) -> np.ndarray:
        key = name.casefold()
        if key in DERIVED_WEIGHT_PCT:
            weight = self._column("Weight")
            return 100.0 * weight / self.initial_weight_mg()
        return self._column(name)

    def label(self, name: str) -> str:
        key = name.casefold()
        if key in DERIVED_WEIGHT_PCT:
            return "Weight [% of initial]"
        for column_name, unit in zip(self.names, self.units):
            if column_name.casefold() == key:
                return f"{column_name} [{unit}]" if unit else column_name
        return name


def _split_fields(line: str) -> list[str]:
    return line.split()


def _default_unit(name: str) -> str:
    key = name.casefold()
    if key in {"ts", "tr"}:
        return "deg C"
    if key == "t":
        return "s"
    if key == "hf":
        return "mW"
    if key == "weight":
        return "mg"
    if key == "index":
        return "#"
    return ""


def load_tga_file(path: str | Path) -> TgaDataset:
    """
    Parse a TGA text export.

    Expected layout:
      line 1: column names (e.g. Index Ts t HF Weight Tr)
      line 2: units        (e.g. [#] [deg C] [s] [mW] [mg] [deg C])
      line 3+: whitespace-separated scientific values

    The units row is optional. If line 2 is numeric data, default units are used.
    """
    file_path = Path(path)
    # Instrument exports often use Latin-1 degree symbols (0xB0), not UTF-8.
    text = file_path.read_text(encoding="latin-1")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"{file_path} needs a header and data.")

    names = _split_fields(lines[0])
    raw_units = _split_fields(lines[1])
    has_units_row = any("[" in field for field in raw_units)
    if has_units_row:
        units = [unit.strip("[]") for unit in raw_units]
        data_start = 2
        if len(names) != len(units):
            raise ValueError(
                f"Header has {len(names)} names but units row has {len(units)} fields."
            )
    else:
        units = [_default_unit(name) for name in names]
        data_start = 1

    rows: list[list[float]] = []
    for line_no, line in enumerate(lines[data_start:], start=data_start + 1):
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
