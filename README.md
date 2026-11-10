# Polymarket: what a taker pays

A measurement of execution cost on Polymarket contracts, and of whether the
price moves enough to matter against that cost.

I built this to answer one question for myself: is there a trade here that
survives the spread. For a taker at retail size the measured cost is larger than
the measured movement, so the answer is no, and the repo is the working that
gets there: a cost model that walks real order books, a snapshot of 256 live
contracts, and a test of whether price movement at hourly frequency can clear
the cost of entry.

What survives is the numbers, which are reusable against any strategy on this
venue, and the correction below, which shows what happens when you trust a JSON
array's ordering.

## What it found

Taken from `data/snapshot-2026-11-10.jsonl`: 128 markets, 256 outcome tokens,
3 samples 90 seconds apart, $133M of 24h volume between them.

**Round trip at 1,000 shares: 666 bps of mid, median.** 6.7% to get in and out.
At 10,000 shares it is 1,020 bps, and the book fails to fill the order 14% of
the time. The split is roughly 274 bps of spread and 161 bps of fee, though the
two components do not add to the median total, because the markets with wide
spreads are also the ones charging fees.

**Cheap contracts are expensive to trade.** A 0.1c tick is 10 bps of the price
at 0.98 and 2,222 bps at 0.0045. The same contract, bought on the side priced
near zero, costs 223 times more to enter than the other side. Entry on the
sub-2c bucket is 2,499 bps, a quarter of the mid, before any fee.

**Only the tail is cheap, and it is all near resolution.** 15.3% of tokens can
be round-tripped under 100 bps at 1,000 shares. The lowest mid in that group is
0.9415.

**The book is mostly frozen.** 84% of tokens showed the same best bid and ask
at the first and last sample 90 seconds apart. In the price histories, 68.7% of
hourly bars show no change at all.

**There is no hourly momentum to sell.** First-order autocorrelation of price
changes is -0.076 and consecutive changes keep their sign 44.3% of the time.
Both point the wrong way for a momentum rule. One entry costs 3.8 hours of
average absolute movement, 17.3 hours in the 90th percentile.

**Fees are not uniform.** They come from each market's own `feeSchedule`, and
four rates appear in the snapshot: 0.03 on UCL football, 0.04 on politics, 0.05
on sports and the Fed, 0.07 on crypto. 594 of the 2,298 rows sit on a market
with fees disabled, and the Iran ceasefire rows are in that group. A fee is
charged on 1,704 rows in total.

## The mistake this started with

The first version of this reported spreads of 118% up to 33,000% and called
the venue dead. Those numbers were wrong by a median factor of 57, and by 3,688
at the 90th percentile.

The cause: `bids` and `asks` come back from the CLOB API sorted worst price
first. Reading the array in order and keeping the first level that matched
returned the minimum bid of 0.001 against the maximum ask of 0.999, so what got
measured was the full width of the book rather than the quoted spread. Sorting
both sides before selecting fixes it.

The old code is not in the tree. The effect is reproducible, though: `legacy_bps`
in every snapshot row is what the same book gives under the old ordering, next
to the corrected `spread_bps`. Across the snapshot the median row is off by
57x. It is the same book, read in the other direction.

## How the cost is measured

Spread cost is the VWAP you can sell into minus the VWAP you can buy out of,
walking real book levels for the size requested, divided by the mid. Fee is
`shares * feeRate * p * (1 - p)` on each crossing leg, with `feeRate` read from
the market's `feeSchedule` rather than a hardcoded table.

Both are quoted in basis points of the mid because a 1c spread is 200 bps at
0.50 and 50,000 bps at 0.002. A cost quoted in cents hides the entire problem.

`docs/method.md` has the definitions, the API behaviour that bit me, and the
unit traps. `docs/results.md` has the full tables and the numbers behind every
claim above.

## Running it

Python 3.10 or newer, tested on 3.12. Standard library only, no key, no account.

```
python src/measure.py --markets 150 --sizes 100,1000,10000 --rounds 3 --interval 45
python src/report.py data/snapshot-2026-11-10.jsonl
python src/lag.py --snapshot data/snapshot-2026-11-10.jsonl
```

`measure.py` writes a timestamped snapshot. `report.py` rebuilds every table
from the committed file, so nothing above has to be taken on trust. `lag.py`
pulls price histories for the same universe and compares movement against entry
cost.

A full snapshot took 98 seconds, most of it waiting between rounds. No request
was refused at one call per 0.15s across both runs.

## Files

```
src/pmbook.py    API access and book normalisation
src/cost.py      book walking, fee model, round-trip cost
src/measure.py   snapshot collection
src/report.py    tables from a snapshot
src/lag.py       price movement against entry cost
src/checks.py    re-derives every figure quoted in the docs
data/            two snapshots and the lag measurement
docs/method.md   definitions and API notes
docs/results.md  full result tables
```

## Checking the claims

Every number in this file and in `docs/` is re-derived by

```
python src/checks.py
```

which prints the documented value beside the measured one and exits non-zero if
they disagree. It is the answer to the obvious question about a repo like this:
whether the prose was written to fit the data or the other way round. The three
API claims in `docs/method.md` are re-measured against the live endpoints by
`python src/checks.py --live`.

External sources, both read 10 November 2026:

- fee formula and per-category rates: https://docs.polymarket.com/polymarket-learn/trading/fees
- order book and pricing endpoints: https://docs.polymarket.com/developers/CLOB/introduction

## What this does not do

It measures the cost side only. Whether a signal exists is a separate question,
and I have not shown one here. The obvious next step is the maker side: quoting
instead of crossing turns the 274 bps of spread into income, and the thing that
decides whether it survives is adverse selection, which needs fill data rather
than books.

Resolution data and the events feed are also untouched. That is where a fund
would look, and it is the part of this venue a retail participant cannot see.

## Licence

MIT. The snapshot is a point in time and will not reproduce; the code will.
