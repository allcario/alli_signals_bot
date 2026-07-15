"""
Configuratie voor de TDI + RCI3Lines crypto scanner.
Pas COINS en TIMEFRAMES hier aan - de rest van de code hoeft niet gewijzigd te worden.
"""

# Exchange (moet ondersteund worden door ccxt: https://github.com/ccxt/ccxt#supported-cryptocurrency-exchanges)
EXCHANGE = "binance"

# Coins/pairs die gemonitord worden.
# Optie A: handmatige lijst invullen hieronder in COINS
# Optie B: automatisch top N op 24u-volume laten bepalen (zie USE_TOP_N_BY_VOLUME)
COINS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
]

# Zet op True om automatisch de top N USDT-pairs op 24u-handelsvolume te gebruiken
# in plaats van de handmatige COINS-lijst hierboven.
USE_TOP_N_BY_VOLUME = True
TOP_N = 100
QUOTE_CURRENCY = "USDT"  # alleen pairs tegen deze quote-munt meenemen

# Timeframes die gemonitord worden (moeten geldige ccxt-timeframes zijn)
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]

# Aantal historische candles dat opgehaald wordt om de indicatoren te berekenen
# (moet ruim boven de langste indicator-lengte liggen, zie hieronder: RCI long = 52)
CANDLE_LIMIT = 150

# ================= TDI SETTINGS =================
TDI_RSI_LEN = 13
TDI_SIGNAL_LEN = 7          # "gele lijn"
TDI_BAND_LEN = 34
TDI_BAND_MULT = 1.6185

# ================= RCI3LINES SETTINGS =================
RCI_SHORT_LEN = 9            # "rode lijn" - dit is de lijn die tegen het niveau wordt gecheckt
RCI_MID_LEN = 26
RCI_LONG_LEN = 52
RCI_LEVEL = 80

# Bestand waarin de laatste bekende signaal-status wordt bijgehouden
# (zodat je niet elke run opnieuw een alert krijgt zolang de conditie aanhoudt)
STATE_FILE = "state.json"
