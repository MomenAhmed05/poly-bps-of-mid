# Results

Every figure below is produced by `src/report.py` from
`data/snapshot-2026-11-10.jsonl`, or by `src/checks.py`, which re-derives each
one and compares it against the value written here. If a number in this file
disagrees with a fresh run, the file is stale and the run is right.

Two notes on reading the tables.

The median of a component and the median of the sum are different numbers,
because markets with wide spreads are also the markets that charge fees. The
components are shown for diagnosis. Quote the total when quoting a cost.

Tags are not partitions. A single market carries several at once, which is why
the tag rows sum to 18,246 assignments over 2,298 rows.

## Universe

| | |
|---|---|
| markets | 128 |
| outcome tokens | 256 |
| rows | 2,298 |
| samples | 3, 45 seconds apart |
| sizes | 100, 1,000, 10,000 shares |
| 24h volume across the universe | $133,044,291 |
| rows on a fee-paying market | 1,704 of 2,298 |

Markets are the top by 24h volume with a live book. Both outcome tokens of a
binary market are included, so a 0.30 contract and its 0.70 complement each
appear once.

## Cost by size

| shares | rows | spread | fee | total | entry only | book filled | median notional |
|---|---|---|---|---|---|---|---|
| 100 | 766 | 214 | 161 | 618 | 314 | 99% | $50 |
| 1,000 | 766 | 274 | 161 | 666 | 323 | 96% | $500 |
| 10,000 | 766 | 730 | 161 | 1,020 | 456 | 86% | $4,850 |

Slippage between 1,000 and 10,000 shares adds 354 bps to the median. That is the
cost of walking deeper, not of paying the touch.

The fill column is the number worth keeping: at 10,000 shares, 14% of orders
could not be filled at any price in the book. At 1,000 shares it is 4%.

## Cost by price level

| price bucket | rows | 1 tick floor | quoted spread | spread at size | fee | total round trip | entry only |
|---|---|---|---|---|---|---|---|
| under 2c | 279 | 2,222 | 4,000 | 5,302 | 796 | 6,135 | 2,499 |
| 2c to 5c | 153 | 274 | 1,695 | 3,186 | 775 | 3,453 | 1,914 |
| 5c to 10c | 111 | 1,053 | 1,176 | 1,445 | 724 | 1,908 | 954 |
| 10c to 25c | 303 | 488 | 645 | 870 | 644 | 1,433 | 716 |
| 25c to 50c | 303 | 235 | 260 | 298 | 524 | 810 | 405 |
| 50c to 90c | 606 | 126 | 148 | 178 | 158 | 380 | 189 |
| 90c and up | 543 | 10 | 21 | 52 | 8 | 61 | 30 |

Cost falls as the price rises, and the fall is driven by the tick. At 0.0045 a
0.001 tick is 2,222 bps of the price. At 0.9955 the same tick is 10 bps. Nothing
about liquidity explains a 222x difference in a constant.

The fee column exceeds the spread at size in exactly one band, 25c to 50c, where
the median fee is 524 bps against 298 bps of spread. Everywhere else the spread
is larger.

### The two ends of the same contract

| side | rows | median mid | 1 tick floor | median entry | entry in cents |
|---|---|---|---|---|---|
| at or under 2c | 279 | 0.0045 | 2,222 bps | 2,499 bps | +0.112 |
| at or over 98c | 279 | 0.9955 | 10 bps | 11 bps | +0.111 |

Both sides cost about a tenth of a cent per contract to enter, $0.0011 either
way. In bps the cheap side is 223 times the dear side. Same trade, same cost per
contract, different denominator.

## What the entry cost demands of a view

Buying at the ask and holding to resolution requires the true probability to be
above the ask by at least the entry cost:

| price bucket | median mid | entry cost | edge needed (points) | as a share of the mid |
|---|---|---|---|---|
| under 2c | 0.0045 | 2,499 bps | 0.1124 | 25.0% |
| 2c to 5c | 0.0365 | 1,914 bps | 0.6985 | 19.1% |
| 5c to 10c | 0.0800 | 954 bps | 0.7634 | 9.5% |
| 10c to 25c | 0.1550 | 716 bps | 1.1104 | 7.2% |
| 25c to 50c | 0.3850 | 405 bps | 1.5596 | 4.1% |
| 50c to 90c | 0.7502 | 189 bps | 1.4156 | 1.9% |
| 90c and up | 0.9815 | 30 bps | 0.2895 | 0.3% |

The largest requirement in probability points is the 25c to 50c band at 1.56
points, which is 4.1% of the mid. That is the price of admission and nothing
more: it says how much better than the quote a view has to be before the trade
is worth making at all.

## Cost by tag

Rate column shows the fee rate when a fee is charged. Fee-charged is the share
of that tag's rows sitting on a market that charges.

| tag | rows | fee charged | rate when charged | quoted spread | total round trip | median 24h volume |
|---|---|---|---|---|---|---|
| Politics | 1,116 | 63% | 0.040 | 200 | 565 | $83,211 |
| Elections | 630 | 89% | 0.040 | 134 | 561 | $84,743 |
| Geopolitics | 630 | 6% | 0.040 | 250 | 444 | $91,488 |
| World Elections | 558 | 87% | 0.040 | 143 | 563 | $82,322 |
| Global Elections | 558 | 87% | 0.040 | 162 | 561 | $83,195 |
| Main Election | 450 | 84% | 0.040 | 134 | 546 | $83,195 |
| Trump | 432 | 54% | 0.050 | 224 | 560 | $113,675 |
| World | 432 | 71% | 0.040 | 200 | 638 | $83,653 |
| Iran | 432 | 4% | 0.040 | 176 | 342 | $111,229 |
| Sports | 336 | 100% | 0.050 | 204 | 724 | $112,662 |
| Iran Ceasefire | 324 | 0% | - | 167 | 290 | $111,229 |
| Games | 318 | 100% | 0.050 | 204 | 724 | $107,910 |
| French Election | 270 | 100% | 0.040 | 94 | 420 | $83,195 |
| France | 270 | 100% | 0.040 | 94 | 420 | $83,195 |

In this snapshot the fee rate takes four values across the universe, 0.03, 0.04,
0.05 and 0.07, and geopolitics markets are charged nothing. Sports and games sat
on a fee in every row. Iran ceasefire in none.

Those are the observed rates, not the published ones. Polymarket's fee page
lists a rate per category and the metadata matches it where I checked, but the
authority for any single market is its own `feeSchedule`, which is what the code
reads.

## Stability

Between the first and last sample, 90 seconds apart, 214 of 254 tokens had an
identical best bid and ask.

## How much of the universe is cheap

Share of tokens whose round trip falls under a ceiling.

| ceiling | 100 shares | 1,000 shares | 10,000 shares |
|---|---|---|---|
| under 100 bps | 15.8% | 15.3% | 10.1% |
| under 200 bps | 30.3% | 26.5% | 17.1% |
| under 500 bps | 46.7% | 44.5% | 33.8% |
| under 1,000 bps | 66.1% | 62.8% | 49.9% |
| under 2,000 bps | 81.9% | 77.2% | 62.4% |

The 15.3% under 100 bps is the group a screen would return, so it is worth being
precise about it: the lowest mid in that group is 0.9415. Every token cheap
enough to trade is one the market has already decided.

## The extremes at 1,000 shares

| question | mid | round trip | entry | fee rate | volume 24h |
|---|---|---|---|---|---|
| Will Shakhtar Donetsk win the 2026-27 Champions League | 0.9985 | 11 bps | 6 | 0.03 | $423,804 |
| Will Anthropic IPO by November 15, 2026? | 0.9985 | 11 bps | 6 | 0.04 | $69,444 |
| Will François Baroin win the 2027 French election | 0.9985 | 11 bps | 6 | 0.04 | $59,503 |
| Will Elon Musk post 260-279 tweets from November 3 | 0.2990 | 16,332 bps | 15,018 | 0.05 | $146,405 |
| Will Eli Cohen be the next Prime Minister of Israel? | 0.0015 | 16,963 bps | 13,630 | 0.00 | $120,710 |
| Bitcoin Up or Down on November 10? | 0.0055 | 19,623 bps | 10,882 | 0.07 | $55,648 |

The Musk row is the awkward one. It sits at 0.299, a genuine two-sided price, and
carries $146,405 of 24h volume, yet 1,000 shares sweeps through a gap and costs
163% of the mid to get in and out. Volume is not depth here.

That is measurable rather than anecdotal. Across the 256 tokens, rank
correlation against the round-trip cost is -0.042 for 24h volume and -0.198 for
`liquidityClob`. Volume against visible depth within 5c of the touch is 0.233,
and `liquidityClob` against the same depth is 0.59. Neither field is a
substitute for reading the book.

## Does the price move enough to matter

`lag.jsonl` covers the same 256 tokens, median 668 hourly bars over 31 days.

| price bucket | tokens | median move bps/bar | median entry bps | hours to cover entry |
|---|---|---|---|---|
| 0.00 to 0.02 | 31 | 258.1 | 2,399 | 5.7 |
| 0.02 to 0.05 | 18 | 249.8 | 1,950 | 6.8 |
| 0.05 to 0.10 | 12 | 235.2 | 969 | 4.7 |
| 0.10 to 0.25 | 34 | 191.6 | 655 | 3.2 |
| 0.25 to 0.50 | 33 | 109.1 | 396 | 4.6 |
| 0.50 to 0.90 | 68 | 71.1 | 175 | 2.8 |
| 0.90 to 1.00 | 60 | 18.5 | 29 | 2.4 |

Four diagnostics across all 256 tokens:

| statistic | value | what it is |
|---|---|---|
| bars with no price change | 68.7% | unchanged hourly |
| hours of movement to pay one entry | 3.8 | 17.3 at the 90th percentile |
| consecutive changes with the same sign | 44.3% | below 50% |
| first-order autocorrelation of changes | -0.076 | changes tend to reverse |

The last two are the reason a momentum rule is not on the table at this
frequency. Changes keep their sign less often than a coin and correlate
negatively with themselves.

Move per bar is large in the cheap buckets, and that is not encouraging once it
is put next to the cost. A contract in the sub-2c bucket moves 258 bps in an
average hour and costs 2,399 bps to enter, which is 5.7 hours of that movement.

## What the numbers say together

For a taker at retail size on this venue, the measured floor is about 11 bps of
round trip on a near-resolved contract and 666 bps at the median 1,000 share
order. Under 2c the median total is 6,135 bps, nine times that median. Movement
at hourly frequency is 3.8 hours of average absolute change per entry, and the
series does not trend.

That bounds the price-following case. It says nothing against a participant with
a better estimate of the resolution, or with news before it is priced, because
they are not competing on the spread. What the tables give them is the number
they have to beat.
