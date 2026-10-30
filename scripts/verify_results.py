"""Offline reconciliation of the published evidence; no market-data download."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    provenance = json.loads((ROOT / 'results/historical/provenance.json').read_text())
    for name, expected in provenance['code_hashes'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    annual = pd.read_csv(ROOT / 'results/historical/annual_returns.csv', index_col='year')
    summary = pd.read_csv(ROOT / 'results/historical/summary.csv')
    for row in summary.itertuples():
        years = annual if row.period == 'full' else annual.loc[:2020] if row.period == 'development' else annual.loc[2021:]
        np.testing.assert_allclose((1 + years[row.strategy]).prod() - 1, row.total_return, atol=1e-10)
        np.testing.assert_allclose((1 + row.total_return) ** (12 / row.months) - 1, row.CAGR, atol=1e-10)
    for path in (ROOT / 'results').glob('*_ledger.csv'):
        led = pd.read_csv(path)
        reconstructed = led.cash + led.shares * led.spot + led.contracts * (led.put_mark - led.call_mark)
        np.testing.assert_allclose(led.nav, reconstructed, atol=1e-10)
        assert (led.cash >= -1e-10).all(), path.name
    stress = pd.read_csv(ROOT / 'results/robustness/rolling_sensitivity.csv')
    assert len(stress) == 288
    assert not stress.duplicated(['scenario', 'strategy', 'iv_scale', 'coverage', 'cost_bps', 'roll_days']).any()
    validation = json.loads((ROOT / 'results/independent_model_validation.json').read_text())
    assert validation['premium_fraction'] <= .02 + 1e-12
    print('PASS archived source hashes, annual/period compounding, funded ledgers, budget and sensitivity coverage')


if __name__ == '__main__':
    main()
