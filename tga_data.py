"""Load whitespace-delimited TGA/DSC text exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_COLUMN_ALIASES = {
    "x value": "t",
    "xvalue": "t",
    "y value": "Weight",
    "yvalue": "Weight",
}


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


def _split_header_fields(line: str) -> list[str]:
    """Keep multi-word names such as 'x value' / 'y value' from older exports."""
    parts = [part.strip() for part in re.split(r"\s{2,}", line.strip()) if part.strip()]
    return parts if len(parts) >= 2 else _split_fields(line)


def _normalize_column_name(name: str) -> str:
    key = " ".join(name.split()).casefold()
    return _COLUMN_ALIASES.get(key, name)


def _looks_like_header(names: list[str]) -> bool:
    keys = {" ".join(name.split()).casefold() for name in names}
    has_index_or_ts = "index" in keys or "ts" in keys
    has_mass = bool(keys & {"weight", "y value", "yvalue"})
    return has_index_or_ts and (has_mass or "t" in keys or "x value" in keys or "hf" in keys)


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
      column names (e.g. Index Ts t HF Weight Tr)
      optional units (e.g. [#] [deg C] [s] [mW] [mg] [deg C])
      whitespace-separated numeric rows

    Older STA exports may start with a date / Curve Name preamble and use
    'x value' / 'y value' for time and mass. Those are mapped to t and Weight.
    The units row is optional. If the next row is numeric, default units are used.
    """
    file_path = Path(path)
    # Instrument exports often use Latin-1 degree symbols (0xB0), not UTF-8.
    text = file_path.read_text(encoding="latin-1")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"{file_path} needs a header and data.")

    header_i = None
    names: list[str] = []
    for index, line in enumerate(lines):
        candidate = [_normalize_column_name(part) for part in _split_header_fields(line)]
        if _looks_like_header(candidate):
            header_i = index
            names = candidate
            break
    if header_i is None:
        raise ValueError(f"{file_path}: no TGA column header found.")

    raw_units = _split_header_fields(lines[header_i + 1]) if header_i + 1 < len(lines) else []
    has_units_row = any("[" in field for field in raw_units)
    if has_units_row:
        units = [unit.strip("[]") for unit in raw_units]
        data_start = header_i + 2
        if len(units) == len(names) - 1:
            units = [""] + units
        if len(names) != len(units):
            raise ValueError(
                f"Header has {len(names)} names but units row has {len(units)} fields."
            )
    else:
        units = [_default_unit(name) for name in names]
        data_start = header_i + 1

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
