import requests
import time
import logging
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_TOKEN = "8101812061:AAFN-XUVsadzv7LvmnI-dtGhkSgvuuB2n5M"
CHAT_ID = "8144437671"
ALERT_THRESHOLD = 0.0020  # 0.20% difference

# Check interval (seconds) - every 5 minutes
CHECK_INTERVAL = 300

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================
# TELEGRAM FUNCTION
# ============================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram message sent!")
        else:
            logger.error(f"Telegram error: {response.text}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")

# ============================================
# DELTA EXCHANGE FUNDING RATES
# ============================================
def get_delta_funding_rates():
    rates = {}
    try:
        url = "https://api.delta.exchange/v2/tickers"
        response = requests.get(url, timeout=10)
        data = response.json()

        if "result" in data:
            for ticker in data["result"]:
                symbol = ticker.get("symbol", "")
                funding_rate = ticker.get("funding_rate", None)
                contract_type = ticker.get("contract_type", "")

                # Only perpetual contracts
                if contract_type == "perpetual_futures" and funding_rate is not None:
                    try:
                        rates[symbol] = float(funding_rate)
                    except:
                        pass
        logger.info(f"Delta: {len(rates)} coins fetched")
    except Exception as e:
        logger.error(f"Delta API error: {e}")
    return rates

# ============================================
# COINDCX FUNDING RATES
# ============================================
def get_coindcx_funding_rates():
    rates = {}
    try:
        url = "https://api.coindcx.com/exchange/v1/derivatives/futures/funding_rates"
        response = requests.get(url, timeout=10)
        data = response.json()

        if isinstance(data, list):
            for item in data:
                symbol = item.get("symbol", "")
                funding_rate = item.get("funding_rate", None)
                if symbol and funding_rate is not None:
                    try:
                        rates[symbol] = float(funding_rate)
                    except:
                        pass
        elif isinstance(data, dict):
            for symbol, info in data.items():
                try:
                    if isinstance(info, dict):
                        rates[symbol] = float(info.get("funding_rate", 0))
                    else:
                        rates[symbol] = float(info)
                except:
                    pass

        logger.info(f"CoinDCX: {len(rates)} coins fetched")
    except Exception as e:
        logger.error(f"CoinDCX API error: {e}")
    return rates

# ============================================
# NORMALIZE SYMBOL NAMES
# ============================================
def normalize_symbol(symbol):
    """Convert symbols to common format like BTCUSDT"""
    symbol = symbol.upper()
    symbol = symbol.replace("-PERP", "").replace("_PERP", "")
    symbol = symbol.replace("-PERPETUAL", "").replace("_PERPETUAL", "")
    symbol = symbol.replace("-USD", "USDT").replace("_USD", "USDT")
    symbol = symbol.replace("-", "").replace("_", "")
    return symbol

# ============================================
# COMPARE AND FIND OPPORTUNITIES
# ============================================
def find_opportunities(delta_rates, coindcx_rates):
    opportunities = []

    # Normalize Delta symbols
    delta_normalized = {}
    for symbol, rate in delta_rates.items():
        norm = normalize_symbol(symbol)
        delta_normalized[norm] = {"rate": rate, "original": symbol}

    # Normalize CoinDCX symbols
    coindcx_normalized = {}
    for symbol, rate in coindcx_rates.items():
        norm = normalize_symbol(symbol)
        coindcx_normalized[norm] = {"rate": rate, "original": symbol}

    # Find common coins
    common_coins = set(delta_normalized.keys()) & set(coindcx_normalized.keys())
    logger.info(f"Common coins found: {len(common_coins)}")

    for coin in common_coins:
        delta_rate = delta_normalized[coin]["rate"]
        coindcx_rate = coindcx_normalized[coin]["rate"]
        difference = abs(delta_rate - coindcx_rate)

        if difference >= ALERT_THRESHOLD:
            opportunities.append({
                "coin": coin,
                "delta_rate": delta_rate,
                "coindcx_rate": coindcx_rate,
                "difference": difference,
                "delta_symbol": delta_normalized[coin]["original"],
                "coindcx_symbol": coindcx_normalized[coin]["original"]
            })

    # Sort by difference (highest first)
    opportunities.sort(key=lambda x: x["difference"], reverse=True)
    return opportunities

# ============================================
# FORMAT ALERT MESSAGE
# ============================================
def format_alert(opportunities):
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    msg = f"🚨 <b>FUNDING RATE ALERT!</b>\n"
    msg += f"🕐 {now}\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n\n"

    for opp in opportunities[:5]:  # Top 5 only
        delta_r = opp['delta_rate'] * 100
        dcx_r = opp['coindcx_rate'] * 100
        diff = opp['difference'] * 100

        # Who to short and who to long
        if opp['delta_rate'] > opp['coindcx_rate']:
            short_on = "Delta Exchange"
            long_on = "CoinDCX"
        else:
            short_on = "CoinDCX"
            long_on = "Delta Exchange"

        msg += f"💰 <b>{opp['coin']}</b>\n"
        msg += f"   Delta Rate: {delta_r:.4f}%\n"
        msg += f"   CoinDCX Rate: {dcx_r:.4f}%\n"
        msg += f"   📊 Difference: <b>{diff:.4f}%</b>\n"
        msg += f"   ✅ SHORT on: {short_on}\n"
        msg += f"   ✅ LONG on: {long_on}\n"
        msg += f"   ⚡ Per day profit: ~{diff*3:.4f}%\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"⚠️ DYOR - Fees calculate karke hi trade karo!"
    return msg

# ============================================
# MAIN BOT LOOP
# ============================================
def main():
    logger.info("🚀 Funding Rate Alert Bot Started!")
    send_telegram("🤖 <b>Funding Rate Bot Started!</b>\n\nMain har 5 minute mein rates check karunga.\nAlert threshold: 0.20%\n\n✅ Bot active hai!")

    last_alert_coins = set()

    while True:
        try:
            logger.info("Checking funding rates...")

            # Fetch rates
            delta_rates = get_delta_funding_rates()
            coindcx_rates = get_coindcx_funding_rates()

            if not delta_rates:
                logger.warning("Delta rates empty!")
            if not coindcx_rates:
                logger.warning("CoinDCX rates empty!")

            # Find opportunities
            opportunities = find_opportunities(delta_rates, coindcx_rates)

            if opportunities:
                # Check if these are new alerts
                current_coins = {o['coin'] for o in opportunities}
                new_coins = current_coins - last_alert_coins

                if new_coins or not last_alert_coins:
                    msg = format_alert(opportunities)
                    send_telegram(msg)
                    last_alert_coins = current_coins
                    logger.info(f"Alert sent for {len(opportunities)} opportunities!")
                else:
                    logger.info("Same opportunities as before - no new alert")
            else:
                logger.info("No opportunities above threshold right now")
                # Reset last alerts so next time it alerts again
                last_alert_coins = set()

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            send_telegram(f"⚠️ Bot Error: {str(e)}\nRestarting...")

        logger.info(f"Waiting {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
