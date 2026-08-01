"""
Backtest van de TDI+RCI3Lines-strategie op BTC/USD, 1h-timeframe.
Regels (simpel, zoals afgesproken):
  - Entry op de OPEN van de candle NA het signaal (long of short)
  - Risk/Reward 1:1, met 1% stop-loss en 1% take-profit vanaf entry
  - Win = TP geraakt vóór SL, Loss = SL geraakt vóór TP (candle-voor-candle gecheckt)
  - Data wordt gesplitst: eerste 2/3 = trainingsperiode, laatste 1/3 = testperiode
    (puur ter info, voor dit simpele 1:1-testje wordt niet geoptimaliseerd,
    maar de opsplitsing laat wel zien of de resultaten consistent blijven)

Haalt zelf 2 jaar aan historische 1h-candles op via ccxt/Kraken (gepagineerd,
want 1 API-call geeft maar een beperkt aantal candles terug).
"""

import time
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd

# ================= INSTELLINGEN =================
SYMBOL = "BTC/USD"
TIMEFRAME = "1h"
YEARS_BACK = 2
RISK_PCT = 0.01      # 1% stop-loss
REWARD_PCT = 0.01    # 2% take-profit (R:R 1:2)
MAX_HOLD_CANDLES = 200  # als na zoveel candles nog niks geraakt is: sluit op close (timeout)

# TDI/RCI-instellingen (zelfde als de live bot)
TDI_RSI_LEN = 13
TDI_SIGNAL_LEN = 7
TDI_BAND_LEN = 34
TDI_BAND_MULT = 1.6185
RCI_SHORT_LEN = 9
RCI_LEVEL = 80


def rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(100)


def _rci_window(window: np.ndarray) -> float:
    n = len(window)
    price_rank = pd.Series(window).rank(method="min", ascending=False).values
    time_rank = np.arange(n, 0, -1)
    d = time_rank - price_rank
    d2sum = np.sum(d ** 2)
    return 100 * (1 - (6 * d2sum) / (n * (n ** 2 - 1)))


def rci(close: pd.Series, length: int) -> pd.Series:
    return close.rolling(length).apply(_rci_window, raw=True)


def fetch_historical_ohlcv(exchange, symbol, timeframe, years_back):
    """Haalt gepagineerd historische candles op tot years_back jaar terug."""
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    since = exchange.milliseconds() - years_back * 365 * 24 * 60 * 60 * 1000
    all_candles = []

    while True:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=720)
        if not candles:
            break
        all_candles.extend(candles)
        last_ts = candles[-1][0]
        if last_ts <= since:
            break
        since = last_ts + tf_ms
        if last_ts >= exchange.milliseconds() - tf_ms:
            break
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    rsi_val = rsi(close, TDI_RSI_LEN)
    basis = rsi_val.rolling(TDI_BAND_LEN).mean()
    dev = TDI_BAND_MULT * rsi_val.rolling(TDI_BAND_LEN).std(ddof=0)
    upper_band = basis + dev
    lower_band = basis - dev
    rci_short = rci(close, RCI_SHORT_LEN)

    tdi_above = rsi_val > upper_band
    tdi_below = rsi_val < lower_band
    rci_above = rci_short > RCI_LEVEL
    rci_below = rci_short < -RCI_LEVEL

    both_long = tdi_above & rci_above
    both_short = tdi_below & rci_below

    # Signaal = state gaat van False -> True (zelfde logica als de live bot)
    signal_long = both_long & ~both_long.shift(1).fillna(False)
    signal_short = both_short & ~both_short.shift(1).fillna(False)

    df = df.copy()
    df["signal_long"] = signal_long
    df["signal_short"] = signal_short
    return df


def simulate_trades(df: pd.DataFrame) -> pd.DataFrame:
    trades = []
    n = len(df)

    for i in range(n - 1):
        direction = None
        if df["signal_long"].iloc[i]:
            direction = "LONG"
        elif df["signal_short"].iloc[i]:
            direction = "SHORT"
        if direction is None:
            continue

        entry_idx = i + 1  # entry op open van volgende candle
        if entry_idx >= n:
            continue
        entry_price = df["open"].iloc[entry_idx]

        if direction == "LONG":
            sl = entry_price * (1 - RISK_PCT)
            tp = entry_price * (1 + REWARD_PCT)
        else:
            sl = entry_price * (1 + RISK_PCT)
            tp = entry_price * (1 - REWARD_PCT)

        outcome = None
        exit_price = None
        exit_idx = None

        for j in range(entry_idx, min(entry_idx + MAX_HOLD_CANDLES, n)):
            high = df["high"].iloc[j]
            low = df["low"].iloc[j]

            if direction == "LONG":
                hit_tp = high >= tp
                hit_sl = low <= sl
            else:
                hit_tp = low <= tp
                hit_sl = high >= sl

            if hit_tp and hit_sl:
                # Beide binnen dezelfde candle geraakt - conservatief: SL telt (worst case)
                outcome = "LOSS"
                exit_price = sl
                exit_idx = j
                break
            elif hit_tp:
                outcome = "WIN"
                exit_price = tp
                exit_idx = j
                break
            elif hit_sl:
                outcome = "LOSS"
                exit_price = sl
                exit_idx = j
                break

        if outcome is None:
            # Timeout: sluit op de laatst beschikbare close
            exit_idx = min(entry_idx + MAX_HOLD_CANDLES, n) - 1
            exit_price = df["close"].iloc[exit_idx]
            if direction == "LONG":
                outcome = "WIN" if exit_price > entry_price else "LOSS"
            else:
                outcome = "WIN" if exit_price < entry_price else "LOSS"

        pct_result = (
            (exit_price - entry_price) / entry_price
            if direction == "LONG"
            else (entry_price - exit_price) / entry_price
        )

        trades.append({
            "signal_idx": i,
            "entry_idx": entry_idx,
            "entry_time": pd.to_datetime(df["timestamp"].iloc[entry_idx], unit="ms"),
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "outcome": outcome,
            "pct_result": pct_result,
        })

    return pd.DataFrame(trades)


def print_stats(trades: pd.DataFrame, label: str):
    if len(trades) == 0:
        print(f"\n=== {label}: geen trades ===")
        return
    n = len(trades)
    wins = (trades["outcome"] == "WIN").sum()
    win_rate = wins / n * 100
    total_pct = trades["pct_result"].sum() * 100
    avg_pct = trades["pct_result"].mean() * 100

    print(f"\n=== {label} ===")
    print(f"Aantal trades: {n}")
    print(f"Winrate: {win_rate:.1f}%  ({wins} win / {n - wins} loss)")
    print(f"Totaal resultaat (som van alle trade-percentages): {total_pct:+.2f}%")
    print(f"Gemiddeld resultaat per trade: {avg_pct:+.3f}%")


def main():
    print(f"Historische data ophalen: {SYMBOL} {TIMEFRAME}, {YEARS_BACK} jaar terug...")
    exchange = ccxt.kraken({"enableRateLimit": True})
    df = fetch_historical_ohlcv(exchange, SYMBOL, TIMEFRAME, YEARS_BACK)
    print(f"Opgehaald: {len(df)} candles, van {pd.to_datetime(df['timestamp'].iloc[0], unit='ms')} "
          f"tot {pd.to_datetime(df['timestamp'].iloc[-1], unit='ms')}")

    df = compute_signals(df)
    trades = simulate_trades(df)

    print_stats(trades, "ALLE DATA (2 jaar)")

    # Opsplitsen in trainings- en testperiode (2/3 - 1/3), puur ter info
    split_idx = int(len(df) * 2 / 3)
    split_time = df["timestamp"].iloc[split_idx]
    train_trades = trades[trades["entry_idx"] < split_idx]
    test_trades = trades[trades["entry_idx"] >= split_idx]

    print_stats(train_trades, "Eerste 2/3 (trainingsperiode)")
    print_stats(test_trades, "Laatste 1/3 (testperiode, 'ongezien')")

    # Sla alle trades op als CSV voor eventuele verdere analyse
    trades.to_csv("backtest_trades.csv", index=False)
    print("\nAlle trades opgeslagen in backtest_trades.csv")


if __name__ == "__main__":
    main()
