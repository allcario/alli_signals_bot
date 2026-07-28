"""
Genereert een chart-afbeelding (PNG) bij een signaal: prijs-candles bovenaan,
TDI-paneel in het midden, RCI3Lines-paneel onderaan - vergelijkbaar met de
TradingView-indeling. Gebruikt standaardkleuren (geen custom TradingView-kleuren).
"""

import matplotlib
matplotlib.use("Agg")  # geen scherm nodig, alleen bestand wegschrijven
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from indicators import compute_signal_series, rci


def generate_chart(df: pd.DataFrame, cfg, symbol: str, timeframe: str, direction: str, out_path: str,
                    lookback: int = 60):
    """
    df: dataframe met 'timestamp' (ms) en 'close' (en evt. open/high/low voor candles)
    direction: "LONG" of "SHORT"
    out_path: waar de PNG wordt weggeschreven
    lookback: hoeveel candles worden getoond in de afbeelding
    """
    series = compute_signal_series(df, cfg)
    rci_mid = rci(df["close"], cfg.RCI_MID_LEN)
    rci_long = rci(df["close"], cfg.RCI_LONG_LEN)

    plot_df = df.tail(lookback).copy()
    dates = pd.to_datetime(plot_df["timestamp"], unit="ms")

    fig, (ax_price, ax_tdi, ax_rci) = plt.subplots(
        3, 1, figsize=(9, 9), sharex=True,
        gridspec_kw={"height_ratios": [3, 2, 2]},
        facecolor="#0d1117"
    )

    for ax in (ax_price, ax_tdi, ax_rci):
        ax.set_facecolor("#0d1117")
        ax.tick_params(colors="#c9d1d9", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#30363d")
        ax.grid(True, color="#21262d", linewidth=0.5)

    # ===== PANEEL 1: PRIJS (candles) =====
    has_ohlc = all(c in plot_df.columns for c in ["open", "high", "low"])
    if has_ohlc:
        for i, (_, row) in enumerate(plot_df.iterrows()):
            color = "#26a69a" if row["close"] >= row["open"] else "#ef5350"
            ax_price.plot([i, i], [row["low"], row["high"]], color=color, linewidth=0.8)
            ax_price.plot([i, i], [row["open"], row["close"]], color=color, linewidth=4)
    else:
        ax_price.plot(range(len(plot_df)), plot_df["close"], color="#26a69a", linewidth=1.2)

    ax_price.set_title(f"{symbol}  ·  {timeframe}  ·  Kraken", color="#c9d1d9", fontsize=11, loc="left")
    ax_price.set_ylabel("Prijs", color="#c9d1d9", fontsize=9)

    # ===== PANEEL 2: TDI =====
    price_line = series["price_line"].tail(lookback).values
    upper_band = series["upper_band"].tail(lookback).values
    lower_band = series["lower_band"].tail(lookback).values

    x = range(len(plot_df))
    ax_tdi.plot(x, upper_band, color="#8b949e", linewidth=1, linestyle="--", label="Upper band")
    ax_tdi.plot(x, lower_band, color="#8b949e", linewidth=1, linestyle="--", label="Lower band")
    ax_tdi.fill_between(x, lower_band, upper_band, color="#8b949e", alpha=0.08)
    ax_tdi.plot(x, price_line, color="#2ecc71", linewidth=1.6, label="TDI (groen)")
    ax_tdi.set_ylabel("TDI", color="#c9d1d9", fontsize=9)
    ax_tdi.legend(loc="upper left", fontsize=7, facecolor="#0d1117", edgecolor="#30363d", labelcolor="#c9d1d9")

    # ===== PANEEL 3: RCI3Lines =====
    rci_s = series["rci_short"].tail(lookback).values
    rci_m = rci_mid.tail(lookback).values
    rci_l = rci_long.tail(lookback).values

    ax_rci.axhline(cfg.RCI_LEVEL, color="#8b949e", linewidth=0.8, linestyle="--")
    ax_rci.axhline(-cfg.RCI_LEVEL, color="#8b949e", linewidth=0.8, linestyle="--")
    ax_rci.plot(x, rci_s, color="#ef5350", linewidth=1.6, label="RCI kort (rood)")
    ax_rci.plot(x, rci_m, color="#2ecc71", linewidth=1, label="RCI midden (groen)")
    ax_rci.plot(x, rci_l, color="#42a5f5", linewidth=1, label="RCI lang (blauw)")
    ax_rci.set_ylim(-110, 110)
    ax_rci.set_ylabel("RCI3Lines", color="#c9d1d9", fontsize=9)
    ax_rci.legend(loc="upper left", fontsize=7, facecolor="#0d1117", edgecolor="#30363d", labelcolor="#c9d1d9")

    last_x = len(plot_df) - 1
    marker_color = "#2ecc71" if direction == "LONG" else "#ef5350"
    for ax in (ax_price, ax_tdi, ax_rci):
        ax.axvline(last_x, color=marker_color, linewidth=1, linestyle=":")

    ax_price.scatter(
        [last_x], [plot_df["close"].iloc[-1]],
        color=marker_color, s=80, zorder=5,
        marker="^" if direction == "LONG" else "v"
    )

    n_ticks = 6
    tick_positions = list(range(0, len(plot_df), max(1, len(plot_df) // n_ticks)))
    tick_labels = [dates.iloc[i].strftime("%m-%d %H:%M") for i in tick_positions]
    ax_rci.set_xticks(tick_positions)
    ax_rci.set_xticklabels(tick_labels, rotation=30, ha="right")

    direction_label = "LONG" if direction == "LONG" else "SHORT"
    title_color = "#2ecc71" if direction == "LONG" else "#ef5350"
    fig.suptitle(f"{symbol}  {timeframe}  —  {direction_label}", color=title_color, fontsize=14, y=0.99, fontweight="bold")

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
