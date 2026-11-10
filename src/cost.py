"""Execution cost for a round trip.

A prediction market contract settles at $1 or $0. A round trip means one taker
fill to open and one to close, so a taker pays whichever is worse of:

  spread    the gap between the VWAP you can sell into and the VWAP you can buy
            out of, walked across real book levels for the size you asked for
  fee       rate * (p * (1 - p)) ** exponent per share, on each crossing leg

Both are quoted in basis points of the mid price, because a 1c spread is 500 bps
at p=0.02 and 20 bps at p=0.50. Any cost number without a price attached is
meaningless in this market, and that is the whole reason the study exists.

Shares vs dollars: book sizes are shares. Dollar notional at the touch is
size * price, so 1000 shares at 0.05 is a $50 position, not a $1000 position.
"""

CENTS = 1e4  # basis points per unit of price


def walk(levels, shares):
    """Average fill price for `shares` against `levels`.

    levels must already be ordered by worsening price: ascending for asks
    (cheapest first) or descending for bids (highest first).
    Returns (vwap, filled_shares) where filled_shares < shares means the book
    ran out.
    """
    remaining = float(shares)
    spent = 0.0
    filled = 0.0
    for price, size in levels:
        if remaining <= 0:
            break
        take = min(remaining, size)
        spent += take * price
        filled += take
        remaining -= take
    if filled <= 0:
        return None, 0.0
    return spent / filled, filled


def fee_per_share(price, rate, exponent=1.0):
    """Taker fee per share, from the fee formula Polymarket publishes.

        fee = shares * feeRate * p * (1 - p)

    The rate comes from the market's own feeSchedule, so a geopolitics market
    (rate 0) prices at zero without a special case, and a crypto market prices at
    0.07. Makers pay nothing, so fee_legs should be 0 if you are the maker.
    """
    if not rate or not price:
        return 0.0
    p = min(max(price, 0.0), 1.0)
    return float(rate) * (p * (1.0 - p)) ** float(exponent or 1.0)


def depth(levels, touch, within):
    """Dollar notional resting within `within` of the touch on this side.

    Measured against the best price on the same side rather than the mid, because
    on a thin book the first ask can sit several ticks away from the mid and
    counting from the mid reports an empty book that is not empty.
    """
    if not touch:
        return 0.0
    total = 0.0
    for price, size in levels:
        if abs(price - touch) <= within + 1e-12:
            total += price * size
    return total


def round_trip(book, shares, fee_rate=0.0, fee_exponent=1.0, fee_legs=2):
    """Cost of buying then selling `shares`, in bps of mid.

    fee_legs=2 charges the taker fee on entry and exit. Set 1 if you only ever
    cross once and hold to a market resolving at $1 or $0.
    """
    if not book:
        return None
    bids = sorted(book["bids"], key=lambda level: level[0], reverse=True)
    asks = sorted(book["asks"], key=lambda level: level[0])
    if len(bids) < 1 or len(asks) < 1:
        return None

    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0:
        return None

    buy_vwap, bought = walk(asks, shares)
    sell_vwap, sold = walk(bids, shares)
    tick = book.get("tick_size") or 0.001

    row = {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "tick": tick,
        "shares": shares,
        "bought": bought,
        "sold": sold,
        "notional_usd": round(mid * min(bought, sold), 2),
        # the structural floor at this price: one tick is this many bps
        "tick_floor_bps": round(tick / mid * CENTS, 1),
        "quoted_spread_bps": round((best_ask - best_bid) / mid * CENTS, 1),
        "quoted_spread_cents": round((best_ask - best_bid) * 100, 3),
        "depth_1c_usd": round(depth(asks, best_ask, 0.01) + depth(bids, best_bid, 0.01), 0),
        "depth_2c_usd": round(depth(asks, best_ask, 0.02) + depth(bids, best_bid, 0.02), 0),
        "depth_5c_usd": round(depth(asks, best_ask, 0.05) + depth(bids, best_bid, 0.05), 0),
        "complete": bought >= shares and sold >= shares,
    }

    if not (buy_vwap and sell_vwap):
        return None

    cost_of_crossing = buy_vwap - sell_vwap  # positive: you pay this
    one_fee = fee_per_share(mid, fee_rate, fee_exponent)
    fee = one_fee * fee_legs

    row.update({
        "buy_vwap": round(buy_vwap, 5),
        "sell_vwap": round(sell_vwap, 5),
        # in and out again, paying the spread twice over and two fees
        "spread_bps": round(cost_of_crossing / mid * CENTS, 1),
        "fee_bps": round(fee / mid * CENTS, 1),
        "total_bps": round((cost_of_crossing + fee) / mid * CENTS, 1),
        # entry only, measured against the mid, for a position held to resolution
        "entry_bps": round((buy_vwap - mid + one_fee) / mid * CENTS, 1),
    })
    return row


def floor_bps(mid, tick):
    """Cheapest possible round trip: the quoted spread cannot be under one tick."""
    if not mid:
        return None
    return tick / mid * CENTS
