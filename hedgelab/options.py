"""European option pricing, fully funded model overlays and ex-ante sizing.

All paths in this module are MODEL scenarios, never observed option executions.
Index options assumed European, cash-settled; no assignment/margin model.
"""
import numpy as np
import pandas as pd
from scipy.special import ndtr

def black_scholes(spot,strike,tau,vol,rate=0.,dividend=0.,put=True):
    s=np.asarray(spot,float); k=np.asarray(strike,float)
    if np.any(s<=0) or np.any(k<=0) or tau<0 or np.any(np.asarray(vol)<=0):
        raise ValueError('Invalid pricing inputs')
    if tau==0: return np.maximum(k-s,0) if put else np.maximum(s-k,0)
    root=np.asarray(vol)*np.sqrt(tau)
    d1=(np.log(s/k)+(rate-dividend+.5*np.asarray(vol)**2)*tau)/root
    d2=d1-root
    call=s*np.exp(-dividend*tau)*ndtr(d1)-k*np.exp(-rate*tau)*ndtr(d2)
    return call-s*np.exp(-dividend*tau)+k*np.exp(-rate*tau) if put else call

def overlay(spot, implied_vol, coverage=1., put_moneyness=.95, call_moneyness=None,
            roll_days=21, cost_bps=10, rate=0.):
    """NAV ledger; share count scales to fund option premium and all execution costs.

    No dividends in scenario paths. Premium and cash earn risk-free rate. Fees
    apply to stock turnover and absolute option premium traded at roll. Daily
    marks use supplied scenario IV; rolls use closing spot and IV. Expiry option
    settles before next purchase. Collar short calls cannot exceed held shares.
    """
    s=np.asarray(spot,float); iv=np.asarray(implied_vol,float)
    if len(s)!=len(iv) or len(s)<2 or np.any(s<=0) or np.any(iv<=0): raise ValueError('Invalid paths')
    if not 0<=coverage<=1 or roll_days<1 or cost_bps<0 or put_moneyness<=0:
        raise ValueError('Invalid overlay parameters')
    if call_moneyness is not None and call_moneyness<=1: raise ValueError('Call must be OTM')
    cash=1.; shares=0.; contracts=0.; kp=kc=0.; expiry=0; rows=[]
    fee_rate=cost_bps/10000
    for t,st in enumerate(s):
        if t: cash*=np.exp(rate/252)
        tau=max(expiry-t,0)/252
        p=float(black_scholes(st,kp,tau,iv[t],rate)) if contracts else 0.
        c=float(black_scholes(st,kc,tau,iv[t],rate,put=False)) if contracts and call_moneyness else 0.
        nav=cash+shares*st+contracts*(p-c)
        premium=fee=0.
        if t==0 or t==expiry:
            cash += contracts*(p-c); contracts=0.
            kp=st*put_moneyness; kc=st*(call_moneyness or 1.1); expiry=t+roll_days
            p=float(black_scholes(st,kp,roll_days/252,iv[t],rate))
            c=float(black_scholes(st,kc,roll_days/252,iv[t],rate,put=False)) if call_moneyness else 0.
            unit=st+coverage*(p-c)
            # Bisection solves post-cost fully invested share quantity.
            lo,hi=0.,nav/max(unit,1e-9)
            for _ in range(60):
                q=(lo+hi)/2
                fees=fee_rate*(abs(q-shares)*st+q*coverage*(p+c))
                if q*unit+fees>nav: hi=q
                else: lo=q
            q=(lo+hi)/2
            fee=fee_rate*(abs(q-shares)*st+q*coverage*(p+c))
            premium=q*coverage*(p-c)
            cash=nav-q*unit-fee; shares=q; contracts=q*coverage
            nav=cash+shares*st+contracts*(p-c)
        rows.append([nav,premium,fee,shares,contracts])
    return pd.DataFrame(rows,columns=['nav','net_premium','fees','shares','contracts'])

def scenario_paths(seed=42):
    rng=np.random.default_rng(seed); paths={}
    # Stylised shock shapes, not calibrated historical event replications.
    for name,drop,days,rebound,iv_peak in [('abrupt_crash',.35,20,.22,.8),('prolonged_selloff',.45,100,.1,.55),('inflation_grind',.25,200,.02,.35),('bull_market',-.2,200,.05,.2)]:
        n=253; log=np.full(n,.0001)+rng.normal(0,.005,n)
        log[1:days+1]+=np.log(1-drop)/days
        log[days+1:]+=np.log(1+rebound)/max(n-days-1,1)
        log[0]=0; s=100*np.exp(np.cumsum(log))
        iv=np.interp(np.arange(n),[0,days//2,days,252],[.2,iv_peak,iv_peak*.8,.2])
        paths[name]=(s,iv)
    return paths

def optimise_hedge(seed=42, annual_budget=.02, paths=1000):
    """One-year terminal ES sizing on seeded GBM simulations.

    Static put protection; budget is actual initial premium / NAV. Independent
    Monte Carlo from the displayed scenario paths. No drawdown optimisation or
    assurance that GBM describes actual tail risk.
    """
    if not 0<=annual_budget<=.2: raise ValueError('Budget outside [0,20%]')
    rng=np.random.default_rng(seed); z=rng.normal(size=(paths,252))
    log=(.04-.5*.22**2)/252+.22/np.sqrt(252)*z
    spot=100*np.exp(np.cumsum(log,axis=1)); spot=np.column_stack([np.full(paths,100.),spot])
    terminal=spot[:,-1]/100-1; rows=[]
    # Static one-year protection: budget interpreted as actual initial premium/NAV.
    for strike in [.85,.9,.95,1.]:
        premium=float(black_scholes(100,100*strike,1,.22))
        for coverage in [0.,.25,.5,.75,1.]:
            shares=1/(100+coverage*premium)
            spend=shares*coverage*premium
            if spend>annual_budget+1e-12: continue
            ret=shares*(spot[:,-1]+coverage*np.maximum(100*strike-spot[:,-1],0))-1
            cutoff=np.quantile(ret,.05)
            rows.append({'strike_ratio':strike,'coverage':coverage,'premium_fraction':spend,
                         'terminal_ES95':-ret[ret<=cutoff].mean(),'mean_return':ret.mean()})
    return pd.DataFrame(rows).sort_values('terminal_ES95').reset_index(drop=True)
