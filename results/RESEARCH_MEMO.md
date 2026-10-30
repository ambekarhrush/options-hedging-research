# Options-based portfolio protection: research memo

## Question

How do protective puts and collars compare with unhedged equity and reduced equity exposure, and how should a hedge be sized under a premium budget?

## Historical evidence: published Cboe benchmark quarters

Cboe reports total returns for fixed-rule benchmark indices over selected adverse quarters. This is the published comparison, in percent, not a custom options backtest:

| Quarter | S&P 500 total return | PPUT | CLL | PPUT minus S&P, pp | CLL minus S&P, pp |
|---|---:|---:|---:|---:|---:|
| 2008 Q4 | -21.9% | 0.2% | -5.9% | 22.1 | 16.0 |
| 2020 Q1 | -19.6% | 0.0% | -5.0% | 19.6 | 14.6 |
| 2022 Q2 | -16.1% | -13.1% | -6.7% | 3.0 | 9.4 |

PPUT holds S&P 500 exposure and buys monthly 5%-out-of-the-money SPX puts. CLL buys quarterly 5%-out-of-the-money puts and sells monthly 10%-out-of-the-money calls. Their index rules, roll dates and option execution assumptions differ. These are hypothetical indices; they embed option economics under index methodology but do not establish a particular investor's realised fills, commissions, spreads or taxes. These quarters were selected because they were stressed: they cannot establish long-run hedge cost, maximum drawdown or investment performance. 2022 Q2 is not the whole 2022 sell-off.

Source: https://www.cboe.com/us/index_protection/ — table "Index Performance in Challenging Quarters". Methodologies: https://cdn.cboe.com/api/global/us_indices/governance/PPUT_Methodology.pdf and https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Collar_Indices_Methodology.pdf.

## Custom option simulation: synthetic paths only

The four hypothetical paths are abrupt crash, prolonged sell-off, inflation-style grind and rising market. They are deliberately generated paths, not historical reconstructions of 2008, 2020 or 2022. Comparison includes full unhedged exposure, 50% equity/50% zero-yield cash, 100% 5%-OTM rolling puts, and 95/110 rolling collars. Options are European and cash-settled; roll every 21 sessions; Black–Scholes uses the scenario's assumed daily IV. Equity turnover and option premium trades cost 10 bps. Initial equity and option premiums are funded from the same NAV, and premium cost reduces the equity position. The half-equity control is an initially funded buy-and-hold combination, not daily rebalanced. See model_scenarios.png and simulated_scenarios.csv.

Caveats: model-implied volatility paths are stipulated, not observed option quotes. No skew surface, dividends, assignment, margin, bid/ask liquidity, jumps or realistic execution delay. Results are model sensitivities, not historical executable returns.

## Premium-budget sizing

One-year European static puts are selected from strikes 85/90/95/100% and coverages 0/25/50/75/100%, subject to the upfront premium being at most 2% of initial NAV. Training uses 10,000 simulated GBM paths, seed 142, spot volatility/IV 22%, expected drift 4%, zero rates/dividends and terminal 95% expected shortfall as objective. This is terminal-loss optimisation, not drawdown optimisation or an annual rolling-premium estimate. The same data path set is used for each candidate. The selected configuration is evaluated on a separate set of 10,000 GBM paths, seed 314; both sets share the same model assumptions. No costs are applied in the static sizing experiment.

Selected strike: 85%; coverage: 75%; premium: 1.99% of NAV. Independent model sample terminal ES95: hedge 21.73%, unhedged 35.57%; mean terminal return hedge 3.33%, unhedged 3.90%. These are model results, not market estimates.

## What remains for a full empirical project

Obtain licensed point-in-time option chains covering 2008, 2020 and 2022, with actual contract expiries, bid/ask quotes, dividends, rates, settlement, roll calendar and stale-quote rules. Build a trade-level historical simulator, compare with matched-risk allocation and record realised premium drag, drawdown saved, tail losses and upside sacrificed. Reserve an untouched later period for selection and validation. Cboe published quarterly points cannot be used to infer continuous performance or tune strikes and coverage.
