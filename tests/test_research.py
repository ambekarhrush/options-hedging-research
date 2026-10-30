import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from hedgelab.options import black_scholes, overlay
from hedgelab.engine import metrics
from hedgelab.historical import validate_levels, fit_weights, monthly_control, paired_interval, daily_validation
from hedgelab.robustness import payoff, terminal_sample


class PricingAndFundingTests(unittest.TestCase):
    def test_independent_binomial_price(self):
        # Risk-neutral European put tree independently checks the closed form.
        steps = 2000
        dt = 1 / steps
        up = np.exp(.2 * np.sqrt(dt))
        down = 1 / up
        probability = (np.exp(.03 * dt) - down) / (up - down)
        terminal = 100 * up ** np.arange(steps + 1) * down ** np.arange(steps, -1, -1)
        values = np.maximum(105 - terminal, 0)
        for _ in range(steps):
            values = np.exp(-.03 * dt) * ((1 - probability) * values[:-1] + probability * values[1:])
        self.assertAlmostEqual(float(values[0]), float(black_scholes(100, 105, 1, .2, .03)), delta=.003)

    def test_ledger_identity_and_expiry_accounting(self):
        spot = np.linspace(100, 70, 64)
        led = overlay(spot, np.full(64, .25), call_moneyness=1.1, rate=.03)
        identity = led.cash + led.shares * led.spot + led.contracts * (led.put_mark - led.call_mark)
        np.testing.assert_allclose(led.nav, identity, atol=1e-12)
        self.assertTrue((led.cash >= -1e-12).all())
        for t in [21, 42, 63]:
            old = led.iloc[t - 1]
            settled = old.cash * np.exp(.03 / 252) + old.shares * spot[t]
            settled += old.contracts * (max(old.put_strike - spot[t], 0) - max(spot[t] - old.call_strike, 0))
            self.assertAlmostEqual(led.nav.iloc[t], settled - led.fees.iloc[t], places=12)

    def test_future_paths_do_not_change_prefix(self):
        spot = np.linspace(100, 120, 80)
        vol = np.full(80, .2)
        original = overlay(spot, vol)
        spot[40:] *= .4
        vol[40:] = .8
        pd.testing.assert_frame_equal(original.iloc[:40], overlay(spot, vol).iloc[:40])

    def test_invalid_inputs_fail_closed(self):
        for value in [np.nan, np.inf, -1]:
            with self.assertRaises(ValueError):
                black_scholes(value, 100, 1, .2)
            with self.assertRaises(ValueError):
                overlay([100, value], [.2, .2])
        with self.assertRaises(ValueError):
            overlay([100, 101], [.2, .2], roll_days=1.5)

    def test_static_payoff_floor_and_funding(self):
        pnl, premium = payoff(np.array([0., 50., 100., 200.]), .95, 1.)
        self.assertAlmostEqual(pnl[0], pnl[1])
        price = float(black_scholes(100, 95, 1, .22))
        self.assertAlmostEqual(premium, price / (100 + price))
        self.assertAlmostEqual(pnl[-1], 200 / (100 + price) - 1)

    def test_stress_reproducibility(self):
        np.testing.assert_array_equal(terminal_sample(42), terminal_sample(42))
        self.assertFalse(np.array_equal(terminal_sample(42), terminal_sample(43)))


class HistoricalTests(unittest.TestCase):
    def test_missing_duplicate_unsorted_levels_rejected(self):
        f = pd.DataFrame({'PPUT': [100., 101.]}, index=pd.date_range('2020-01-01', periods=2))
        validate_levels(f)
        for bad in [f.iloc[::-1], pd.concat([f, f]), f.assign(PPUT=[100, np.nan])]:
            with self.assertRaises(ValueError):
                validate_levels(bad)

    def test_risk_control_training_independence(self):
        index = pd.date_range('2014-01-31', '2025-12-31', freq='ME')
        equity = np.random.default_rng(2).normal(0, .04, len(index))
        r = pd.DataFrame({'SPY': equity, 'PPUT': .7 * equity, 'CLL': .6 * equity}, index=index)
        before = fit_weights(r)
        r.loc['2021':, ['PPUT', 'CLL']] *= 10
        self.assertEqual(before, fit_weights(r))
        self.assertAlmostEqual(before['PPUT'], .7)

    def test_monthly_control_initial_fee_and_cash(self):
        index = pd.to_datetime(['2020-12-31', '2021-01-29', '2021-02-26'])
        r = pd.Series([0., .10, -.10], index=index)
        cash = pd.Series([0., .01, .01], index=index)
        ledger = monthly_control(r, cash, .5, cost_bps=0)
        np.testing.assert_allclose(ledger.nav, [1., 1.055, 1.055 * .955])
        charged = monthly_control(r, cash, .5, cost_bps=5)
        self.assertAlmostEqual(charged.nav.iloc[0], 1 / (1 + .5 * .0005))

    def test_frequency_and_first_loss(self):
        result = metrics([.01] * 12, periods_per_year=12)
        self.assertAlmostEqual(result['CAGR'], 1.01**12 - 1)
        self.assertAlmostEqual(metrics([-.1, 0], periods_per_year=12)['max_drawdown'], -.1)

    def test_paired_bootstrap_constant_difference(self):
        base = np.linspace(-.1, .1, 60)
        result = paired_interval(base + .01, base, draws=50)
        for value in result.values():
            self.assertAlmostEqual(value, .12)

    def test_daily_report_uses_daily_frequency(self):
        index = pd.bdate_range('2020-12-31', periods=253)
        levels = pd.DataFrame({k: 100 * 1.001 ** np.arange(253) for k in ['SPY', 'PPUT', 'CLL']}, index=index)
        with tempfile.TemporaryDirectory() as directory:
            daily_validation(levels, pd.Series(0., index=index), {'PPUT': .7, 'CLL': .6}, Path(directory))
            row = pd.read_csv(Path(directory) / 'daily_validation.csv').set_index('strategy').loc['PPUT']
            self.assertAlmostEqual(row.CAGR, 1.001**252 - 1)
            self.assertEqual(row.sessions, 252)


if __name__ == '__main__':
    unittest.main()
