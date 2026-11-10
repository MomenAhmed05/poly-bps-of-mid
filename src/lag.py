"""How much the price moves against what it costs to get in.

The cost study answers what a taker pays. This answers whether there is enough
movement on the other side of that payment to matter. Both numbers are per
contract, so they can be divided.

    python src/lag.py --snapshot data/snapshot-2026-11-10.jsonl

For every token in the snapshot it pulls the full price history at hourly
fidelity and reports:

  move     mean absolute change per bar, in bps of the price it happened at
  cover    entry cost divided by that move: how many hours of average
           movement you have to capture to pay for one entry
  ar1      first-order autocorrelation of the price changes
  sticks   share of consecutive non-zero changes with the same sign, which is
           the whole question for a momentum rule at this frequency

Writes one JSON line per token so the result can be re-derived from the file.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import pmbook

ROOT = Path(__file__).resolve().parent.parent


def read_snapshot(path):
    source = Path(path)
    if not source.is_file():
        print(f"no such snapshot: {source}", file=sys.stderr)
        return []
    rows = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def ar1(series):
    if len(series) < 10:
        return None
    mean = statistics.fmean(series)
    centred = [x - mean for x in series]
    numerator = sum(centred[i] * centred[i - 1] for i in range(1, len(centred)))
    denominator = sum(x * x for x in centred)
    return round(numerator / denominator, 4) if denominator else None


def sticks(changes):
    """Same-sign share of consecutive non-zero changes."""
    moves = [c for c in changes if c]
    if len(moves) < 10:
        return None
    same = sum(1 for i in range(1, len(moves)) if (moves[i] > 0) == (moves[i - 1] > 0))
    return round(100.0 * same / (len(moves) - 1), 1)


def stats(history, entry_bps):
    if len(history) < 12:
        return None
    prices = [price for _ts, price in history]
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    # normalise each move by the price level it happened at
    moves_bps = [abs(c) / max(prices[i], 1e-6) * 1e4 for i, c in enumerate(changes)]
    if not moves_bps:
        return None
    mean_move = statistics.fmean(moves_bps)
    span_days = (history[-1][0] - history[0][0]) / 86400.0
    return {
        "bars": len(history),
        "span_days": round(span_days, 1),
        "last": prices[-1],
        "mean_move_bps": round(mean_move, 1),
        "median_move_bps": round(statistics.median(moves_bps), 1),
        "p90_move_bps": round(sorted(moves_bps)[int(0.9 * (len(moves_bps) - 1))], 1),
        "quiet_bars": round(100.0 * sum(1 for c in changes if c == 0) / len(changes), 1),
        "ar1": ar1(changes),
        "sticks": sticks(changes),
        "cover_hours": round(entry_bps / mean_move, 1) if mean_move else None,
    }


def bucket(price):
    edges = [(0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 0.25),
             (0.25, 0.50), (0.50, 0.90), (0.90, 1.0001)]
    for low, high in edges:
        if low <= price < high:
            return f"{low:.2f} to {high:.2f}"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=None,
                        help="snapshot to take the universe from")
    parser.add_argument("--markets", type=int, default=None,
                        help="use the top N markets by 24h volume instead")
    parser.add_argument("--fidelity", type=int, default=60,
                        help="minutes per bar")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    entries = []
    if args.snapshot:
        rows = read_snapshot(args.snapshot)
        if not rows:
            print("snapshot empty", file=sys.stderr)
            return 1
        sizes = sorted({r["shares"] for r in rows})
        size = sizes[len(sizes) // 2]
        for row in rows:
            if row["shares"] != size or row["round"] != 0:
                continue
            entries.append({
                "token_id": row["token_id"],
                "market_id": row["market_id"],
                "question": row["question"],
                "mid": row["mid"],
                "entry_bps": row["entry_bps"],
                "total_bps": row["total_bps"],
                "fee_rate": row["fee_rate"],
            })
    else:
        count = args.markets or 100
        for raw in pmbook.markets(limit=100, pages=max(1, count // 100 + 1))[:count]:
            view = pmbook.market_view(raw)
            for token, outcome in zip(view["tokens"], view["outcomes"], strict=False):
                entries.append({"token_id": str(token), "market_id": view["market_id"],
                                "question": view["question"], "outcome": outcome,
                                "mid": None, "entry_bps": 0.0, "total_bps": 0.0,
                                "fee_rate": view["fee_rate"]})
        entries = entries[:count]

    out = []
    for index, entry in enumerate(entries, 1):
        history = pmbook.history(entry["token_id"], interval="max", fidelity=args.fidelity)
        measured = stats(history, entry["entry_bps"] or 0.0)
        if not measured:
            continue
        measured.update(entry)
        measured["bucket"] = bucket(measured["last"])
        out.append(measured)
        if index % 25 == 0:
            print(f"{index}/{len(entries)} tokens", file=sys.stderr)

    if not out:
        print("no histories returned", file=sys.stderr)
        return 1

    stamp = "lag"
    target = Path(args.out) if args.out else ROOT / "data" / f"{stamp}.jsonl"
    with target.open("w", encoding="utf-8") as handle:
        for row in out:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(f"\n# Price movement against entry cost, {len(out)} tokens, "
          f"{args.fidelity} minute bars\n")
    print("| price bucket | tokens | median move bps/bar | median entry bps | hours to cover entry |")
    print("|---|---|---|---|---|")
    buckets = {}
    for row in out:
        buckets.setdefault(row["bucket"], []).append(row)
    for label in sorted(buckets):
        subset = buckets[label]
        move = statistics.median([r["mean_move_bps"] for r in subset])
        entry = statistics.median([r["entry_bps"] for r in subset])
        cover = statistics.median([r["cover_hours"] for r in subset if r["cover_hours"]])
        print(f"| {label} | {len(subset)} | {move:,.1f} | {entry:,.0f} | {cover:,.1f} |")

    all_cover = [r["cover_hours"] for r in out if r["cover_hours"]]
    medians = [r["median_move_bps"] for r in out]
    stick = [r["sticks"] for r in out if r["sticks"] is not None]
    ar = [r["ar1"] for r in out if r["ar1"] is not None]
    quiet = [r["quiet_bars"] for r in out]
    print(f"\n- median bars sampled: {statistics.median([r['bars'] for r in out]):,.0f}, "
          f"median span {statistics.median([r['span_days'] for r in out]):,.0f} days")
    print(f"- median quiet bars (price unchanged): {statistics.median(quiet):.1f}%")
    print(f"- median of per-token median moves: {statistics.median(medians):,.1f} bps per bar")
    if all_cover:
        print(f"- hours of average movement to pay one entry: median {statistics.median(all_cover):,.1f}, "
              f"90th percentile {sorted(all_cover)[int(0.9 * (len(all_cover) - 1))]:,.1f}")
    if stick:
        print(f"- consecutive changes with the same sign: median {statistics.median(stick):.1f}% "
              f"(50% is a coin)")
    if ar:
        print(f"- first-order autocorrelation of changes: median {statistics.median(ar):+.4f}")
    print(f"\nwrote {len(out)} rows to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
