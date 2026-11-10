"""Take a cost snapshot of the live order books.

    python src/measure.py --markets 150 --sizes 100,1000,10000

Writes one JSON line per (outcome token, trade size) into data/snapshot-<date>.jsonl.

The legacy_bps column reproduces the mistake this study started with: reading the
book arrays in the order the API returns them, which is worst price first, so the
"spread" it measures is the full width of the book (0.001 to 0.999) rather than
the quoted spread. It is kept in the output so the correction can be checked
against the old numbers instead of taken on trust.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cost
import pmbook

ROOT = Path(__file__).resolve().parent.parent

# The schema of a snapshot row. Anything the cost model computes but nothing
# reads afterwards is dropped here, which keeps the files to about 1.8MB each.
ROW_FIELDS = (
    "ts", "round", "token_id", "market_id", "question", "tags", "volume_24h",
    "liquidity_clob", "fee_rate", "shares", "legacy_bps", "mid", "best_bid",
    "best_ask", "tick", "tick_floor_bps", "quoted_spread_bps", "quoted_spread_cents",
    "spread_bps", "fee_bps", "total_bps", "entry_bps", "depth_5c_usd",
    "notional_usd", "complete",
)


def legacy_bps(book, shares):
    """The original measurement. Order of the arrays taken at face value."""
    bids, asks = book["bids"], book["asks"]
    bid, _ = cost.walk(bids, shares)          # bids as returned, worst first
    ask, _ = cost.walk(list(reversed(asks)), shares)  # asks as returned, worst first
    if not bid or not ask:
        return None
    last = book.get("last_trade") or (book["bids"][0][0] + book["asks"][0][0]) / 2
    if not last:
        return None
    return round((ask - bid) / last * cost.CENTS, 1)


def collect(markets_n, sizes, rounds, interval):
    raw = pmbook.markets(limit=100, pages=max(1, markets_n // 100 + 1))
    tag_map = pmbook.market_tags(pages=max(1, markets_n // 100 + 1))
    views = [pmbook.market_view(record) for record in raw[:markets_n]]
    views = [v for v in views if v["tokens"] and v["volume_24h"]]
    for view in views:
        view["tags"] = tag_map.get(view["market_id"], [])
    print(f"{len(views)} markets, {sum(1 for v in views if v['tags'])} with tags", file=sys.stderr)

    rows = []
    for round_index in range(rounds):
        if round_index:
            time.sleep(interval)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        tokens = [token for view in views for token in view["tokens"]]
        books = {}
        for start in range(0, len(tokens), 50):
            books.update(pmbook.books(tokens[start:start + 50]))

        for view in views:
            for token in view["tokens"]:
                book = books.get(str(token))
                if not book or not book["bids"] or not book["asks"]:
                    continue
                for shares in sizes:
                    trip = cost.round_trip(book, shares, view["fee_rate"] or 0.0,
                                           view["fee_exponent"] or 1.0)
                    if not trip or not trip.get("total_bps"):
                        continue
                    # only fields something downstream reads, so the file stays small
                    rows.append({
                        "ts": stamp,
                        "round": round_index,
                        "token_id": str(token),
                        "market_id": view["market_id"],
                        "question": view["question"],
                        "tags": view["tags"],
                        "volume_24h": view["volume_24h"],
                        "liquidity_clob": view["liquidity_clob"],
                        "fee_rate": view["fee_rate"],
                        "shares": shares,
                        "legacy_bps": legacy_bps(book, shares),
                        **trip,
                    })
                    rows[-1] = {k: v for k, v in rows[-1].items() if k in ROW_FIELDS}
        print(f"round {round_index + 1}/{rounds}: {len(rows)} rows", file=sys.stderr)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", type=int, default=150)
    parser.add_argument("--sizes", default="100,1000,10000")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--interval", type=int, default=60,
                        help="seconds between rounds, for a stability check")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    rows = collect(args.markets, sizes, args.rounds, args.interval)
    if not rows:
        print("no rows collected", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path(args.out) if args.out else ROOT / "data" / f"snapshot-{stamp}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
