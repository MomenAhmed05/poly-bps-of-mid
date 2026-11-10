"""Polymarket API access.

Two hosts:

  gamma-api.polymarket.com  market metadata, one record per outcome-market
  clob.polymarket.com       order book, price history, last trade

Everything here is stdlib. No auth, no key. Public read endpoints only.

Field notes that cost me time, recorded so they do not cost anyone else time:

  clobTokenIds / outcomes      JSON encoded strings inside a JSON payload
  bids / asks                  returned worst price first, so bids[0] is the
                               minimum bid and bids[-1] is the best bid. Reading
                               the array in order gives you the widest spread in
                               the book, not the quoted one.
  size                         outcome shares, not dollars. A share settles at $1
                               so dollar notional is size * price.
  liquidity vs liquidityClob   `liquidity` copies the parent event and repeats on
                               every child market. `liquidityClob` is per market.
  feeSchedule                  {rate, exponent, takerOnly, rebateRate}. Fee is
                               rate * (p * (1 - p)) ** exponent per share.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = {"User-Agent": "polymarket-cost-study/1.0"}

# Rate limits are undocumented. One request per second has not been refused.
_MIN_INTERVAL = 0.15
_last_call = [0.0]


def _get(url, data=None, tries=4, timeout=30):
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("only http(s) endpoints are allowed")
    for attempt in range(tries):
        wait = _MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        req = urllib.request.Request(url, headers=UA, data=data)  # noqa: S310 (scheme checked above)
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())  # noqa: S310
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                return None
            if attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == tries - 1:
                raise
        time.sleep(1.0 * (attempt + 1))
    return None


def _loads(value, default=None):
    """Gamma returns some list fields as JSON strings inside the JSON."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return value if value is not None else (default if default is not None else [])


def markets(limit=100, pages=5, order="volume24hr", active=True):
    """Page the markets endpoint. Returns raw Gamma records."""
    out = []
    for page in range(pages):
        query = {
            "limit": limit,
            "offset": page * limit,
            "order": order,
            "ascending": "false",
            "active": "true" if active else "false",
            "closed": "false",
        }
        batch = _get(f"{GAMMA}/markets?" + urllib.parse.urlencode(query))
        if not batch:
            break
        out.extend(batch)
        if len(batch) < limit:
            break
    return out


def market_tags(pages=3, limit=100):
    """Map market id to its event tags.

    The markets endpoint drops them (`include_tags` does nothing) and the copy
    nested under markets[].events[].tags is empty, so the tags only exist on the
    events endpoint. One extra paged call buys the whole cross-section.
    """
    out = {}
    for page in range(pages):
        batch = _get(f"{GAMMA}/events?limit={limit}&offset={page * limit}"
                     f"&order=volume24hr&ascending=false&active=true&closed=false")
        if not batch:
            break
        for event in batch:
            labels = [t.get("label") for t in (event.get("tags") or []) if t.get("label")]
            if not labels:
                continue
            for market in event.get("markets") or []:
                market_id = market.get("id")
                if not market_id:
                    continue
                known = out.setdefault(market_id, [])
                for label in labels:
                    if label not in known:
                        known.append(label)
        if len(batch) < limit:
            break
    return out


def market_view(raw):
    """Flatten a Gamma record into the fields the cost model needs."""
    tokens = _loads(raw.get("clobTokenIds"))
    outcomes = _loads(raw.get("outcomes"))
    prices = _loads(raw.get("outcomePrices"))
    events = raw.get("events") or []
    tags = []
    for event in events[:1]:
        tags = [t.get("label") for t in (event.get("tags") or []) if t.get("label")]
    fee = raw.get("feeSchedule") or {}
    return {
        "market_id": raw.get("id"),
        "condition_id": raw.get("conditionId"),
        "question": raw.get("question"),
        "slug": raw.get("slug"),
        "outcomes": outcomes,
        "tokens": tokens,
        "outcome_prices": prices,
        "last_trade": _num(raw.get("lastTradePrice")),
        "best_bid": _num(raw.get("bestBid")),
        "best_ask": _num(raw.get("bestAsk")),
        "reported_spread": _num(raw.get("spread")),
        "volume_24h": _num(raw.get("volume24hr")),
        "volume_total": _num(raw.get("volume")),
        "liquidity_clob": _num(raw.get("liquidityClob")),
        "tick_size": _num(raw.get("orderPriceMinTickSize")) or 0.001,
        "min_order_size": _num(raw.get("orderMinSize")),
        "neg_risk": bool(raw.get("negRisk")),
        "end_date": raw.get("endDate"),
        "resolution_source": raw.get("resolutionSource"),
        "fees_enabled": bool(raw.get("feesEnabled")),
        "fee_rate": _num(fee.get("rate")),
        "fee_exponent": _num(fee.get("exponent")),
        "fee_type": raw.get("feeType"),
        "tags": tags,
    }


def book(token_id):
    """Single order book. Returns a normalised dict or None."""
    raw = _get(f"{CLOB}/book?token_id={urllib.parse.quote(str(token_id))}")
    return normalise_book(raw) if raw else None


def books(token_ids):
    """Batch order books. One request for up to a few hundred tokens."""
    payload = json.dumps([{"token_id": str(t)} for t in token_ids]).encode()
    raw = _get(f"{CLOB}/books", data=payload)
    if not raw:
        return {}
    out = {}
    for record in raw:
        norm = normalise_book(record)
        if norm:
            out[norm["token_id"]] = norm
    return out


def normalise_book(raw):
    if not raw:
        return None
    token = raw.get("asset_id")
    if not token:
        return None
    bids = _levels(raw.get("bids"))
    asks = _levels(raw.get("asks"))
    # Ascending sort makes the index meaning explicit instead of relying on the
    # API's order: bids[-1] is the best bid, asks[0] is the best ask.
    bids.sort(key=lambda level: level[0])
    asks.sort(key=lambda level: level[0])
    return {
        "token_id": token,
        "bids": bids,
        "asks": asks,
        "tick_size": _num(raw.get("tick_size")),
        "min_order_size": _num(raw.get("min_order_size")),
        "last_trade": _num(raw.get("last_trade_price")),
        "timestamp": raw.get("timestamp"),
        "hash": raw.get("hash"),
    }


def history(token_id, interval="max", fidelity=60):
    """Price history. The `market` parameter takes a token id, not a condition id."""
    raw = _get(f"{CLOB}/prices-history?market={urllib.parse.quote(str(token_id))}"
               f"&interval={interval}&fidelity={fidelity}")
    if not raw:
        return []
    return [(int(p["t"]), float(p["p"])) for p in raw.get("history") or []]


def midpoint(token_id):
    raw = _get(f"{CLOB}/midpoint?token_id={urllib.parse.quote(str(token_id))}")
    return _num(raw.get("mid")) if raw else None


def _levels(rows):
    out = []
    for row in rows or []:
        price, size = _num(row.get("price")), _num(row.get("size"))
        if price and size:
            out.append((price, size))
    return out


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
