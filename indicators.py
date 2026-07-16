"""
Berekeningen voor TDI (Traders Dynamic Index) en RCI3Lines.
Dit is de Python-versie van de logica uit het Pine Script (tdi_rci3_combo_signal.pine),
zodat de conditie hetzelfde werkt als op TradingView.
"""

import numpy as np
import pandas as pd


def rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.fillna(100)
    return result


def compute_tdi(close: pd.Series, rsi_len: int, signal_len: int, band_len: int, band_mult: float):
    rsi_val = rsi(close, rsi_len)
    signal_line = rsi_val.rolling(signal_len).mean()
    basis = rsi_val.rolling(band_len).mean()
    dev = band_mult * rsi_val.rolling(band_len).std(ddof=0)
    upper_band = basis + dev
    lower_band = basis - dev
    return {
        "price_line": rsi_val,
        "signal_line": signal_line,
        "upper_band": upper_band,
        "lower_band": lower_band,
    }


def _rci_window(window: np.ndarray) -> float:
    n = len(window)
    price_rank = pd.Series(window).rank(method="min", ascending=False).values
    time_rank = np.arange(n, 0, -1)
    d = time_rank - price_rank
    d2sum = np.sum(d ** 2)
    return 100 * (1 - (6 * d2sum) / (n * (n ** 2 - 1)))


def rci(close: pd.Series, length: int) -> pd.Series:
    return close.rolling(length).apply(_rci_window, raw=True)


def compute_signal(df: pd.DataFrame, cfg) -> dict:
    close = df["close"]

    tdi = compute_tdi(close, cfg.TDI_RSI_LEN, cfg.TDI_SIGNAL_LEN, cfg.TDI_BAND_LEN, cfg.TDI_BAND_MULT)
    rci_short = rci(close, cfg.RCI_SHORT_LEN)

    price_line_last = tdi["price_line"].iloc[-1]
    upper_band_last = tdi["upper_band"].iloc[-1]
    lower_band_last = tdi["lower_band"].iloc[-1]
    rci_short_last = rci_short.iloc[-1]

    tdi_above_band = bool(price_line_last > upper_band_last)
    rci_above_level = bool(rci_short_last > cfg.RCI_LEVEL)
    both_true_long = tdi_above_band and rci_above_level

    tdi_below_band = bool(price_line_last < lower_band_last)
    rci_below_level = bool(rci_short_last < -cfg.RCI_LEVEL)
    both_true_short = tdi_below_band and rci_below_level

    return {
        "both_true_long": both_true_long,
        "both_true_short": both_true_short,
        "tdi_above_band": tdi_above_band,
        "rci_above_level": rci_above_level,
        "tdi_below_band": tdi_below_band,
        "rci_below_level": rci_below_level,
        "price_line": float(price_line_last),
        "upper_band": float(upper_band_last),
        "lower_band": float(lower_band_last),
        "rci_short": float(rci_short_last),
        "close": float(close.iloc[-1]),
    }
