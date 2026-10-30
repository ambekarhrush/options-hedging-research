import unittest
import numpy as np
from hedgelab.options import black_scholes,overlay,optimise_hedge,scenario_paths
from hedgelab.study import CBOE

class HedgeTests(unittest.TestCase):
 def test_put_call_parity(self):
  c=black_scholes(100,105,1,.2,.03,put=False);p=black_scholes(100,105,1,.2,.03)
  self.assertAlmostEqual(c-p,100-105*np.exp(-.03))
 def test_expiry(self):self.assertEqual(black_scholes(80,100,0,.2),20)
 def test_coverage_zero(self):
  s=np.array([100.,90.,110.]); out=overlay(s,np.full(3,.2),coverage=0,cost_bps=0)
  np.testing.assert_allclose(out.nav,s/100)
 def test_premium_paid(self):
  out=overlay(np.full(23,100.),np.full(23,.2),cost_bps=0)
  self.assertAlmostEqual(out.nav.iloc[0],1);self.assertLess(out.nav.iloc[20],1)
 def test_collar_covered(self):
  out=overlay([100,95,80],[.2,.3,.5],call_moneyness=1.1)
  self.assertTrue((out.contracts<=out.shares+1e-10).all())
 def test_budget(self):
  g=optimise_hedge(annual_budget=.02,paths=1000)
  self.assertTrue((g.premium_fraction<=.020000001).all())
 def test_scenarios_reproducible(self):
  a=scenario_paths(42);b=scenario_paths(42)
  for key in a:np.testing.assert_array_equal(a[key][0],b[key][0])
 def test_published_quarter(self):self.assertAlmostEqual(CBOE['2008 Q4']['PPUT']-CBOE['2008 Q4']['SPX'],22.1)

if __name__=='__main__':unittest.main()
