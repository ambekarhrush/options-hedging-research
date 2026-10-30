"""Long-only, self-financing close-to-close accounting with explicit cash."""
import numpy as np
import pandas as pd

def backtest(returns, targets, cost_bps=5, cash_daily=0.):
    """Targets dated t are executed at t close and first earn t+1 returns.

    Costs are bps per dollar traded across risky assets. Holdings drift between
    rebalance dates. Initial purchases incur costs. Cost is solved against post-cost
    NAV so weights, trading cash and wealth reconcile. Cash earns cash_daily.
    """
    cash_rates = (cash_daily.reindex(returns.index) if isinstance(cash_daily,pd.Series)
                  else pd.Series(float(cash_daily),index=returns.index))
    if cost_bps < 0 or cash_rates.isna().any() or not np.isfinite(cash_rates).all() or (cash_rates <= -1).any():
        raise ValueError('Invalid costs/cash return')
    if returns.isna().any().any() or not np.isfinite(returns.to_numpy()).all() or (returns <= -1).any().any():
        raise ValueError('Invalid asset returns')
    if not targets.columns.equals(returns.columns) or not targets.index.isin(returns.index).all() or targets.index.has_duplicates:
        raise ValueError('Target dates/assets must match returns')
    if targets.isna().any().any() or not np.isfinite(targets.to_numpy()).all() or (targets < 0).any().any() or (targets.sum(axis=1) > 1+1e-9).any():
        raise ValueError('Long-only, unlevered target weights required')
    holdings = np.zeros(returns.shape[1]); cash = 1.; nav = 1.; rows=[]; weights=[]
    rate = cost_bps/10000
    if rate >= 1:
        raise ValueError('Cost rate must be less than 100%')
    for date, row in returns.iterrows():
        before = nav
        holdings *= 1+row.to_numpy(); cash *= 1+cash_rates.loc[date]
        gross_nav = holdings.sum()+cash
        fee=0.; turnover=0.
        if date in targets.index:
            w = targets.loc[date].to_numpy()
            # Fixed-point solve C = rate * sum(abs(w*(NAV-C)-holdings)).
            fee = rate*np.abs(w*gross_nav-holdings).sum()
            for _ in range(100):
                new = rate*np.abs(w*(gross_nav-fee)-holdings).sum()
                if abs(new-fee)<1e-13:
                    fee=new; break
                fee=new
            desired = w*(gross_nav-fee)
            turnover = np.abs(desired-holdings).sum()/gross_nav
            holdings=desired; cash=(gross_nav-fee)*(1-w.sum())
        nav = holdings.sum()+cash
        rows.append([nav, nav/before-1, turnover, fee/before])
        weights.append(holdings/nav)
    result=pd.DataFrame(rows,index=returns.index,columns=['nav','return','turnover','cost'])
    return result, pd.DataFrame(weights,index=returns.index,columns=returns.columns)

def metrics(r):
    r=pd.Series(r).dropna()
    if r.empty: raise ValueError('No returns')
    nav=(1+r).cumprod(); dd=nav/nav.cummax().clip(lower=1)-1
    vol=r.std(ddof=1)*np.sqrt(252)
    q=r.quantile(.05)
    return {'CAGR': float(nav.iloc[-1]**(252/len(r))-1), 'volatility':float(vol),
            'Sharpe_zero_cash':float(r.mean()*252/vol) if vol>1e-12 else 0.,
            'max_drawdown':float(dd.min()),'daily_ES_95':float(-r[r<=q].mean()),
            'total_return':float(nav.iloc[-1]-1)}

def stress_windows(results, windows):
    rows=[]
    for name,(start,end) in windows.items():
        r=results.loc[start:end,'return']
        if not r.empty:
            rows.append({'window':name,'start':str(r.index.min().date()),'end':str(r.index.max().date()),**metrics(r)})
    return pd.DataFrame(rows)
