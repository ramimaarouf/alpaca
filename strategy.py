# strategy.py
# Pure strategy logic for DailyRotationLongShortBot

from datetime import timedelta

# ---- Constants ----
LONG = "LONG"
SHORT = "SHORT"


# ---- Indicator Calculation ----
def compute_indicators(prices, params):
    """
    Returns dict of indicators or None if insufficient data
    """
    if len(prices) < params["SMA_SLOW"]:
        return None

    sma_fast = sum(prices[-params["SMA_FAST"]:]) / params["SMA_FAST"]
    sma_slow = sum(prices[-params["SMA_SLOW"]:]) / params["SMA_SLOW"]
    roc = (prices[-1] - prices[-params["ROC"]]) / prices[-params["ROC"]]

    return {
        "sma_fast": sma_fast,
        "sma_slow": sma_slow,
        "roc": roc
    }


# ---- Scoring ----
def score_asset(prices, indicators):
    """
    Momentum-based scoring system
    """
    score = 0

    if prices[-1] > indicators["sma_slow"]:
        score += 2
    if indicators["sma_fast"] > indicators["sma_slow"]:
        score += 1
    if indicators["roc"] > 0:
        score += 1

    return score


# ---- Ranking ----
def rank_assets(store):
    """
    Returns list of (score, symbol) sorted descending
    """
    ranked = []

    for symbol, record in store.items():
        ranked.append((record.get("score", -999), symbol))

    ranked.sort(reverse=True, key=lambda x: x[0])
    return ranked


# ---- Target Selection ----
def select_targets(ranked, params):
    """
    Select top longs and bottom shorts
    """
    targets = {}

    top_longs = ranked[:params["TOP_LONGS"]]
    bottom_shorts = ranked[-params["BOTTOM_SHORTS"]:]

    for _, symbol in top_longs:
        targets[symbol] = LONG

    for _, symbol in bottom_shorts:
        targets[symbol] = SHORT

    return targets


# ---- Cooldown Logic ----
def in_cooldown(last_trade_date, today, cooldown_days):
    if last_trade_date is None:
        return False
    return today - last_trade_date < timedelta(days=cooldown_days)


# ---- Take-Profit Logic ----
def check_take_profit(portfolio, store, params):
    """
    Returns list of symbols to close due to take-profit
    """
    to_close = []

    for symbol, pos in portfolio["positions"].items():
        price = store[symbol]["prices"][-1]
        entry = pos["entry_price"]

        if pos["side"] == LONG and price >= entry * (1 + params["TAKE_PROFIT_PCT"]):
            to_close.append(symbol)

        elif pos["side"] == SHORT and price <= entry * (1 - params["TAKE_PROFIT_PCT"]):
            to_close.append(symbol)

    return to_close


# ---- Rotation Logic ----
def find_positions_to_close(portfolio, targets, store, today, params):
    """
    Closes positions that are no longer in target universe
    """
    to_close = []

    for symbol, pos in portfolio["positions"].items():
        if symbol not in targets:
            last_trade = store[symbol].get("last_trade_date")
            if not in_cooldown(last_trade, today, params["COOLDOWN_DAYS"]):
                to_close.append(symbol)

    return to_close


# ---- Open Candidates ----
def find_positions_to_open(portfolio, targets, store, today, params):
    """
    Returns list of symbols eligible to open
    """
    to_open = []

    for symbol, side in targets.items():
        if symbol in portfolio["positions"]:
            continue

        last_trade = store[symbol].get("last_trade_date")
        if in_cooldown(last_trade, today, params["COOLDOWN_DAYS"]):
            continue

        to_open.append(symbol)

    return to_open


# ---- Full Strategy Evaluation ----
def evaluate_strategy(store, portfolio, params, today):
    """
    Main strategy entry point.
    Returns dict with targets and trade decisions.
    """

    # Rank assets
    ranked = rank_assets(store)

    # Select target positions
    targets = select_targets(ranked, params)

    # Determine exits
    take_profit_closes = check_take_profit(portfolio, store, params)
    rotation_closes = find_positions_to_close(
        portfolio, targets, store, today, params
    )

    # Merge closes (avoid duplicates)
    closes = list(set(take_profit_closes + rotation_closes))

    # Determine entries
    opens = find_positions_to_open(
        portfolio, targets, store, today, params
    )

    return {
        "ranked": ranked,
        "targets": targets,
        "close": closes,
        "open": opens
    }
