# TDI + RCI3Lines Crypto Scanner

Monitort meerdere coins/timeframes op je eigen TDI + RCI3Lines combo-signaal
en stuurt een Telegram-bericht zodra het signaal afgaat. Draait gratis via
GitHub Actions (cron, elke 5 minuten).

## Setup (eenmalig)

### 1. Telegram bot maken
1. Open Telegram, zoek `@BotFather`
2. Stuur `/newbot`, volg de stappen, kies een naam
3. Je krijgt een **token** terug zoals `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ` — bewaar deze

### 2. Je Chat ID ophalen
1. Stuur een willekeurig bericht naar je eigen bot (zoek 'm op via de naam die je gaf)
2. Open in je browser: `https://api.telegram.org/bot<JOUW_TOKEN>/getUpdates`
3. Zoek in de JSON-response naar `"chat":{"id":123456789,...}` — dat getal is je Chat ID

### 3. Repo naar GitHub pushen
1. Maak een nieuwe (privé mag ook) GitHub-repository aan
2. Push deze hele map ernaartoe:
   ```
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin <JOUW_REPO_URL>
   git push -u origin main
   ```

### 4. Secrets instellen in GitHub
1. Ga naar je repo → **Settings** → **Secrets and variables** → **Actions**
2. Voeg twee **Repository secrets** toe:
   - `TELEGRAM_TOKEN` = je bot-token
   - `TELEGRAM_CHAT_ID` = je chat-ID

### 5. Klaar
De workflow (`.github/workflows/scanner.yml`) draait vanaf nu automatisch elke
5 minuten. Je kunt 'm ook handmatig starten via het **Actions**-tabblad in
GitHub → kies "Crypto TDI+RCI3Lines Scanner" → **Run workflow**.

## Coins/timeframes aanpassen

Open `config.py` en pas de lijsten `COINS` en `TIMEFRAMES` aan. Geen andere
bestanden hoeven gewijzigd te worden.

## Lokaal testen (optioneel, voordat je naar GitHub pusht)

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN="jouw_token"
export TELEGRAM_CHAT_ID="jouw_chat_id"
python scanner.py
```

Zonder de env variables gezet te hebben print het script het bericht gewoon
in de terminal in plaats van te versturen, zodat je kan zien of de conditie-
logica goed werkt.

## Belangrijk om te weten

- Dit is **geen financieel advies** en geen garantie dat het signaal winstgevend
  is — het is een 1-op-1 vertaling van de conditie uit je Pine Script.
- De RCI-berekening in Python is een zo goed mogelijke match van de klassieke
  RCI-formule. Vergelijk gerust een paar waarden met je TradingView-chart om
  te controleren of ze overeenkomen; laat het weten als er afwijkingen zijn
  dan stemmen we de formule verder af.
- GitHub Actions gratis quotum: 2000 minuten/maand voor privé-repositories
  (onbeperkt voor publieke). Een run van dit script duurt typisch een paar
  seconden tot een minuut, dus elke 5 minuten draaien past hier ruim binnen.
