"""
Hoofdscript: haalt candle-data op voor elke coin/timeframe, berekent TDI + RCI3Lines,
en stuurt een Telegram-bericht zodra de combinatie-conditie van "niet waar" naar "waar" gaat.

Wordt periodiek uitgevoerd (bijv. elke 5 min via GitHub Actions cron).
Elke timeframe wordt alleen daadwerkelijk gecheckt op het moment dat de candle
van die timeframe net gesloten is (dus 1u alleen elk heel uur, 1d alleen om
middernacht UTC, etc.) - dat scheelt veel onnodige API-calls.

Status wordt bijgehouden in STATE_FILE zodat er geen dubbele alerts komen
zolang de conditie aanhoudt.
"""

import json
import os
import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

import config as cfg
from indicators import compute_signal
from telegram import send_telegram_message

# Lengte van elke timeframe in minuten - gebruikt om te bepalen wanneer een
# candle van die timeframe daadwerkelijk sluit.
TIMEFRAME_MINUTES = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def load_state() -> dict:
    if os.path.exists(cfg.STATE_FILE):
        with open(cfg.STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(cfg.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def should_check_timeframe(timeframe: str, now: datetime) -> bool:
    """
    True als deze timeframe nu net een candle heeft gesloten (uitgaande van
    een cron die elke 5 minuten draait, op UTC-tijd).
    """
    tf_minutes = TIMEFRAME_MINUTES[timeframe]
    minutes_since_midnight = now.hour * 60 + now.minute
    return minutes_since_midnight % tf_minutes == 0


def fetch_closed_ohlcv(exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """
    Haalt candles op en verwijdert de laatste candle als die nog niet
    volledig gesloten is (exchanges geven vaak de 'live' candle-in-wording
    mee als laatste rij).
    """
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])

    tf_ms = TIMEFRAME_MINUTES[timeframe] * 60 * 1000
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    if len(df) > 0:
        last_close_time = df["timestamp"].iloc[-1] + tf_ms
        if last_close_time > now_ms:
            df = df.iloc[:-1]  # laatste candle is nog niet gesloten, weggooien

    return df


def format_message(symbol: str, timeframe: str, result: dict, direction: str) -> str:
    if direction == "LONG":
        return (
            f"🚨 <b>LONG signaal: {symbol}</b> ({timeframe})\n"
            f"📈 TDI groen (snel) boven bovenband + RCI rood boven {cfg.RCI_LEVEL}\n"
            f"💰 Prijs: {result['close']}\n"
            f"TDI fast line: {result['price_line']:.2f} | upper band: {result['upper_band']:.2f}\n"
            f"RCI(short): {result['rci_short']:.2f}"
        )
    else:
        return (
            f"🔻 <b>SHORT signaal: {symbol}</b> ({timeframe})\n"
            f"📉 TDI groen (snel) onder onderband + RCI rood onder -{cfg.RCI_LEVEL}\n"
            f"💰 Prijs: {result['close']}\n"
            f"TDI fast line: {result['price_line']:.2f} | lower band: {result['lower_band']:.2f}\n"
            f"RCI(short): {result['rci_short']:.2f}"
        )


def get_top_n_symbols(exchange, quote: str, n: int) -> list:
    """Haalt de top N USDT-pairs op basis van 24u-handelsvolume op."""
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    candidates = []
    for symbol, market in markets.items():
        if market.get("quote") != quote or not market.get("active", True):
            continue
        ticker = tickers.get(symbol)
        if not ticker or ticker.get("quoteVolume") is None:
            continue
        candidates.append((symbol, ticker["quoteVolume"]))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in candidates[:n]]


def main():
    exchange_class = getattr(ccxt, cfg.EXCHANGE)
    exchange = exchange_class({"enableRateLimit": True})

    if cfg.USE_TOP_N_BY_VOLUME:
        coins = get_top_n_symbols(exchange, cfg.QUOTE_CURRENCY, cfg.TOP_N)
        print(f"Top {cfg.TOP_N} op volume opgehaald: {len(coins)} pairs.")
    else:
        coins = cfg.COINS

    now = datetime.now(timezone.utc)
    state = load_state()
    new_alerts = []

    for timeframe in cfg.TIMEFRAMES:
        if not should_check_timeframe(timeframe, now):
            print(f"{timeframe}: candle nog niet gesloten, sla over.")
            continue

        for symbol in coins:
            key_long = f"{symbol}:{timeframe}:long"
            key_short = f"{symbol}:{timeframe}:short"
            try:
                df = fetch_closed_ohlcv(exchange, symbol, timeframe, cfg.CANDLE_LIMIT)
                if len(df) < cfg.RCI_LONG_LEN + 5:
                    print(f"Te weinig candles voor {symbol}:{timeframe}, sla over.")
                    continue

                result = compute_signal(df, cfg)

                # LONG
                previous_long = state.get(key_long, False)
                current_long = result["both_true_long"]
                if current_long and not previous_long:
                    send_telegram_message(format_message(symbol, timeframe, result, "LONG"))
                    new_alerts.append(key_long)
                    print(f"SIGNAAL: {key_long}")
                state[key_long] = current_long

                # SHORT
                previous_short = state.get(key_short, False)
                current_short = result["both_true_short"]
                if current_short and not previous_short:
                    send_telegram_message(format_message(symbol, timeframe, result, "SHORT"))
                    new_alerts.append(key_short)
                    print(f"SIGNAAL: {key_short}")
                state[key_short] = current_short

            except Exception as e:
                print(f"Fout bij {symbol}:{timeframe}: {e}")

            time.sleep(exchange.rateLimit / 1000)  # netjes binnen exchange rate limit blijven

    save_state(state)
    print(f"Klaar. {len(new_alerts)} nieuwe signalen: {new_alerts}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
