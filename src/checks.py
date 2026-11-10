"""Re-check every number quoted in the docs against the committed files.

    python src/checks.py

Prints a table of claim, documented value, measured value. Exits non-zero if
anything drifts. The point is that no sentence in README.md or docs/ has to be
believed: each figure in those files appears here with the code that produces
it, and running this is the proof.

Rows marked `docs` come from Polymarket's published fee page rather than from
the snapshot, so they cannot move. Everything else is derived from data.
"""

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SNAPSHOT = ROOT / "data" / "snapshot-2026-11-10.jsonl"
REPEAT = ROOT / "data" / "snapshot-2026-11-10-repeat.jsonl"
LAG = ROOT / "data" / "lag.jsonl"


def load(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0] * len(values)
    for position, index in enumerate(order):
        out[index] = position + 1
    return out


def spearman(left, right):
    rx, ry = ranks(left), ranks(right)
    n = len(left)
    total = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * total / (n * (n * n - 1))


def med(values):
    """Median as a float, so callers can round it without a None branch."""
    clean = [float(v) for v in values if v is not None]
    return statistics.median(clean) if clean else 0.0


def at_size(rows, shares):
    return [r for r in rows if r["shares"] == shares]


def live_probe():
    """Re-measure the API behaviour claimed in docs/method.md. Network required.

    Three claims, each of which was originally an observation rather than
    something in the snapshot: history needs a token id, include_tags does
    nothing, and Gamma's cached touch drifts from the live book.
    """
    import pmbook

    raw = pmbook.markets(limit=100, pages=2)
    views = [pmbook.market_view(record) for record in raw]

    print("\nlive probe")
    print("-" * 84)

    if views and views[0]["tokens"]:
        token = views[0]["tokens"][0]
        by_token = len(pmbook.history(token))
        by_condition = len(pmbook.history(views[0]["condition_id"]))
        print(f"history by token id {by_token} points, by condition id {by_condition} points")

    tagged = pmbook._get(pmbook.GAMMA + "/markets?limit=1&include_tags=true"
                         "&active=true&closed=false&order=volume24hr&ascending=false")
    print(f"include_tags returns a tags field: {'tags' in (tagged or [{}])[0]}")

    tokens = [token for view in views for token in view["tokens"]]
    books = {}
    for start in range(0, len(tokens), 50):
        books.update(pmbook.books(tokens[start:start + 50]))
    gaps = []
    for view in views:
        book = books.get(str(view["tokens"][0])) if view["tokens"] else None
        if not book or not book["bids"] or not book["asks"]:
            continue
        if view["best_bid"] is None or view["best_ask"] is None:
            continue
        live_bid = max(price for price, _size in book["bids"])
        live_ask = min(price for price, _size in book["asks"])
        gaps.append(max(abs(view["best_bid"] - live_bid), abs(view["best_ask"] - live_ask)))
    if gaps:
        exact = sum(1 for g in gaps if g < 1e-9)
        drift = sum(1 for g in gaps if g >= 0.0005)
        print(f"gamma touch against live book over {len(gaps)} markets: "
              f"{100 * exact / len(gaps):.1f}% identical, "
              f"{100 * drift / len(gaps):.1f}% off by at least a tick, "
              f"largest gap {max(gaps):.3f}")
    return 0


def main():
    if "--live" in sys.argv:
        return live_probe()

    rows = load(SNAPSHOT)
    repeat = load(REPEAT)
    lag = load(LAG)

    volume = sum(r["volume_24h"] or 0 for r in rows) / 3
    legacy = [r["legacy_bps"] / r["total_bps"] for r in rows
              if r["legacy_bps"] and r["total_bps"] and r["total_bps"] > 0]
    legacy_sorted = sorted(legacy)

    cheap = [r for r in at_size(rows, 1000) if r["total_bps"] <= 100]
    tick_violations = sum(1 for r in rows
                          if r["tick_floor_bps"] and r["quoted_spread_bps"] < r["tick_floor_bps"] - 0.5)
    at_one_tick = sum(1 for r in rows
                      if r["tick_floor_bps"] and
                      abs(r["quoted_spread_bps"] / r["tick_floor_bps"] - 1.0) < 0.05)

    first = {r["token_id"]: r for r in rows if r["round"] == 0 and r["shares"] == 100}
    last = {r["token_id"]: r for r in rows if r["round"] == 2 and r["shares"] == 100}
    shared = set(first) & set(last)
    same_touch = sum(1 for t in shared
                     if first[t]["best_bid"] == last[t]["best_bid"]
                     and first[t]["best_ask"] == last[t]["best_ask"])

    base = at_size(rows, 1000)
    base = [r for r in base if r["round"] == 0]
    cheap_side = [r for r in rows if r["mid"] <= 0.02]
    dear_side = [r for r in rows if r["mid"] >= 0.98]
    entry_cheap = med([r["entry_bps"] for r in cheap_side])
    entry_dear = med([r["entry_bps"] for r in dear_side])

    quiet = [r["quiet_bars"] for r in lag]
    cover = [r["cover_hours"] for r in lag if r["cover_hours"]]
    cover_sorted = sorted(cover)
    stick = [r["sticks"] for r in lag if r["sticks"] is not None]
    autocorr = [r["ar1"] for r in lag if r["ar1"] is not None]

    claims = [
        # (label, documented, measured, source)
        ("markets in snapshot", 128, len({r["market_id"] for r in rows}), "data"),
        ("outcome tokens", 256, len({r["token_id"] for r in rows}), "data"),
        ("rows", 2298, len(rows), "data"),
        ("24h volume across universe", 133044291, round(volume), "data"),
        ("rows on a fee-paying market", 1704, sum(1 for r in rows if (r["fee_rate"] or 0) > 0), "data"),
        ("rows with no fee schedule at all", 594, sum(1 for r in rows if r["fee_rate"] is None), "data"),
        ("distinct fee rates across the universe", 4,
         len({round(r["fee_rate"], 3) for r in rows if (r["fee_rate"] or 0) > 0}), "data"),
        ("book filled at 1,000 shares (%)", 96,
         round(100 * sum(1 for r in at_size(rows, 1000) if r["complete"]) / len(at_size(rows, 1000))), "data"),
        ("round trip at 100 shares", 618, round(med([r["total_bps"] for r in at_size(rows, 100)])), "data"),
        ("round trip at 1,000 shares", 666, round(med([r["total_bps"] for r in base])), "data"),
        ("round trip at 10,000 shares", 1020, round(med([r["total_bps"] for r in at_size(rows, 10000)])), "data"),
        ("book filled at 10,000 shares (%)", 86,
         round(100 * sum(1 for r in at_size(rows, 10000) if r["complete"]) / len(at_size(rows, 10000))), "data"),
        ("legacy overstatement, median", 57, round(med(legacy)), "data"),
        ("legacy overstatement, 90th pct", 3688, round(legacy_sorted[int(0.9 * (len(legacy_sorted) - 1))]), "data"),
        ("tokens round-tripped under 100 bps at 1,000 shares (%)", 15.3,
         round(100 * len(cheap) / len(at_size(rows, 1000)), 1), "data"),
        ("lowest mid among those tokens", 0.9415, round(min((r["mid"] for r in cheap), default=0.0), 4), "data"),
        ("rows with quoted spread under one tick", 0, tick_violations, "data"),
        ("rows quoting exactly one tick (%)", 61.6, round(100 * at_one_tick / len(rows), 1), "data"),
        ("identical touch between first and last sample", 214, same_touch, "data"),
        ("tokens compared for stability", 254, len(shared), "data"),
        ("entry cost on the cheap side (bps)", 2499, round(entry_cheap), "data"),
        ("entry cost on the dear side (bps)", 11, round(entry_dear), "data"),
        ("entry ratio, cheap over dear", 223, round(entry_cheap / entry_dear), "data"),
        ("tag assignments across all rows", 18246, sum(len(r["tags"]) for r in rows), "data"),
        ("spearman volume24h against total cost", -0.042,
         round(spearman([r["volume_24h"] or 0 for r in base], [r["total_bps"] for r in base]), 3), "data"),
        ("spearman liquidityClob against total cost", -0.198,
         round(spearman([r["liquidity_clob"] or 0 for r in base], [r["total_bps"] for r in base]), 3), "data"),
        ("spearman liquidityClob against depth within 5c", 0.59,
         round(spearman([r["liquidity_clob"] or 0 for r in base], [r["depth_5c_usd"] or 0 for r in base]), 2), "data"),
        ("spearman volume24h against depth within 5c", 0.233,
         round(spearman([r["volume_24h"] or 0 for r in base], [r["depth_5c_usd"] or 0 for r in base]), 3), "data"),
        ("hourly bars with no change (%)", 68.7, round(med(quiet), 1), "data"),
        ("median bars per token in the lag sample", 668, round(med([r["bars"] for r in lag])), "data"),
        ("median days covered by each history", 31, round(med([r["span_days"] for r in lag])), "data"),
        ("hours of movement to cover one entry", 3.8, round(med(cover), 1), "data"),
        ("same, 90th percentile", 17.3, round(cover_sorted[int(0.9 * (len(cover_sorted) - 1))], 1), "data"),
        ("consecutive changes keeping sign (%)", 44.3, round(med(stick), 1), "data"),
        ("autocorrelation of changes", -0.076, round(med(autocorr), 3), "data"),
        ("second run, round trip at 1,000 shares", 666,
         round(med([r["total_bps"] for r in at_size(repeat, 1000)])), "data"),
        ("second run, round trip at 10,000 shares", 945,
         round(med([r["total_bps"] for r in at_size(repeat, 10000)])), "data"),
        ("second run, markets", 125, len({r["market_id"] for r in repeat}), "data"),
        # published, not measured here
        ("fee for 100 shares at 0.50, rate 0.07 (USD)", 1.75,
         round(100 * 0.07 * 0.50 * 0.50, 2), "docs"),
    ]

    failures = 0
    print(f"{'claim':52s} {'documented':>12} {'measured':>12}  ")
    print("-" * 84)
    for label, documented, measured, source in claims:
        if measured is None:
            marker = "MISSING"
            failures += 1
        elif isinstance(documented, float):
            ok = abs(measured - documented) <= max(0.02, abs(documented) * 0.02)
            marker = "ok" if ok else "DRIFT"
        else:
            ok = int(measured) == int(documented)
            marker = "ok" if ok else "DRIFT"
        if marker != "ok":
            failures += 1
        print(f"{label:52s} {documented:>12} {measured:>12}  {marker}  [{source}]")

    print(f"\n{len(claims) - failures} of {len(claims)} claims match the committed data")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
