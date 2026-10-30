"""Published quarterly benchmark comparisons and transparent synthetic option paths."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .engine import metrics
from .options import scenario_paths, overlay, optimise_hedge

# Published Cboe table, expressed as percent total return. These are three
# selected historical quarters; not a continuous backtest or options quotes.
CBOE = {'2008 Q4':{'SPX':-21.9,'PPUT':0.2,'CLL':-5.9},
        '2020 Q1':{'SPX':-19.6,'PPUT':0.0,'CLL':-5.0},
        '2022 Q2':{'SPX':-16.1,'PPUT':-13.1,'CLL':-6.7}}

def run(out='results'):
    out=Path(out);out.mkdir(exist_ok=True,parents=True)
    historical=pd.DataFrame(CBOE).T
    historical['PPUT_minus_SPX_pp']=historical.PPUT-historical.SPX
    historical['CLL_minus_SPX_pp']=historical.CLL-historical.SPX
    historical.to_csv(out/'historical_quarters.csv',index_label='quarter')
    rows=[]; series={}
    for name,(spot,iv) in scenario_paths(42).items():
        strategies={'unhedged':spot/spot[0], 'half_equity_cash':.5+.5*spot/spot[0]}
        for strategy,call in [('put',None),('collar',1.1)]:
            led=overlay(spot,iv,coverage=1.,put_moneyness=.95,call_moneyness=call,cost_bps=10)
            led.to_csv(out/f'{name}_{strategy}_ledger.csv',index_label='session')
            strategies[strategy]=led.nav.to_numpy()
        series[name]=pd.DataFrame({'spot':spot,'iv':iv,**strategies})
        series[name].to_csv(out/f'{name}_paths.csv',index_label='session')
        for strat,nav in strategies.items():
            r=np.diff(np.r_[1.,nav])/np.r_[1.,nav][:-1]
            rows.append({'scenario':name,'strategy':strat,'total_return':nav[-1]-1,'max_drawdown':metrics(r)['max_drawdown']})
    summary=pd.DataFrame(rows);summary.to_csv(out/'simulated_scenarios.csv',index=False)
    grid=optimise_hedge(seed=142,annual_budget=.02,paths=10000)
    grid.to_csv(out/'sizing_grid.csv',index=False)
    # Re-evaluate the selected choice on independent simulated paths.
    chosen=grid.iloc[0];rng=np.random.default_rng(314)
    from .options import black_scholes
    terminal=100*np.exp(np.sum((.04-.5*.22**2)/252+.22/np.sqrt(252)*rng.normal(size=(10000,252)),axis=1))
    premium=float(black_scholes(100,100*chosen.strike_ratio,1,.22))
    shares=1/(100+chosen.coverage*premium)
    pnl=shares*(terminal+chosen.coverage*np.maximum(100*chosen.strike_ratio-terminal,0))-1
    unhedged=terminal/100-1
    def es(a):
        q=np.quantile(a,.05);return float(-a[a<=q].mean())
    validation={'seed':314,'paths':10000,'chosen_strike_ratio':float(chosen.strike_ratio),'chosen_coverage':float(chosen.coverage),'premium_fraction':float(chosen.premium_fraction),'model_hedge_terminal_ES95':es(pnl),'model_unhedged_terminal_ES95':es(unhedged),'model_hedge_mean_return':float(pnl.mean()),'model_unhedged_mean_return':float(unhedged.mean())}
    (out/'independent_model_validation.json').write_text(json.dumps(validation,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,2,figsize=(12,8))
    for a,(name,frame) in zip(ax.flat,series.items()):
        for col in ['unhedged','half_equity_cash','put','collar']:a.plot(frame[col],label=col,lw=1.4)
        a.set_title(name.replace('_',' ').title());a.grid(alpha=.2);a.set_ylabel('NAV from $1');a.set_xlabel('Model session')
    ax[0,0].legend(fontsize=8);fig.suptitle('MODEL SCENARIOS — not historical events');fig.tight_layout();fig.savefig(out/'model_scenarios.png',dpi=140);plt.close(fig)
    report=f'''# Options-based portfolio protection: research memo

## Question

How do protective puts and collars compare with unhedged equity and reduced equity exposure, and how should a hedge be sized under a premium budget?

## Historical evidence: published Cboe benchmark quarters

Cboe reports total returns for fixed-rule benchmark indices over selected adverse quarters. This is the published comparison, in percent, not a custom options backtest:

| Quarter | S&P 500 total return | PPUT | CLL | PPUT minus S&P, pp | CLL minus S&P, pp |
|---|---:|---:|---:|---:|---:|
'''
    for q,x in historical.iterrows(): report+=f"| {q} | {x.SPX:.1f}% | {x.PPUT:.1f}% | {x.CLL:.1f}% | {x.PPUT_minus_SPX_pp:.1f} | {x.CLL_minus_SPX_pp:.1f} |\n"
    report+='''
PPUT holds S&P 500 exposure and buys monthly 5%-out-of-the-money SPX puts. CLL buys quarterly 5%-out-of-the-money puts and sells monthly 10%-out-of-the-money calls. Their index rules, roll dates and option execution assumptions differ. These are hypothetical indices; they embed option economics under index methodology but do not establish a particular investor's realised fills, commissions, spreads or taxes. These quarters were selected because they were stressed: they cannot establish long-run hedge cost, maximum drawdown or investment performance. 2022 Q2 is not the whole 2022 sell-off.

Source: https://www.cboe.com/us/index_protection/ — table "Index Performance in Challenging Quarters". Methodologies: https://cdn.cboe.com/api/global/us_indices/governance/PPUT_Methodology.pdf and https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Collar_Indices_Methodology.pdf.

## Custom option simulation: synthetic paths only

The four hypothetical paths are abrupt crash, prolonged sell-off, inflation-style grind and rising market. They are deliberately generated paths, not historical reconstructions of 2008, 2020 or 2022. Comparison includes full unhedged exposure, 50% equity/50% zero-yield cash, 100% 5%-OTM rolling puts, and 95/110 rolling collars. Options are European and cash-settled; roll every 21 sessions; Black–Scholes uses the scenario's assumed daily IV. Equity turnover and option premium trades cost 10 bps. Initial equity and option premiums are funded from the same NAV, and premium cost reduces the equity position. The half-equity control is an initially funded buy-and-hold combination, not daily rebalanced. See model_scenarios.png and simulated_scenarios.csv.

Caveats: model-implied volatility paths are stipulated, not observed option quotes. No skew surface, dividends, assignment, margin, bid/ask liquidity, jumps or realistic execution delay. Results are model sensitivities, not historical executable returns.

## Premium-budget sizing

One-year European static puts are selected from strikes 85/90/95/100% and coverages 0/25/50/75/100%, subject to the upfront premium being at most 2% of initial NAV. Training uses 10,000 simulated GBM paths, seed 142, spot volatility/IV 22%, expected drift 4%, zero rates/dividends and terminal 95% expected shortfall as objective. This is terminal-loss optimisation, not drawdown optimisation or an annual rolling-premium estimate. The same data path set is used for each candidate. The selected configuration is evaluated on a separate set of 10,000 GBM paths, seed 314; both sets share the same model assumptions. No costs are applied in the static sizing experiment.

'''
    report+=f"Selected strike: {chosen.strike_ratio:.0%}; coverage: {chosen.coverage:.0%}; premium: {chosen.premium_fraction:.2%} of NAV. Independent model sample terminal ES95: hedge {validation['model_hedge_terminal_ES95']:.2%}, unhedged {validation['model_unhedged_terminal_ES95']:.2%}; mean terminal return hedge {validation['model_hedge_mean_return']:.2%}, unhedged {validation['model_unhedged_mean_return']:.2%}. These are model results, not market estimates.\n"
    report+='''
## What remains for a full empirical project

Obtain licensed point-in-time option chains covering 2008, 2020 and 2022, with actual contract expiries, bid/ask quotes, dividends, rates, settlement, roll calendar and stale-quote rules. Build a trade-level historical simulator, compare with matched-risk allocation and record realised premium drag, drawdown saved, tail losses and upside sacrificed. Reserve an untouched later period for selection and validation. Cboe published quarterly points cannot be used to infer continuous performance or tune strikes and coverage.
'''
    (out/'RESEARCH_MEMO.md').write_text(report)
    print(historical.to_string());print(json.dumps(validation,indent=2))

if __name__=='__main__':run()
