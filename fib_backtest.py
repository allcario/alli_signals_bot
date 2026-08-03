"""
Backtest: Asian-sessie Fibonacci-extensie strategie op BTC/USD.

Regels:
  1. Aziatische sessie = 00:00 - 07:00 UTC (elke dag)
  2. Bepaal de high en low van die sessie -> 0% = low, 100% = high
  3. Fib-extensies:
       127.2%-niveau = high + 0.272 * (high - low)   -> SHORT als prijs dit raakt
       -27.2%-niveau = low  - 0.272 * (high - low)   -> LONG  als prijs dit raakt
  4. Na de sessie (vanaf 07:00 UTC) wordt gewacht op de EERSTE aanraking van een
     van beide niveaus, die dag. Zodra er 1 geraakt is, wordt de andere genegeerd
     (max 1 trade per dag).
  5. Entry = het niveau zelf (op het moment dat de candle het niveau doorkruist)
  6. Stop-loss = 1.5x ATR(14, 1h) vanaf entry
  7. Take-profit = 1R (zelfde afstand als de SL, R:R 1:1)
  8. Fees worden ook hier meegerekend (zelfde als de andere backtest)
"""

import time

import ccxt
import numpy as np
import pandas as pd

# ================= INSTELLINGEN =================
SYMBOL = "BTC/USD"
TIMEFRAME = "1h"
YEARS_BACK = 2

ASIAN_SESSION_START_UTC = 0   # 00:00 UTC
ASIAN_SESSION_END_UTC = 7     # 07:00 UTC (exclusief) - sessie duurt dus 00:00-06:59

FIB_EXTENSION = 0.272  # 127.2% en -27.2%

ATR_LEN = 14
ATR_MULT = 1.5
MAX_HOLD_CANDLES = 200

FEE_PCT_PER_SIDE = 0.001  # 0.1% per kant, 0.2% round-trip


def fetch_historical_ohlcv(exchange, symbol, timeframe, years_back):
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    since = exchange.milliseconds() - years_back * 365 * 24 * 60 * 60 * 1000
    all_candles = []
    while True:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=300)
        if not candles:
            break
        all_candles.extend(candles)
        last_ts = candles[-1][0]
        if last_ts <= since:
            break
        since = last_ts + tf_ms
        if since >= exchange.milliseconds() - tf_ms:
            break
        time.sleep(exchange.rateLimit / 1000)
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def compute_atr(df: pd.DataFrame, length: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()


def add_datetime_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dt = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["date"] = dt.dt.date
    df["hour"] = dt.dt.hour
    df["atr"] = compute_atr(df, ATR_LEN)
    return df


def get_daily_fib_levels(df: pd.DataFrame) -> dict:
    """Per kalenderdag (UTC): bepaal de Aziatische-sessie high/low en de fib-niveaus."""
    session_mask = (df["hour"] >= ASIAN_SESSION_START_UTC) & (df["hour"] < ASIAN_SESSION_END_UTC)
    session_df = df[session_mask]

    levels = {}
    for date, group in session_df.groupby("date"):
        session_high = group["high"].max()
        session_low = group["low"].min()
        rng = session_high - session_low
        if rng <= 0:
            continue
        levels[date] = {
            "session_high": session_high,
            "session_low": session_low,
            "level_short": session_high + FIB_EXTENSION * rng,   # 127.2%
            "level_long": session_low - FIB_EXTENSION * rng,     # -27.2%
        }
    return levels


def simulate_trades(df: pd.DataFrame, levels: dict) -> pd.DataFrame:
    trades = []
    n = len(df)
    traded_dates = set()

    for i in range(n):
        row = df.iloc[i]
        # Alleen candles NA de Aziatische sessie meenemen als mogelijke trigger
        if row["hour"] < ASIAN_SESSION_END_UTC:
            continue

        date = row["date"]
        if date not in levels or date in traded_dates:
            continue

        lvl = levels[date]
        atr = row["atr"]
        if pd.isna(atr) or atr <= 0:
            continue

        direction = None
        entry_price = None

        # Check welke van de 2 niveaus deze candle raakt (high/low doorkruist het niveau)
        touched_short = row["high"] >= lvl["level_short"]
        touched_long = row["low"] <= lvl["level_long"]

        if touched_short and touched_long:
            # Beide in dezelfde candle geraakt - neem de richting die het dichtst bij open ligt (simpel, conservatief: sla deze dag over)
            continue
        elif touched_short:
            direction = "SHORT"
            entry_price = lvl["level_short"]
        elif touched_long:
            direction = "LONG"
            entry_price = lvl["level_long"]
        else:
            continue

        traded_dates.add(date)  # max 1 trade per dag

        sl_distance = ATR_MULT * atr
        if direction == "LONG":
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance  # 1R
        else:
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance

        outcome = None
        exit_price = None

        for j in range(i, min(i + MAX_HOLD_CANDLES, n)):
            high = df["high"].iloc[j]
            low = df["low"].iloc[j]
            if direction == "LONG":
                hit_tp = high >= tp
                hit_sl = low <= sl
            else:
                hit_tp = low <= tp
                hit_sl = high >= sl

            if hit_tp and hit_sl:
                outcome, exit_price = "LOSS", sl
                break
            elif hit_tp:
                outcome, exit_price = "WIN", tp
                break
            elif hit_sl:
                outcome, exit_price = "LOSS", sl
                break

        if outcome is None:
            exit_idx = min(i + MAX_HOLD_CANDLES, n) - 1
            exit_price = df["close"].iloc[exit_idx]
            if direction == "LONG":
                outcome = "WIN" if exit_price > entry_price else "LOSS"
            else:
                outcome = "WIN" if exit_price < entry_price else "LOSS"

        pct_result = (
            (exit_price - entry_price) / entry_price if direction == "LONG"
            else (entry_price - exit_price) / entry_price
        )
        r_multiple = pct_result / (sl_distance / entry_price)  # resultaat in R
        pct_result_net = pct_result - FEE_PCT_PER_SIDE * 2

        trades.append({
            "date": date,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "outcome": outcome,
            "pct_result": pct_result,
            "pct_result_net": pct_result_net,
            "r_multiple": r_multiple,
        })

    return pd.DataFrame(trades)


def print_stats(trades: pd.DataFrame, label: str):
    if len(trades) == 0:
        print(f"\n=== {label}: geen trades ===")
        return
    n = len(trades)
    wins = (trades["outcome"] == "WIN").sum()
    win_rate = wins / n * 100
    total_r = trades["r_multiple"].sum()
    total_pct_gross = trades["pct_result"].sum() * 100
    total_pct_net = trades["pct_result_net"].sum() * 100

    print(f"\n=== {label} ===")
    print(f"Aantal trades: {n}")
    print(f"Winrate: {win_rate:.1f}%  ({wins} win / {n - wins} loss)")
    print(f"Totaal resultaat in R-multiples: {total_r:+.2f}R")
    print(f"Totaal resultaat (bruto, %): {total_pct_gross:+.2f}%")
    print(f"Totaal resultaat (netto na fees, %): {total_pct_net:+.2f}%")


def main():
    print(f"Historische data ophalen: {SYMBOL} {TIMEFRAME}, {YEARS_BACK} jaar terug...")
    exchange = ccxt.coinbase({"enableRateLimit": True})
    df = fetch_historical_ohlcv(exchange, SYMBOL, TIMEFRAME, YEARS_BACK)
    print(f"Opgehaald: {len(df)} candles, van {pd.to_datetime(df['timestamp'].iloc[0], unit='ms')} "
          f"tot {pd.to_datetime(df['timestamp'].iloc[-1], unit='ms')}")

    df = add_datetime_cols(df)
    levels = get_daily_fib_levels(df)
    print(f"Aantal dagen met geldige Aziatische-sessie-range: {len(levels)}")

    trades = simulate_trades(df, levels)
    print_stats(trades, "ALLE DATA (2 jaar)")

    if len(trades) > 0:
        split_idx = int(len(trades) * 2 / 3)
        print_stats(trades.iloc[:split_idx], "Eerste 2/3 (trainingsperiode)")
        print_stats(trades.iloc[split_idx:], "Laatste 1/3 (testperiode, 'ongezien')")

    trades.to_csv("fib_backtest_trades.csv", index=False)
    print("\nAlle trades opgeslagen in fib_backtest_trades.csv")


if __name__ == "__main__":
    main()
