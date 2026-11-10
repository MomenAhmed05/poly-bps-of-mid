# Method

Every number in this file is either produced by the code in `src/` or taken from
Polymarket's published documentation, and the ones that matter are re-checked by
`src/checks.py`.

## The two costs

Two numbers matter and they answer different questions.

**Round trip** is what you pay to open and close at the same moment: buy at the
ask side, sell at the bid side. This is the cost of trading a signal that has
already paid you, and it is the number to compare against a per-trade edge.

**Entry only** is what you pay to take a position against the mid and keep it.
A contract held to resolution has no exit fill, so this is the cost that matters
for a directional bet. It is half the spread plus one fee leg, quoted against
the mid.

All costs are in basis points of the mid. The choice matters: 1c of spread is
200 bps at a price of 0.50 and 50,000 bps at 0.002. Cents hide the problem.

## Book walking, not depth filtering

A first pass filtered for a single level with enough size and took its price.
That is wrong in a way that flatters thin books, because it does not care how
far past the touch the qualifying level sits. The implementation here walks
levels in order of worsening price and accumulates a VWAP until the requested
size is filled. If the book runs out first, `complete` is false and the row
records how much was actually available.

Sizes are shares, not dollars. A contract settles at $1 or $0, so the dollar
notional of a level is `size * price`. 1,000 shares at 0.05 is a $50 position.
The snapshot records `notional_usd` per row so this cannot be misread: the
median 1,000 share row is $500, and the median 10,000 share row is $4,850.

## Fees

Polymarket publishes the fee as

```
fee = shares * feeRate * p * (1 - p)
```

The docs example reproduces exactly: 100 shares at $0.50 with a rate of 0.07
gives 100 * 0.07 * 0.25 = $1.75, which is the figure on their page.

`feeRate` is per market and comes from the market's own `feeSchedule.rate`
rather than a hardcoded table. In this snapshot that means 0.03 on UCL football,
0.04 on politics, 0.05 on sports and the Fed, and 0.07 on crypto. 594 of the
2,298 rows have no fee schedule at all, and every one of those markets also
reports `feesEnabled: false`, so reading the missing rate as zero is checked
rather than assumed.

Takers pay the fee and makers do not: `feeSchedule.takerOnly` is true and the
docs say the same. Round trip charges two legs, entry charges one. Set
`fee_legs=0` to price a maker.

## The tick floor

The quoted spread cannot be narrower than one tick, and across 2,298 rows not
one observation falls below it. 61.6% of rows sit exactly at one tick.

That single fact produces most of the asymmetry in the results. Tick size is
0.001 on 1,224 rows and 0.01 on 1,074, so the floor is computed per market rather
than assumed. At a mid of 0.0045 a 0.001 tick is 2,222 bps of the price. At a mid
of 0.9955 the same tick is 10 bps. The same contract, quoted from opposite ends,
has entry costs 223 times apart, which is arithmetic rather than liquidity.

## API behaviour worth knowing

Recorded because each of these cost me time, and each is checked.

**Array ordering.** `bids` and `asks` come back worst price first. `bids[0]` is
the minimum bid, `bids[-1]` is the best bid. Iterating in order and taking the
first level that matches a size filter returns the widest spread in the book.
This produced the original 118% to 33,000% figures. Every snapshot row carries
`legacy_bps`, the same book under the old ordering, next to the corrected
figure, so the size of the error is visible rather than asserted: median 57x,
90th percentile 3,688x.

**JSON inside JSON.** `clobTokenIds`, `outcomes` and `outcomePrices` are
JSON-encoded strings inside the JSON payload, so they need a second parse.

**Two identifiers.** `conditionId` and the token id are different things. On the
same market, `prices-history` returned 688 points when given the token id and 0
points when given the condition id, in both cases with a 200. A whole phase of
the original work measured nothing because of this.

**Liquidity fields.** `liquidityClob` is the per-market field. `liquidity` is not
a per-market value: in a sample of 35 events with more than one child, none had
a single `liquidity` value shared across its children. Neither field is a
substitute for reading the book, and that is measurable rather than a
preference. Rank correlation against round-trip cost is -0.198 for
`liquidityClob` and -0.042 for 24h volume. Against visible depth within 5c of
the touch it is 0.59 and 0.23 respectively.

**Tags.** Not on the markets endpoint. `include_tags=true` changes nothing and
the copy nested under `markets[].events[].tags` is empty. The tags exist only on
the events endpoint, so the cross-section costs one extra paged call.

**Stale touch.** Gamma's `bestBid` and `bestAsk` are a cache. Two live probes,
over 111 and 165 markets compared against the CLOB book, found 84.7% and 86.7%
of touches identical, 15.3% and 13.3% off by at least one tick, and a largest
gap of 0.10. Every price in the snapshot comes from the CLOB book rather than
from these fields. Re-measure with `python src/checks.py --live`.

**Tick sizes differ.** `orderPriceMinTickSize` is 0.001 on 1,224 rows and 0.01
on the rest in this snapshot, so the floor is computed per market.

## Sampling

The universe is the top markets by 24h volume, filtered to those with a live
book and non-zero volume. Both outcome tokens are taken, so a binary market
contributes two rows and a multi-outcome market contributes one per outcome.

Three rounds 45 seconds apart give the stability check. 214 of 254 tokens showed
an identical best bid and ask between the first and last round, which is what
makes a single snapshot worth quoting on cost.

Two full runs are committed, `snapshot-2026-11-10.jsonl` and
`snapshot-2026-11-10-repeat.jsonl`, taken about half an hour apart with 128 and
125 markets respectively. The aggregates agree closely enough to be quotable:

| statistic | first run | repeat |
|---|---|---|
| median round trip at 1,000 shares | 666 bps | 666 bps |
| median round trip at 10,000 shares | 1,020 bps | 945 bps |
| legacy overstatement, median | 57x | 58x |

The 10,000 share figure moves by 8% between runs and the 1,000 share figure by
nothing. Anything quoted to two significant figures is stable; anything quoted
to three is not.

A full run took 98 seconds end to end, most of it waiting between rounds. Across
both runs no request was refused at one call per 0.15 seconds.

## What is not modelled

**Maker fills.** The cost side is measured, the income side is not. Quoting turns
the spread into revenue and what decides whether that survives is adverse
selection, which needs fills rather than books.

**Resolution.** These contracts terminate at $1 or $0. Holding to resolution is
not a trade with a spread, it is a bet on the resolution, and the cost figures
here only say how good the bet has to be.

**Multi-outcome conversion.** On negRisk events the outcomes are linked and can
be converted. The conversion mechanics are not priced in.

**Queue position.** A taker does not have any, so it does not matter here. It
matters entirely for the maker side.

## Sources

Read 10 November 2026.
- Fee formula, per-category rates, taker-only: https://docs.polymarket.com/polymarket-learn/trading/fees
- CLOB order book, prices-history, batch books: https://docs.polymarket.com/developers/CLOB/introduction
- Market metadata, events, tags: https://gamma-api.polymarket.com
