"""
oanda_helper.py

Usage:
1) export OANDA_TOKEN="your_token_here"
2) export OANDA_ACCOUNT_ID="101-003-26750929-002"   # must be an account your token can access
3) (optionally) edit USE_PRACTICE below to False to use live URLs
4) python oanda_helper.py

This file uses requests (no external OANDA wrapper), so it's easy to debug.
"""

import os
import requests
import json
from typing import Optional, Dict

# -----------------------
# CONFIG: switch practice/live here
# -----------------------
USE_PRACTICE = True  # True => practice endpoints, False => live endpoints

# automatically read from env
TOKEN = os.getenv("OANDA_TOKEN")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")

if not TOKEN or not ACCOUNT_ID:
    raise SystemExit("Set OANDA_TOKEN and OANDA_ACCOUNT_ID environment variables before running.")

# base urls (do not change these strings)
BASE_PRACTICE = "https://api-fxpractice.oanda.com/v3"
BASE_LIVE = "https://api-fxtrade.oanda.com/v3"

BASE = BASE_PRACTICE if USE_PRACTICE else BASE_LIVE
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# -----------------------
# Helpers
# -----------------------
def _pretty(obj):
    try:
        return json.dumps(obj, indent=2)
    except Exception:
        return str(obj)

def _print_success(msg: str):
    print(f"SUCCESS: {msg}")

def _print_failed(msg: str):
    print(f"FAILED: {msg}")

def _get_account_summary(account_id: str) -> Optional[Dict]:
    """GET /accounts/{accountID}/summary - return dict or None"""
    url = f"{BASE}/accounts/{account_id}/summary"
    r = requests.get(url, headers=HEADERS, timeout=10)
    if r.status_code == 200:
        return r.json().get("account", {})
    else:
        # return None but provide a clear message if required by caller
        return None

# -----------------------
# Core: submit market buy order
# -----------------------
def submit_market_order_buy(account_id: str, instrument: str, units: int):
    """
    Submit a MARKET buy order.
    units: positive for buy (e.g., 100), negative for sell.
    This function prints a neat message on success/failure and returns API response dict.
    """
    url = f"{BASE}/accounts/{account_id}/orders"
    body = {
        "order": {
            "instrument": instrument,
            "units": str(units),   # OANDA expects string numeric
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }
    r = requests.post(url, headers=HEADERS, json=body, timeout=10)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw_text": r.text}

    if r.status_code in (200, 201):
        # success; determine if filled or created
        if "orderFillTransaction" in payload:
            t = payload["orderFillTransaction"]
            trade_id = t.get("tradeOpened", {}).get("tradeID") or t.get("tradeID") or "n/a"
            price = t.get("price") or t.get("averagePrice") or "n/a"
            # fetch updated account summary to show money left (balance)
            summary = _get_account_summary(account_id)
            bal = summary.get("balance") if summary else "n/a"
            _print_success(f"Market BUY filled. TradeID: {trade_id}, Price: {price}. New balance: {bal}")
        else:
            # order created but maybe pending (LIMIT/STOP) - for market usually immediate
            ord_tx = payload.get("orderCreateTransaction") or payload.get("order")
            ord_id = (ord_tx.get("id") if isinstance(ord_tx, dict) else "n/a")
            summary = _get_account_summary(account_id)
            bal = summary.get("balance") if summary else "n/a"
            _print_success(f"Order submitted (not filled immediately). OrderID: {ord_id}. Balance: {bal}")
    else:
        # failure
        err_msg = payload.get("errorMessage") or payload.get("error") or payload
        _print_failed(f"Submit MARKET BUY -> HTTP {r.status_code}. {err_msg}")

    return payload

# -----------------------
# Comments / Example code you can uncomment to SELL, LIMIT, STOP etc.
# (these are examples — leave commented or copy & change as needed)
# -----------------------


# SELL MARKET (units negative to sell)
# submit_market_order_buy(account_id=ACCOUNT_ID, instrument="EUR_USD", units=-100)

# LIMIT order (place an order to SELL 1000 units at price 1.20000)
limit_order_example = {
    "order": {
        "instrument": "EUR_USD",
        "units": "-1000",            # negative => sell
        "price": "1.20000",
        "type": "LIMIT",
        "timeInForce": "GTC",        # GTC = good till cancelled, FOK, IOC available
        "positionFill": "DEFAULT"
    }
}
# POST to /accounts/{accountID}/orders with json=limit_order_example

# STOP order (stop-loss style pending order)
stop_order_example = {
    "order": {
        "instrument": "EUR_USD",
        "units": "1000",
        "price": "1.05000",
        "type": "STOP",
        "timeInForce": "GTC",
        "positionFill": "DEFAULT"
    }
}

# MARKET_IF_TOUCHED (MIT) - becomes market order when price touches the trigger
mit_order_example = {
    "order": {
        "instrument": "EUR_USD",
        "units": "1000",
        "price": "1.10000",   # trigger
        "type": "MARKET_IF_TOUCHED",
        "timeInForce": "GTC",
        "positionFill": "DEFAULT"
    }
}


# -----------------------
# Cancel a pending order
# -----------------------
def cancel_order(account_id: str, order_id: str):
    """
    Cancels a pending order. Prints success/failure and returns API response.
    Endpoint: PUT /accounts/{accountID}/orders/{orderID}/cancel
    """
    url = f"{BASE}/accounts/{account_id}/orders/{order_id}/cancel"
    r = requests.put(url, headers=HEADERS, timeout=10)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw_text": r.text}

    if r.status_code in (200, 201):
        _print_success(f"Order {order_id} cancelled.")
    else:
        err_msg = payload.get("errorMessage") or payload
        _print_failed(f"Cancel order {order_id} -> HTTP {r.status_code}. {err_msg}")

    return payload

# -----------------------
# Get order list (all orders and pending orders)
# -----------------------
def get_orders(account_id: str, only_pending: bool = False):
    """
    GET /accounts/{accountID}/orders or GET /accounts/{accountID}/orders?state=PENDING
    Prints a succinct result.
    """
    if only_pending:
        url = f"{BASE}/accounts/{account_id}/orders?state=PENDING"
    else:
        url = f"{BASE}/accounts/{account_id}/orders"
    r = requests.get(url, headers=HEADERS, timeout=10)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw_text": r.text}

    if r.status_code == 200:
        orders = payload.get("orders", [])
        _print_success(f"Retrieved orders list ({len(orders)} orders).")
        # print only the orders list for clarity
        print(_pretty(orders))
    else:
        _print_failed(f"Get orders -> HTTP {r.status_code}. {payload}")

    return payload

# -----------------------
# Get pricing snapshot (polling)
# -----------------------
def get_prices(instruments: str):
    """
    GET /v3/accounts/{accountID}/pricing?instruments=EUR_USD,USD_JPY
    prints latest prices only for the instruments requested.
    """
    url = f"{BASE}/accounts/{ACCOUNT_ID}/pricing"
    params = {"instruments": instruments}
    r = requests.get(url, headers=HEADERS, params=params, timeout=10)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw_text": r.text}

    if r.status_code == 200:
        prices = payload.get("prices", [])
        _print_success(f"Pricing for {instruments} returned ({len(prices)} items).")
        # Print only the pricing objects:
        print(_pretty(prices))
    else:
        _print_failed(f"Get prices -> HTTP {r.status_code}. {payload}")

    return payload

# -----------------------
# Account summary
# -----------------------
def get_account_summary_print(account_id: str):
    """
    GET account summary and print concise details: balance, NAV, openTrades, marginUsed
    """
    url = f"{BASE}/accounts/{account_id}/summary"
    r = requests.get(url, headers=HEADERS, timeout=10)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw_text": r.text}

    if r.status_code == 200:
        acc = payload.get("account", {})
        bal = acc.get("balance")
        nav = acc.get("NAV") or acc.get("pl") or "n/a"
        open_trades = acc.get("openTradeCount", 0)
        margin_used = acc.get("marginUsed", "n/a")
        _print_success(f"Account summary - Balance: {bal}, OpenTrades: {open_trades}, MarginUsed: {margin_used}")
        # If you want to inspect raw account object, uncomment:
        # print(_pretty(acc))
    else:
        _print_failed(f"Get account summary -> HTTP {r.status_code}. {payload}")

    return payload

# -----------------------
# Example main usage
# -----------------------
if __name__ == "__main__":
    print(f"Using {'PRACTICE' if USE_PRACTICE else 'LIVE'} endpoints: {BASE}")
    print("Account ID:", ACCOUNT_ID)
    print("NOTE: Script will only execute the BUY MARKET example below. Uncomment others to run them.\n")

    # --- RUN the buy market example (this is active) ---
    # Buy 100 units of EUR_USD (change instrument/units as needed)
    buy_resp = submit_market_order_buy(account_id=ACCOUNT_ID, instrument="EUR_USD", units=100)

    # after order, show account summary
    get_account_summary_print(ACCOUNT_ID)

    # --- Examples you can run by uncommenting ---
    # get_orders(ACCOUNT_ID, only_pending=True)
    # cancel_order(ACCOUNT_ID, order_id="12345")   # replace 12345 with a real order id from get_orders
    # get_prices("EUR_USD,USD_JPY")
    # get_orders(ACCOUNT_ID, only_pending=False)

    # SELL market example (uncomment to run):
    # submit_market_order_buy(account_id=ACCOUNT_ID, instrument="EUR_USD", units=-100)

    # LIMIT / STOP / MIT examples:
    # To place any of the commented pending order bodies above, do:
    # requests.post(f"{BASE}/accounts/{ACCOUNT_ID}/orders", headers=HEADERS, json=limit_order_example)

    # -----------------------
    # Switching to LIVE
    # -----------------------
    # To use live instead of practice:
    # 1) set USE_PRACTICE = False at top of this file OR export an env var and read it here
    # 2) ensure your token is a LIVE token (practice tokens won't work against live endpoints)
    # 3) ensure ACCOUNT_ID is a live account id that your live token can access
    #
    # Always test with small units on practice first.
