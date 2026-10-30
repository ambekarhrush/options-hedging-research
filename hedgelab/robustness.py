"""Frozen hedge selection, model misspecification and rolling-overlay sensitivities."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .options import black_scholes, optimise_hedge, overlay, scenario_paths
from .engine import metrics


def terminal_sample(seed, paths=10000, vol=.22, drift=.04, jump_probability=0.):
    """One-year GBM terminal draws, optionally multiplied by a 30% downward jump.

    Jump stress is uncompensated: its expected return is lower by construction.
    This is a distributional stress, not a fitted jump-diffusion model.
    """
    rng = np.random.default_rng(seed)
    spot = 100 * np.exp(drift - .5 * vol**2 + vol * rng.normal(size=paths))
    return spot * np.where(rng.random(paths) < jump_probability, .7, 1.)


def payoff(terminal, strike, coverage, implied_vol=.22):
    premium = float(black_scholes(100, 100 * strike, 1, implied_vol))
    shares = 1 / (100 + coverage * premium)
    return shares * (terminal + coverage * np.maximum(100 * strike - terminal, 0)) - 1, shares * coverage * premium


def tail_metrics(pnl):
    q = np.quantile(pnl, .05)
    return {'mean_return': float(pnl.mean()), 'terminal_ES95': float(-pnl[pnl <= q].mean()),
            'probability_loss': float((pnl < 0).mean()), 'probability_loss_20pct': float((pnl < -.2).mean())}


def run(out='results/robustness'):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # Retain the original training experiment, so added diagnostics cannot retune it.
    selected = optimise_hedge(seed=142, annual_budget=.02, paths=10000).iloc[0]
    strike, coverage = float(selected.strike_ratio), float(selected.coverage)
    train = terminal_sample(142)
    grid = []
    for k in [.85, .90, .95, 1.]:
        for c in [0., .25, .50, .75, 1.]:
            pnl, premium = payoff(train, k, c)
            grid.append({'strike': k, 'coverage': c, 'premium_fraction': premium,
                         'within_2pct_budget': bool(premium <= .02 + 1e-12), **tail_metrics(pnl)})
    # This diagnostic grid uses terminal draws; it does not replace the original selection grid.
    pd.DataFrame(grid).to_csv(out / 'all_candidates_diagnostic.csv', index=False)
    train_hedged, _ = payoff(train, strike, coverage)
    matched = float(np.clip(train_hedged.std(ddof=1) / (train / 100 - 1).std(ddof=1), 0, 1))
    regimes = [('base', .22, .04, .22, 0.), ('quiet', .12, .04, .22, 0.),
               ('high_realised_vol', .35, .04, .22, 0.), ('expensive_puts', .22, .04, .35, 0.),
               ('negative_drift', .22, -.10, .22, 0.), ('jump_stress', .22, .04, .22, .10)]
    rows = []
    for name, vol, drift, iv, jump in regimes:
        terminal = terminal_sample(314, vol=vol, drift=drift, jump_probability=jump)
        hedged, premium = payoff(terminal, strike, coverage, iv)
        unhedged = terminal / 100 - 1
        for strategy, pnl in [('selected_put', hedged), ('unhedged', unhedged),
                              ('half_equity_cash', .5 * unhedged), ('risk_matched_cash', matched * unhedged)]:
            rows.append({'regime': name, 'strategy': strategy, 'realised_vol_assumption': vol,
                         'drift_assumption': drift, 'implied_vol_assumption': iv,
                         'jump_probability': jump, 'premium_fraction': premium if strategy == 'selected_put' else 0.,
                         'within_2pct_budget': bool(premium <= .02 + 1e-12) if strategy == 'selected_put' else True,
                         **tail_metrics(pnl)})
    pd.DataFrame(rows).to_csv(out / 'model_regimes.csv', index=False)
    sensitivities = []
    for name, (spot, iv) in scenario_paths(42).items():
        for iv_scale in [.75, 1., 1.5]:
            for cover in [.5, 1.]:
                for fee in [0, 10, 25]:
                    for roll in [21, 63]:
                        for strategy, call in [('put', None), ('collar', 1.1)]:
                            ledger = overlay(spot, iv * iv_scale, coverage=cover, call_moneyness=call,
                                             cost_bps=fee, roll_days=roll)
                            ret = ledger.nav.pct_change().fillna(ledger.nav.iloc[0] - 1)
                            sensitivities.append({'scenario': name, 'strategy': strategy, 'iv_scale': iv_scale,
                                                  'coverage': cover, 'cost_bps': fee, 'roll_days': roll,
                                                  'net_premium_cashflow': float(ledger.net_premium.sum()),
                                                  'fees': float(ledger.fees.sum()), **metrics(ret)})
    pd.DataFrame(sensitivities).to_csv(out / 'rolling_sensitivity.csv', index=False)
    config = {'training_seed': 142, 'validation_seed': 314, 'paths_per_regime': 10000,
              'frozen_strike': strike, 'frozen_coverage': coverage, 'risk_matched_equity_weight': matched,
              'budget': .02, 'scenario_seed': 42, 'scenario_experiments': len(sensitivities),
              'note': 'Frozen original selection; no re-optimisation across stress regimes. Diagnostic terminal grid is separate from original path-based training.'}
    (out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    (out / 'README.md').write_text('''# Model robustness experiments

These are synthetic sensitivities, not historical executable returns. Run `python -m hedgelab.robustness`.

The original 85%-strike / 75%-coverage selection is frozen from the original seed-142 path-based training. The independent seed-314 experiments vary realised volatility, drift, option IV and an uncompensated 30% crash affecting 10% of paths. All regimes use common random numbers. No re-selection occurs. Cash earns zero in this static experiment; no fees, dividends, margin or liquidity are modelled.

- [Model regimes](model_regimes.csv): terminal ES, expected return and loss probabilities, compared with unhedged, half-equity and a training-fitted terminal-volatility cash control.
- [All candidate diagnostics](all_candidates_diagnostic.csv): includes budget-infeasible candidates; these direct terminal draws are a diagnostic, not a replacement for the original daily-path training selection.
- [Rolling sensitivity](rolling_sensitivity.csv): all 288 combinations of four model paths, three IV multipliers, two coverages, three cost assumptions, two roll tenors and two overlay types. Both legs of the model collar share a tenor; this does not replicate Cboe CLL.
- [Configuration](config.json): seeds, frozen choice and control weight.

An expensive-IV regime can breach the 2% budget with the frozen quantity. Such rows are explicitly flagged and represent an infeasible stress, not an approved hedge. The terminal ES objective does not minimise path drawdown. Net premium cashflow is the sum of signed premiums paid on rolls; it is neither a standalone performance attribution nor gross insurance spending. The final session may include an opening roll whose premium remains as an option asset in NAV.

Parameter sweeps are disclosed diagnostics. They do not establish an optimal strategy or supply an untouched market holdout.
''')
    print(f'Wrote {len(rows)} regime comparisons and {len(sensitivities)} rolling sensitivities to {out}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='results/robustness')
    run(parser.parse_args().out)
