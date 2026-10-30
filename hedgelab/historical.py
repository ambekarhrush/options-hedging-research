"""Reproducible benchmark-index research; never a custom option-chain backtest."""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from .engine import backtest, metrics

START = '2013-12-31'
END = '2025-12-31'
SPLIT = '2021-01-01'
HEADERS = {'User-Agent': 'Mozilla/5.0 (research; reproducible benchmark study)'}


def fetch(url, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = response.read()
        path.write_bytes(payload)
    raw = path.read_bytes()
    return raw, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(),
                 'cache_file': path.name}


def validate_levels(frame):
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.empty:
        raise ValueError('Nonempty dated levels required')
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError('Dates must be unique and increasing')
    if not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
        raise ValueError('Finite positive levels required; no filling allowed')


def download(cache='data/private'):
    cache = Path(cache)
    levels = []
    sources = []
    for symbol in ['PPUT', 'CLL']:
        url = f'https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv'
        raw, record = fetch(url, cache / f'{symbol}.csv')
        frame = pd.read_csv(io.BytesIO(raw))
        series = pd.Series(frame[symbol].to_numpy(),
                           index=pd.to_datetime(frame.DATE, format='%m/%d/%Y'), name=symbol)
        levels.append(series)
        sources.append({**record, 'series': symbol, 'source_first_date': str(series.index.min().date()),
                        'source_last_date': str(series.index.max().date())})
    start = int(pd.Timestamp('2008-08-01', tz='UTC').timestamp())
    end = int(pd.Timestamp('2026-01-01', tz='UTC').timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/SPY?period1={start}&period2={end}&interval=1d'
    raw, record = fetch(url, cache / 'SPY_2008_2025.json')
    source = json.loads(raw)['chart']['result'][0]
    if source['meta']['currency'] != 'USD':
        raise ValueError('USD prices required')
    dates = pd.to_datetime(source['timestamp'], unit='s', utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
    levels.append(pd.Series(source['indicators']['adjclose'][0]['adjclose'], index=dates, name='SPY'))
    sources.append({**record, 'series': 'SPY', 'field': 'adjusted close; includes distributions and fund expenses'})
    # Cut to a frozen common period before computing returns. Missing sessions fail closed.
    raw_panel = pd.concat([s.loc['2008-08-26':END] for s in levels], axis=1).sort_index()
    # SPY identifies actual exchange sessions. Audit every missing/extra source date.
    issues = raw_panel.loc[raw_panel.isna().any(axis=1)].isna()
    issues.to_csv(cache / 'calendar_audit.csv', index_label='date')
    spy_dates = levels[-1].loc[START:END].index
    ends = pd.Series(spy_dates, index=spy_dates).groupby(spy_dates.to_period('M')).last()
    panel = raw_panel.reindex(pd.DatetimeIndex(ends.to_numpy()))
    validate_levels(panel)
    daily = raw_panel.reindex(spy_dates[spy_dates >= pd.Timestamp('2020-12-31')])
    validate_levels(daily)
    if panel.index[0] != pd.Timestamp(START) or panel.index[-1] != pd.Timestamp(END):
        raise ValueError('Sources do not cover the configured interval')
    url = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip'
    raw, record = fetch(url, cache / 'ff_daily.zip')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        lines = archive.read(archive.namelist()[0]).decode('utf-8-sig').splitlines()
    rows = [line.split(',') for line in lines if len(line.split(',')[0].strip()) == 8 and line.split(',')[0].strip().isdigit()]
    cash_all = pd.Series({pd.Timestamp(row[0].strip()): float(row[-1]) / 100 for row in rows}, name='cash').reindex(spy_dates)
    if not np.isfinite(cash_all).all() or (cash_all <= -1).any():
        raise ValueError('Missing or invalid cash proxy')
    cash = (1 + cash_all).groupby(cash_all.index.to_period('M')).prod() - 1
    cash.index = panel.index
    cash.iloc[0] = 0
    sources.append({**record, 'series': 'RF', 'field': 'daily RF percent / 100'})
    provenance = {'checked_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'sources': sources,
                  'start': START, 'end': END, 'level_rows': len(panel), 'missing_values': panel.isna().sum().to_dict(),
                  'validation_start': SPLIT, 'frequency': 'month-end',
                  'source_calendar_issues': {str(date.date()): [col for col in issues if row[col]] for date, row in issues.iterrows()},
                  'notes': ['Raw provider files stay in ignored data/private.',
                            'Cached bytes are reused; checked_utc is not necessarily the original retrieval time.',
                            'CLL downloaded history starts August 2008; no claim to cover the full 2007–2009 crisis.',
                            'PPUT/CLL are hypothetical total-return indices; SPY is an adjusted ETF proxy, not SPX total return.',
                            'Historical and validation periods are retrospective, not an untouched holdout.']}
    return panel, cash, provenance, daily, cash_all.reindex(daily.index)


def monthly_control(equity, cash, weight, cost_bps=5):
    """Invest at the base close; monthly close rebalance, then earn next return."""
    dates = equity.index
    first = dates[0]
    # Final available session of each month; initial allocation at the base close.
    ends = pd.Series(dates, index=dates).groupby(dates.to_period('M')).last()
    targets = pd.DataFrame({'SPY': weight}, index=pd.DatetimeIndex(sorted(set([first, *ends.tolist()]))))
    ledger, _ = backtest(equity.to_frame('SPY'), targets, cost_bps=cost_bps, cash_daily=cash)
    return ledger


def fit_weights(returns, split=SPLIT):
    """Match training volatility by static cash dilution, without future data."""
    train = returns.loc[returns.index < pd.Timestamp(split)]
    if len(train) < 36:
        raise ValueError('At least 36 monthly training observations required')
    vol = train.SPY.std(ddof=1)
    if vol <= 0:
        raise ValueError('Nonzero equity volatility required')
    return {name: float(np.clip(train[name].std(ddof=1) / vol, 0, 1)) for name in ['PPUT', 'CLL']}


def paired_interval(a, b, seed=2718, draws=2000, block=3, annualisation=12):
    """Circular paired block bootstrap of annualised arithmetic return difference."""
    x = np.asarray(a, float) - np.asarray(b, float)
    if len(x) < block or not np.isfinite(x).all():
        raise ValueError('Insufficient finite paired observations')
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(x), size=(draws, int(np.ceil(len(x) / block))))
    indices = (starts[..., None] + np.arange(block)) % len(x)
    means = x[indices.reshape(draws, -1)[:, :len(x)]].mean(axis=1) * annualisation
    low, high = np.quantile(means, [.025, .975])
    return {'annual_mean_difference': float(x.mean() * annualisation), 'lower_95': float(low), 'upper_95': float(high)}


def monthly_metrics(r):
    result = metrics(r, periods_per_year=12)
    result['monthly_ES_95'] = result.pop('daily_ES_95')
    return result


def summarise(returns, cash):
    rows = []
    for period, subset in [('full', returns), ('development', returns.loc[:'2020-12-31']),
                           ('validation', returns.loc[SPLIT:])]:
        for name in subset:
            r = subset[name]
            excess = r - cash.reindex(r.index)
            vol = r.std(ddof=1) * np.sqrt(12)
            rows.append({'period': period, 'strategy': name, 'start': str(r.index[0].date()),
                         'end': str(r.index[-1].date()), 'months': len(r), **monthly_metrics(r),
                         'Sharpe_excess_cash': float(excess.mean() * 12 / vol) if vol > 1e-12 else 0})
    return pd.DataFrame(rows)


def run(out='results/historical', cache='data/private'):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    levels, cash, provenance, daily, daily_cash = download(cache)
    source_returns = levels.pct_change(fill_method=None).iloc[1:]
    weights = fit_weights(source_returns)
    # Include a base date with zero market return to charge initial investment fees.
    equity = levels.SPY.pct_change(fill_method=None).fillna(0)
    cash_base = cash.copy()
    cash_base.iloc[0] = 0
    nav = pd.DataFrame(index=levels.index)
    for name in ['PPUT', 'CLL']:
        nav[name] = levels[name] / levels[name].iloc[0]
    controls = {'SPY': 1., 'half_equity_cash': .5,
                **{f'{name}_risk_matched': weight for name, weight in weights.items()}}
    for name, weight in controls.items():
        ledger = monthly_control(equity, cash_base, weight)
        nav[name] = ledger.nav
        # Summary evidence only is published; raw daily provider histories stay private.
    nav['cash'] = (1 + cash_base).cumprod()
    returns = nav.pct_change(fill_method=None).iloc[1:]
    # Fold initial funding fees into the first return, preserving NAV reconciliation.
    returns.iloc[0] = nav.iloc[1] - 1
    summary = summarise(returns, cash.iloc[1:])
    summary.to_csv(out / 'summary.csv', index=False)
    annual = (1 + returns).groupby(returns.index.year).prod() - 1
    annual.index.name = 'year'
    annual.to_csv(out / 'annual_returns.csv')
    validation = returns.loc[SPLIT:]
    intervals = []
    for strategy in ['PPUT', 'CLL']:
        for reference in ['SPY', 'half_equity_cash', f'{strategy}_risk_matched']:
            intervals.append({'strategy': strategy, 'reference': reference,
                              **paired_interval(validation[strategy], validation[reference])})
    pd.DataFrame(intervals).to_csv(out / 'uncertainty.csv', index=False)
    windows = {'COVID_Q1': ('2020-01-01', '2020-03-31'), 'inflation_2022': ('2022-01-01', '2022-12-31')}
    crisis = []
    for label, (start, end) in windows.items():
        for name in returns:
            r = returns.loc[start:end, name]
            crisis.append({'window': label, 'strategy': name, 'first_return': str(r.index[0].date()),
                           'last_return': str(r.index[-1].date()), **monthly_metrics(r)})
    pd.DataFrame(crisis).to_csv(out / 'crisis_windows.csv', index=False)
    # Annual extra drag, not a fictitious reconstruction of option trading fees.
    drag = []
    for bps in [0, 25, 50, 100]:
        for name in ['PPUT', 'CLL']:
            net = (1 + validation[name]) * np.exp(-bps / 10000 / 12) - 1
            drag.append({'strategy': name, 'extra_annual_drag_bps': bps, **monthly_metrics(net)})
    pd.DataFrame(drag).to_csv(out / 'cost_sensitivity.csv', index=False)
    monthly = (1 + returns).groupby(returns.index.to_period('M')).prod() - 1
    capture = []
    for name in ['PPUT', 'CLL', 'half_equity_cash']:
        for regime, mask in [('up', monthly.SPY > 0), ('down', monthly.SPY < 0)]:
            capture.append({'strategy': name, 'SPY_month': regime, 'months': int(mask.sum()),
                            'mean_return': float(monthly.loc[mask, name].mean()),
                            'SPY_mean_return': float(monthly.loc[mask, 'SPY'].mean())})
    pd.DataFrame(capture).to_csv(out / 'monthly_capture.csv', index=False)
    config = {'base_date': START, 'end': END, 'validation_start': SPLIT, 'control_cost_bps': 5,
              'risk_matched_weights': weights, 'bootstrap_seed': 2718, 'bootstrap_draws': 2000,
              'bootstrap_block_months': 3, 'frequency': 'month-end', 'selection': 'No strike/coverage selection from historical index results'}
    (out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    provenance['code_hashes'] = {'hedgelab/' + p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
    import platform
    import importlib.metadata
    provenance['environment'] = {'python': platform.python_version(), **{name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'matplotlib']}}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    # Local daily calculations support notebooks without publishing vendor archives.
    private = Path(cache)
    nav.to_csv(private / 'benchmark_nav.csv', index_label='date')
    returns.to_csv(private / 'benchmark_returns.csv', index_label='date')
    daily_validation(daily, daily_cash, weights, out)
    plot(nav, out / 'overview.png')
    write_report(summary, weights, intervals, out)
    print(summary.loc[summary.period == 'validation', ['strategy', 'CAGR', 'max_drawdown', 'Sharpe_excess_cash']].to_string(index=False))
    return summary


def daily_validation(levels, cash, weights, out):
    """Daily metrics on the verified complete validation calendar; reset at base close."""
    nav = levels[['PPUT', 'CLL']].div(levels[['PPUT', 'CLL']].iloc[0])
    equity = levels.SPY.pct_change(fill_method=None).fillna(0)
    cash = cash.copy()
    cash.iloc[0] = 0
    for name, weight in {'SPY': 1., 'half_equity_cash': .5,
                         **{f'{key}_risk_matched': value for key, value in weights.items()}}.items():
        nav[name] = monthly_control(equity, cash, weight).nav
    nav['cash'] = (1 + cash).cumprod()
    ret = nav.pct_change(fill_method=None).iloc[1:]
    ret.iloc[0] = nav.iloc[1] - 1
    rows = []
    for name in ret:
        r = ret[name]
        vol = r.std(ddof=1) * np.sqrt(252)
        rows.append({'strategy': name, 'start': str(r.index[0].date()), 'end': str(r.index[-1].date()),
                     'sessions': len(r), **metrics(r),
                     'Sharpe_excess_cash': float((r - cash.reindex(r.index)).mean() * 252 / vol) if vol > 1e-12 else 0})
    pd.DataFrame(rows).to_csv(out / 'daily_validation.csv', index=False)


def plot(nav, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'SPY': '#223e5a', 'PPUT': '#007f82', 'CLL': '#bd6634', 'half_equity_cash': '#7e739e'}
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    for name, color in colors.items():
        axes[0].plot(nav.index, nav[name], label=name, color=color, lw=1.6)
        axes[1].plot(nav.index, nav[name] / nav[name].cummax().clip(lower=1) - 1, color=color, lw=1.1)
    axes[0].set_yscale('log')
    axes[0].set_ylabel('Wealth from $1 · log scale')
    axes[1].set_ylabel('Drawdown')
    axes[0].legend(frameon=False, ncol=2)
    for ax in axes:
        ax.axvline(pd.Timestamp(SPLIT), color='#777777', ls='--', lw=1)
        ax.grid(alpha=.15)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('Portfolio protection · historical benchmark study', fontsize=18, x=.08, ha='left')
    fig.text(.08, .91, 'Jan 2014–Dec 2025 · month-end observations | Cboe hypothetical indices vs SPY ETF proxy | dashed line: retrospective validation', fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, .90))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_report(summary, weights, intervals, out):
    lines = ['# Historical portfolio protection study', '',
             'Monthly benchmark research, January 2014–December 2025, with separate daily validation for 2021–2025. This is a completed comparison of published hypothetical indices, not a custom trade-level options backtest.', '',
             '## Question and design', '',
             'Does buying protection improve realised downside outcomes enough to justify its return drag, compared with reducing equity exposure? PPUT and CLL are compared with SPY adjusted returns, cash, a monthly 50/50 equity/cash control, and two monthly cash controls whose fixed equity weights match development-period index volatility approximately. Weights are fitted through 2020 and frozen for 2021–2025. Validation is retrospective and has already been inspected; it is not a pristine holdout.', '',
             'PPUT and CLL embed different roll schedules. The custom monthly collar model in the parent folder is not a replication of CLL. SPY includes ETF expenses and differs from the S&P 500 total-return index. Cash uses daily French RF. Control trades cost 5 bps per dollar traded, including initial funding; Cboe series follow their published index methodology. No additional index execution assumptions are smuggled into these comparisons.', '',
             '## Monthly validation results: 2021–2025', '',
             '| Strategy | CAGR | Volatility | Month-end drawdown | Excess-cash Sharpe |',
             '|---|---:|---:|---:|---:|']
    for row in summary.loc[summary.period == 'validation'].itertuples():
        lines.append(f'| {row.strategy} | {row.CAGR:.2%} | {row.volatility:.2%} | {row.max_drawdown:.2%} | {row.Sharpe_excess_cash:.2f} |')
    daily = pd.read_csv(out / 'daily_validation.csv').set_index('strategy')
    lines += ['', '## Daily validation and principal finding', '',
              'The complete 2021–2025 daily calendar supplies 1,255 returns. Controls are freshly funded at the 2020 year-end close. Daily drawdowns can exceed month-end drawdowns.', '',
              '| Strategy | CAGR | Daily maximum drawdown | Excess-cash Sharpe |', '|---|---:|---:|---:|']
    for name in ['SPY', 'PPUT', 'CLL', 'half_equity_cash', 'PPUT_risk_matched', 'CLL_risk_matched']:
        row = daily.loc[name]
        lines.append(f'| {name} | {row.CAGR:.2%} | {row.max_drawdown:.2%} | {row.Sharpe_excess_cash:.2f} |')
    lines += ['', 'Both protection indices reduced daily drawdown versus SPY but delivered lower CAGR and lower excess-cash Sharpe in validation. The 50/50 equity/cash control had a smaller drawdown than either index and a similar CAGR. The volatility-matched comparisons show that the value of protection depends on the chosen downside objective; these observations do not establish timing alpha or universal superiority.', '']
    lines += ['', '## Interpretation and controls', '',
              f'Development volatility ratios imply fixed SPY weights of {weights["PPUT"]:.1%} for PPUT and {weights["CLL"]:.1%} for CLL. These are approximate risk controls, not exact realised-volatility matches, beta matches, or investable replications. Their development results are in-sample. Volatility and correlations can change during validation.', '',
              'Compare the return sacrifice with maximum drawdown, adverse-quarter outcomes and up/down-month averages. Protection can fail during a slow sell-off; repeated premiums can exceed realised put payoffs, while short calls surrender rebound participation. Historical index levels alone do not identify premium spend, bid/ask costs, or the option trade ledger.', '',
              '## Uncertainty', '',
              'Paired circular 3-month block bootstrap, 2,000 resamples, seed 2718. Intervals refer to annualised arithmetic mean monthly-return differences, not CAGR differences. They condition on this historical sample, assume approximate stationarity, and are not multiple-comparison adjusted.', '',
              '| Index | Reference | Mean difference | 95% interval |', '|---|---|---:|---:|']
    for row in intervals:
        lines.append(f'| {row["strategy"]} | {row["reference"]} | {row["annual_mean_difference"]:.2%} | [{row["lower_95"]:.2%}, {row["upper_95"]:.2%}] |')
    lines += ['', '## Coverage and limitations', '',
              '- A calendar audit found missing daily observations before 2021. This study uses complete exchange month-ends from December 2013; it does not fill gaps or annualise multi-session changes as daily returns. The original selected-quarter table remains separate evidence for 2008.',
              '- Monthly drawdowns miss intramonth losses. See daily_validation.csv for daily 2021–2025 metrics, with all controls freshly funded at the 2020 year-end close. Crisis drawdowns here restart at the window boundary; COVID_Q1 covers the whole first quarter, not the precise peak-to-trough event.',
              '- Index histories may include back-calculated periods and subsequent methodology changes. This is not a live record and no independent vendor audit was performed.',
              '- Every required month-end and every required validation trading date must be present. No forward filling is allowed. The source calendar audit lists missing and extra dates explicitly in provenance.json.',
              '- Cost sensitivity subtracts 0/25/50/100 bps of annual drag in validation. It is not a calibrated option execution model.',
              '- Raw source files and daily derived series remain local. Published aggregate evidence, source hashes and charts support review; reruns may change after vendor revisions.',
              '- Historical option chains are still required to substantiate a custom executable strike-selection strategy. This study does not make that claim.', '',
              '## Reproduce and inspect', '',
              '`python -m hedgelab.historical` downloads/caches the provider data, validates alignment and regenerates this report, figures and aggregate tables. See [provenance](provenance.json), [configuration](config.json), [full summary](summary.csv), [annual returns](annual_returns.csv), [crisis windows](crisis_windows.csv), [cost sensitivity](cost_sensitivity.csv) and [uncertainty](uncertainty.csv).', '',
              '## Primary sources', '',
              '- [Cboe PPUT daily history](https://cdn.cboe.com/api/global/us_indices/daily_prices/PPUT_History.csv)',
              '- [Cboe CLL daily history](https://cdn.cboe.com/api/global/us_indices/daily_prices/CLL_History.csv)',
              '- [Put protection methodology](https://cdn.cboe.com/api/global/us_indices/governance/PPUT_Methodology.pdf)',
              '- [Collar methodology](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Collar_Indices_Methodology.pdf)',
              '- [French daily factors and RF](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)',
              '- SPY adjusted-close URL and hashes are recorded in provenance.json.', '']
    (out / 'RESEARCH_MEMO.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='results/historical')
    parser.add_argument('--cache', default='data/private')
    args = parser.parse_args()
    run(args.out, args.cache)
