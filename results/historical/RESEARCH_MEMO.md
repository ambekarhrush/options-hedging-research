# Historical portfolio protection study

Monthly benchmark research, January 2014–December 2025, with separate daily validation for 2021–2025. This is a completed comparison of published hypothetical indices, not a custom trade-level options backtest.

## Question and design

Does buying protection improve realised downside outcomes enough to justify its return drag, compared with reducing equity exposure? PPUT and CLL are compared with SPY adjusted returns, cash, a monthly 50/50 equity/cash control, and two monthly cash controls whose fixed equity weights match development-period index volatility approximately. Weights are fitted through 2020 and frozen for 2021–2025. Validation is retrospective and has already been inspected; it is not a pristine holdout.

PPUT and CLL embed different roll schedules. The custom monthly collar model in the parent folder is not a replication of CLL. SPY includes ETF expenses and differs from the S&P 500 total-return index. Cash uses daily French RF. Control trades cost 5 bps per dollar traded, including initial funding; Cboe series follow their published index methodology. No additional index execution assumptions are smuggled into these comparisons.

## Monthly validation results: 2021–2025

| Strategy | CAGR | Volatility | Month-end drawdown | Excess-cash Sharpe |
|---|---:|---:|---:|---:|
| PPUT | 9.27% | 13.14% | -20.81% | 0.49 |
| CLL | 9.08% | 11.64% | -16.55% | 0.53 |
| SPY | 14.34% | 15.14% | -23.93% | 0.75 |
| half_equity_cash | 9.00% | 7.60% | -12.15% | 0.74 |
| PPUT_risk_matched | 11.83% | 11.53% | -18.40% | 0.75 |
| CLL_risk_matched | 11.32% | 10.82% | -17.29% | 0.75 |
| cash | 3.32% | 0.67% | 0.00% | 0.00 |

## Daily validation and principal finding

The complete 2021–2025 daily calendar supplies 1,255 returns. Controls are freshly funded at the 2020 year-end close. Daily drawdowns can exceed month-end drawdowns.

| Strategy | CAGR | Daily maximum drawdown | Excess-cash Sharpe |
|---|---:|---:|---:|
| SPY | 14.38% | -24.50% | 0.68 |
| PPUT | 9.31% | -22.14% | 0.49 |
| CLL | 9.12% | -17.23% | 0.52 |
| half_equity_cash | 9.03% | -12.44% | 0.67 |
| PPUT_risk_matched | 11.87% | -18.85% | 0.68 |
| CLL_risk_matched | 11.36% | -17.71% | 0.68 |

Both protection indices reduced daily drawdown versus SPY but delivered lower CAGR and lower excess-cash Sharpe in validation. The 50/50 equity/cash control had a smaller drawdown than either index and a similar CAGR. The volatility-matched comparisons show that the value of protection depends on the chosen downside objective; these observations do not establish timing alpha or universal superiority.


## Interpretation and controls

Development volatility ratios imply fixed SPY weights of 76.1% for PPUT and 71.4% for CLL. These are approximate risk controls, not exact realised-volatility matches, beta matches, or investable replications. Their development results are in-sample. Volatility and correlations can change during validation.

Compare the return sacrifice with maximum drawdown, adverse-quarter outcomes and up/down-month averages. Protection can fail during a slow sell-off; repeated premiums can exceed realised put payoffs, while short calls surrender rebound participation. Historical index levels alone do not identify premium spend, bid/ask costs, or the option trade ledger.

## Uncertainty

Paired circular 3-month block bootstrap, 2,000 resamples, seed 2718. Intervals refer to annualised arithmetic mean monthly-return differences, not CAGR differences. They condition on this historical sample, assume approximate stationarity, and are not multiple-comparison adjusted.

| Index | Reference | Mean difference | 95% interval |
|---|---|---:|---:|
| PPUT | SPY | -4.85% | [-7.57%, -1.96%] |
| PPUT | half_equity_cash | 0.82% | [-3.82%, 5.50%] |
| PPUT | PPUT_risk_matched | -2.13% | [-4.80%, 0.37%] |
| CLL | SPY | -5.21% | [-8.99%, -0.14%] |
| CLL | half_equity_cash | 0.46% | [-4.43%, 5.48%] |
| CLL | CLL_risk_matched | -1.96% | [-5.53%, 2.17%] |

## Coverage and limitations

- A calendar audit found missing daily observations before 2021. This study uses complete exchange month-ends from December 2013; it does not fill gaps or annualise multi-session changes as daily returns. The original selected-quarter table remains separate evidence for 2008.
- Monthly drawdowns miss intramonth losses. See daily_validation.csv for daily 2021–2025 metrics, with all controls freshly funded at the 2020 year-end close. Crisis drawdowns here restart at the window boundary; COVID_Q1 covers the whole first quarter, not the precise peak-to-trough event.
- Index histories may include back-calculated periods and subsequent methodology changes. This is not a live record and no independent vendor audit was performed.
- Every required month-end and every required validation trading date must be present. No forward filling is allowed. The source calendar audit lists missing and extra dates explicitly in provenance.json.
- Cost sensitivity subtracts 0/25/50/100 bps of annual drag in validation. It is not a calibrated option execution model.
- Raw source files and daily derived series remain local. Published aggregate evidence, source hashes and charts support review; reruns may change after vendor revisions.
- Historical option chains are still required to substantiate a custom executable strike-selection strategy. This study does not make that claim.

## Reproduce and inspect

`python -m hedgelab.historical` downloads/caches the provider data, validates alignment and regenerates this report, figures and aggregate tables. See [provenance](provenance.json), [configuration](config.json), [full summary](summary.csv), [annual returns](annual_returns.csv), [crisis windows](crisis_windows.csv), [cost sensitivity](cost_sensitivity.csv) and [uncertainty](uncertainty.csv).

## Primary sources

- [Cboe PPUT daily history](https://cdn.cboe.com/api/global/us_indices/daily_prices/PPUT_History.csv)
- [Cboe CLL daily history](https://cdn.cboe.com/api/global/us_indices/daily_prices/CLL_History.csv)
- [Put protection methodology](https://cdn.cboe.com/api/global/us_indices/governance/PPUT_Methodology.pdf)
- [Collar methodology](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Collar_Indices_Methodology.pdf)
- [French daily factors and RF](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- SPY adjusted-close URL and hashes are recorded in provenance.json.
