# Model robustness experiments

These are synthetic sensitivities, not historical executable returns. Run `python -m hedgelab.robustness`.

The original 85%-strike / 75%-coverage selection is frozen from the original seed-142 path-based training. The independent seed-314 experiments vary realised volatility, drift, option IV and an uncompensated 30% crash affecting 10% of paths. All regimes use common random numbers. No re-selection occurs. Cash earns zero in this static experiment; no fees, dividends, margin or liquidity are modelled.

- [Model regimes](model_regimes.csv): terminal ES, expected return and loss probabilities, compared with unhedged, half-equity and a training-fitted terminal-volatility cash control.
- [All candidate diagnostics](all_candidates_diagnostic.csv): includes budget-infeasible candidates; these direct terminal draws are a diagnostic, not a replacement for the original daily-path training selection.
- [Rolling sensitivity](rolling_sensitivity.csv): all 288 combinations of four model paths, three IV multipliers, two coverages, three cost assumptions, two roll tenors and two overlay types. Both legs of the model collar share a tenor; this does not replicate Cboe CLL.
- [Configuration](config.json): seeds, frozen choice and control weight.

An expensive-IV regime can breach the 2% budget with the frozen quantity. Such rows are explicitly flagged and represent an infeasible stress, not an approved hedge. The terminal ES objective does not minimise path drawdown. Net premium cashflow is the sum of signed premiums paid on rolls; it is neither a standalone performance attribution nor gross insurance spending. The final session may include an opening roll whose premium remains as an option asset in NAV.

Parameter sweeps are disclosed diagnostics. They do not establish an optimal strategy or supply an untouched market holdout.
