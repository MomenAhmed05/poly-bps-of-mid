"""Summarise a snapshot taken by measure.py.

    python src/report.py data/snapshot-2026-11-10.jsonl

Prints markdown. Nothing here reaches the network, so every number in
docs/results.md can be rebuilt from the committed snapshot by anyone.
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


PRICE_BUCKETS = [
    ("under 2c", 0.0, 0.02),
    ("2c to 5c", 0.02, 0.05),
    ("5c to 10c", 0.05, 0.10),
    ("10c to 25c", 0.10, 0.25),
    ("25c to 50c", 0.25, 0.50),
    ("50c to 90c", 0.50, 0.90),
    ("90c and up", 0.90, 1.0001),
]

# Tags that describe the feed that produced the market rather than the subject.
GENERIC_TAGS = {"All", "Recurring", "Feed", "Featured", "Weekly", "Monthly", "Daily"}


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def median_price(values):
    """A median that survives prices near zero. median() rounds to one place,
    which turns every mid under 0.05 into zero."""
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 4) if values else None


def median_rate(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def percentile(values, share):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    index = min(len(values) - 1, int(round(share * (len(values) - 1))))
    return round(values[index], 1)


def load(path):
    rows = []
    source = Path(path)
    if not source.is_file():
        print(f"no such snapshot: {source}", file=sys.stderr)
        return rows
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def dedupe(rows):
    """One row per (market, token, size, round). Guards against a market being
    returned twice by the paged listing."""
    seen = {}
    for row in rows:
        seen[(row["market_id"], row["token_id"], row["shares"], row["round"])] = row
    return list(seen.values())


def bucket(price):
    for label, low, high in PRICE_BUCKETS:
        if low <= price < high:
            return label
    return "unknown"


def table(title, header, body):
    print(f"\n### {title}\n")
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join("---" for _ in header) + "|")
    for row in body:
        print("| " + " | ".join(str(cell) for cell in row) + " |")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot")
    args = parser.parse_args()

    rows = dedupe(load(args.snapshot))
    if not rows:
        print("empty snapshot", file=sys.stderr)
        return 1

    markets = {r["market_id"] for r in rows}
    tokens = {r["token_id"] for r in rows}
    sizes = sorted({r["shares"] for r in rows})
    rounds = sorted({r["round"] for r in rows})
    volume = sum(r["volume_24h"] or 0 for r in rows) / max(1, len(sizes))
    fee_paying = sum(1 for r in rows if (r["fee_rate"] or 0) > 0)

    print(f"# Snapshot report: {Path(args.snapshot).name}\n")
    print(f"- markets: {len(markets)}, outcome tokens: {len(tokens)}")
    print(f"- rounds: {len(rounds)}, trade sizes: {', '.join(str(s) for s in sizes)} shares")
    print(f"- rows on a fee-paying market: {fee_paying:,} of {len(rows):,}")
    print(f"- 24h volume across the universe: ${volume:,.0f}")

    ratios = [r["legacy_bps"] / r["total_bps"] for r in rows
              if r["legacy_bps"] and r["total_bps"] and r["total_bps"] > 0]
    if ratios:
        print(f"- the old measurement overstates the round trip by a median "
              f"{median(ratios):,.0f}x, 90th percentile {percentile(ratios, 0.9):,.0f}x")

    # cost by trade size
    body = []
    for shares in sizes:
        subset = [r for r in rows if r["shares"] == shares]
        body.append([
            f"{shares:,}",
            len(subset),
            f"{median([r['spread_bps'] for r in subset]):,.0f}",
            f"{median([r['fee_bps'] for r in subset]):,.0f}",
            f"{median([r['total_bps'] for r in subset]):,.0f}",
            f"{median([r['entry_bps'] for r in subset]):,.0f}",
            f"{100 * sum(1 for r in subset if r['complete']) / len(subset):.0f}%",
            f"${median([r['notional_usd'] for r in subset]):,.0f}",
        ])
    table("Round-trip cost by trade size, medians in bps of mid",
          ["shares", "rows", "spread", "fee", "total", "entry only", "book filled", "median notional"],
          body)

    # cost by price
    grouped = defaultdict(list)
    for row in rows:
        grouped[bucket(row["mid"])].append(row)
    body = []
    for label, _low, _high in PRICE_BUCKETS:
        subset = grouped.get(label)
        if not subset:
            continue
        body.append([
            label,
            len(subset),
            f"{median([r['tick_floor_bps'] for r in subset]):,.0f}",
            f"{median([r['quoted_spread_bps'] for r in subset]):,.0f}",
            f"{median([r['spread_bps'] for r in subset]):,.0f}",
            f"{median([r['fee_bps'] for r in subset]):,.0f}",
            f"{median([r['total_bps'] for r in subset]):,.0f}",
            f"{median([r['entry_bps'] for r in subset]):,.0f}",
        ])
    table("Cost against price level, medians in bps of mid, all sizes pooled",
          ["price bucket", "rows", "1 tick floor", "quoted spread", "spread at size",
           "fee", "total round trip", "entry only"],
          body)

    # how much probability edge the entry costs you
    body = []
    for label, _low, _high in PRICE_BUCKETS:
        subset = grouped.get(label)
        if not subset:
            continue
        entry = median([r["entry_bps"] for r in subset])
        mid = median_price([r["mid"] for r in subset])
        if entry is None or mid is None:
            continue
        body.append([label, f"{mid:.4f}", f"{entry:,.0f}", f"{entry / 1e4 * mid * 100:.4f}"])
    table("Probability edge needed to buy at the ask and hold to resolution",
          ["price bucket", "median mid", "entry cost (bps)", "edge needed (points)"], body)

    # the two ends of the same contract: one tick is a fraction of one and most
    # of the other, so the cheap side is the expensive one to trade
    cheap = [r for r in rows if r["mid"] <= 0.02]
    dear = [r for r in rows if r["mid"] >= 0.98]
    if cheap and dear:
        print("\n### The two ends of the same contract\n")
        print("| side | rows | median mid | 1 tick floor bps | median entry bps | entry in cents |")
        print("|---|---|---|---|---|---|")
        for label, subset in (("at or under 2c", cheap), ("at or over 98c", dear)):
            entry = median([r["entry_bps"] for r in subset]) or 0.0
            mid = median_price([r["mid"] for r in subset]) or 0.0
            floor = median([r["tick_floor_bps"] for r in subset]) or 0.0
            print(f"| {label} | {len(subset):,} | {mid:.4f} | {floor:,.0f} | {entry:,.0f} | "
                  f"{entry / 1e4 * mid * 100:+.3f} |")
        cheap_floor = median([r["tick_floor_bps"] for r in cheap]) or 0.0
        dear_floor = median([r["tick_floor_bps"] for r in dear]) or 1.0
        print(f"\nThe tick floor on the cheap side is {cheap_floor / dear_floor:,.0f}x the dear side.")

    # categories
    by_tag = defaultdict(list)
    for row in rows:
        for tag in row["tags"] or []:
            if tag not in GENERIC_TAGS:
                by_tag[tag].append(row)
    body = []
    for tag, subset in sorted(by_tag.items(), key=lambda pair: -len(pair[1]))[:14]:
        charged = [r["fee_rate"] for r in subset if (r["fee_rate"] or 0) > 0]
        body.append([
            tag[:24],
            len(subset),
            f"{100 * len(charged) / len(subset):.0f}%",
            f"{median_rate(charged):.3f}" if charged else "-",
            f"{median([r['quoted_spread_bps'] for r in subset]):,.0f}",
            f"{median([r['total_bps'] for r in subset]):,.0f}",
            f"${median([r['volume_24h'] or 0 for r in subset]):,.0f}",
        ])
    if body:
        table("Cost by event tag, tags seen on at least one market",
              ["tag", "rows", "fee charged", "rate when charged", "quoted spread",
               "total round trip", "median 24h volume"],
              body)

    # is the book even stable between samples
    if len(rounds) > 1:
        first = {r["token_id"]: r for r in rows if r["round"] == rounds[0] and r["shares"] == sizes[0]}
        last = {r["token_id"]: r for r in rows if r["round"] == rounds[-1] and r["shares"] == sizes[0]}
        both = set(first) & set(last)
        if both:
            same_book = sum(1 for t in both if first[t]["best_bid"] == last[t]["best_bid"]
                            and first[t]["best_ask"] == last[t]["best_ask"])
            print(f"\n### Stability between round {rounds[0] + 1} and round {rounds[-1] + 1}\n")
            print(f"- identical best bid and ask at both samples: {same_book} of {len(both)} "
                  f"({100 * same_book / len(both):.0f}%)")

    # how much of the universe is cheap enough to consider at all
    print("\n### Share of tokens under a cost ceiling\n")
    print("| ceiling | " + " | ".join(f"{s:,} shares" for s in sizes) + " |")
    print("|---|" + "|".join("---" for _ in sizes) + "|")
    for ceiling in (100, 200, 500, 1000, 2000):
        cells = []
        for shares in sizes:
            subset = [r for r in rows if r["shares"] == shares]
            cells.append(f"{100 * sum(1 for r in subset if r['total_bps'] <= ceiling) / len(subset):.1f}%")
        print(f"| under {ceiling:,} bps | " + " | ".join(cells) + " |")

    # cheapest and dearest, at the middle size
    mid_size = sizes[len(sizes) // 2]
    print(f"\n### Cheapest and dearest round trips at {mid_size:,} shares\n")
    subset = sorted([r for r in rows if r["shares"] == mid_size], key=lambda r: r["total_bps"])
    seen_questions = set()
    picked = []
    for row in subset[:5] + subset[-5:]:
        if row["question"] in seen_questions:
            continue
        seen_questions.add(row["question"])
        picked.append(row)
    print("| question | mid | round trip bps | entry bps | fee rate | volume 24h |")
    print("|---|---|---|---|---|---|")
    for row in picked:
        print(f"| {row['question'][:62]} | {row['mid']:.4f} | {row['total_bps']:,.0f} | "
              f"{row['entry_bps']:,.0f} | {row['fee_rate'] or 0:.2f} | "
              f"${row['volume_24h'] or 0:,.0f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
