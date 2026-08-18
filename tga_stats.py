"""Mass-loss onset, cutoff, and DTG peak temperatures from a TGA run."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tga_data import TgaDataset


@dataclass(frozen=True)
class MassLossStats:
    """Characteristic temperatures in deg C and residual-mass percentages."""

    t5_c: float
    t10_c: float
    t50_c: float
    t95_c: float
    t_onset_c: float
    t_cutoff_c: float
    t_peak_c: float
    dtg_peak_pct_per_c: float
    mass_loss_pct: float
    mass_final_pct: float
    heating_rate_c_min: float
    isothermal: bool


def _moving_average(y: np.ndarray, window: int) -> np.ndarray:
    window = max(int(window), 1)
    if window % 2 == 0:
        window += 1
    if window <= 1 or window > len(y):
        return y.copy()
    kernel = np.ones(window) / window
    pad = window // 2
    return np.convolve(np.pad(y, pad, mode="edge"), kernel, mode="valid")


def _heating_rate_c_per_min(temperature: np.ndarray, time_s: np.ndarray) -> float:
    if len(temperature) < 20:
        return float("nan")
    i0, i1 = int(0.2 * len(temperature)), int(0.8 * len(temperature))
    dt = float(time_s[i1] - time_s[i0])
    if dt <= 0:
        return float("nan")
    return float((temperature[i1] - temperature[i0]) / dt * 60.0)


def mass_loss_stats(dataset: TgaDataset) -> MassLossStats:
    """
    T5/T50/T95 plus ASTM-style tangent onset/cutoff at the main DTG peak.

    Residual mass is 100% at the initial weight plateau. The main peak is the
    steepest loss while residual mass is still 12-90%, so a late residue
    burnout is not treated as the EC step.
    """
    ts_raw = np.asarray(dataset.series("Ts"), dtype=float)
    weight_raw = np.asarray(dataset.series("Weight"), dtype=float)
    try:
        time_s = np.asarray(dataset.series("t"), dtype=float)
    except KeyError:
        time_s = np.arange(len(ts_raw), dtype=float)
    try:
        tr = np.asarray(dataset.series("Tr"), dtype=float)
        heating_rate = _heating_rate_c_per_min(tr, time_s)
    except KeyError:
        heating_rate = _heating_rate_c_per_min(ts_raw, time_s)

    w0 = float(np.median(weight_raw[: min(50, len(weight_raw))]))
    if w0 == 0:
        w0 = float(weight_raw[0])
    mass_final_pct = float(100.0 * weight_raw[-1] / w0)
    isothermal = bool(np.isfinite(heating_rate) and abs(heating_rate) < 1.5)

    ts = ts_raw.copy()
    weight = weight_raw.copy()
    if not isothermal:
        order = np.argsort(ts)
        ts, weight = ts[order], weight[order]
        _, uniq = np.unique(ts, return_index=True)
        ts, weight = ts[uniq], weight[uniq]
    if len(ts) < 50:
        raise ValueError("Not enough points to compute mass-loss statistics.")

    mass = 100.0 * weight / w0
    mass_s = _moving_average(mass, 21)

    m_base = float(np.median(mass_s[: max(len(mass_s) // 12, 20)]))
    lost = m_base - mass_s
    idx_1 = int(np.argmax(lost >= 1.0))
    if lost[idx_1] >= 1.0:
        m_base = float(np.median(mass_s[: max(idx_1, 10)]))
        lost = m_base - mass_s

    m_end_run = float(np.median(mass_s[int(0.88 * len(mass_s)) :]))
    total_loss = m_base - m_end_run
    if total_loss < 0.5:
        raise ValueError("No significant mass-loss step found.")

    converted = lost / total_loss
    t_at: dict[str, float] = {}
    for frac, key in ((0.05, "t5_c"), (0.10, "t10_c"), (0.50, "t50_c"), (0.95, "t95_c")):
        i = int(np.argmax(converted >= frac))
        t_at[key] = float(ts[i]) if converted[i] >= frac else float("nan")

    if isothermal:
        return MassLossStats(
            t5_c=t_at["t5_c"],
            t10_c=t_at["t10_c"],
            t50_c=t_at["t50_c"],
            t95_c=t_at["t95_c"],
            t_onset_c=float("nan"),
            t_cutoff_c=float("nan"),
            t_peak_c=float("nan"),
            dtg_peak_pct_per_c=float("nan"),
            mass_loss_pct=float(total_loss),
            mass_final_pct=mass_final_pct,
            heating_rate_c_min=float(heating_rate),
            isothermal=True,
        )

    dtg = _moving_average(np.gradient(mass_s, ts), 31)

    main_mask = (mass_s <= 90.0) & (mass_s >= 12.0)
    if not np.any(main_mask):
        main_mask = np.ones(len(ts), dtype=bool)
    peak_i = int(np.argmin(np.where(main_mask, dtg, np.inf)))
    slope = float(dtg[peak_i])
    t_peak = float(ts[peak_i])
    m_peak = float(mass_s[peak_i])
    if slope >= -1e-6:
        raise ValueError("DTG peak is not a mass-loss step.")

    after = (ts >= t_peak + 8.0) & (ts <= t_peak + 40.0)
    if np.count_nonzero(after) >= 10:
        m_end_step = float(np.median(mass_s[after]))
    else:
        m_end_step = m_end_run

    t_onset = t_peak + (m_base - m_peak) / slope
    t_cutoff = t_peak + (m_end_step - m_peak) / slope

    return MassLossStats(
        t5_c=t_at["t5_c"],
        t10_c=t_at["t10_c"],
        t50_c=t_at["t50_c"],
        t95_c=t_at["t95_c"],
        t_onset_c=float(t_onset),
        t_cutoff_c=float(t_cutoff),
        t_peak_c=t_peak,
        dtg_peak_pct_per_c=slope,
        mass_loss_pct=float(total_loss),
        mass_final_pct=mass_final_pct,
        heating_rate_c_min=float(heating_rate),
        isothermal=isothermal,
    )


def _fmt_c(value: float) -> str:
    if not np.isfinite(value):
        return "    n/a"
    return f"{value:7.1f} C"


def format_stats(label: str, stats: MassLossStats) -> str:
    lines = [
        f"{label}",
        f"  T5 onset             {_fmt_c(stats.t5_c)}",
        f"  Tangent onset        {_fmt_c(stats.t_onset_c)}",
        f"  T50                  {_fmt_c(stats.t50_c)}",
        f"  DTG peak             {_fmt_c(stats.t_peak_c)}",
        f"  Main-step cutoff     {_fmt_c(stats.t_cutoff_c)}",
        f"  T95                  {_fmt_c(stats.t95_c)}",
        f"  Mass loss            {stats.mass_loss_pct:7.1f} %",
        f"  Final residual       {stats.mass_final_pct:7.1f} %",
    ]
    if stats.isothermal:
        lines.append(
            "  Note: furnace is a hold (heating rate ~0). "
            "Temperature statistics are not comparable to a ramp."
        )
    elif np.isfinite(stats.heating_rate_c_min):
        lines.append(f"  Heating rate         {stats.heating_rate_c_min:7.2f} C/min")
    return "\n".join(lines)
