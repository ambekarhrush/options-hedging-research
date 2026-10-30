# Verification record · 0.2.0

Local verification on 30 October 2026, Python 3.12.3. This record describes executed checks; GitHub Actions status is reported separately by GitHub.

- 20 automated tests passed: independent binomial/Black–Scholes agreement, put-call parity, expiry and premium funding, covered calls, cash and NAV identities, independent expiry reconciliation, future-path independence, finite-input validation, calendar rejection, training-only control weights, monthly cash accounting, frequency-aware metrics and bootstrap invariants.
- The historical pipeline downloaded and hashed Cboe PPUT/CLL, Yahoo SPY adjusted closes and the French daily RF source. Raw data is kept locally under ignored `data/private/`.
- A daily-calendar audit found gaps before 2021. All 145 required month-end levels from December 2013 through December 2025 passed validation. The 2021–2025 daily study used 1,255 returns with no filling. Earlier crisis-quarter figures are retained separately.
- The original synthetic study and the expanded model study executed: 24 regime/strategy comparisons, 288 unique rolling-sensitivity combinations. The original strike/coverage choice stayed frozen.
- Two Jupyter notebooks executed from fresh kernels, with cell outputs retained and local HTML exports generated. The default execution requires no market-data downloads.
- Archived annual returns reconcile with full/development/validation total returns, and every model ledger reconciles cash, equity and option marks to NAV. Source-code hashes match the historical provenance record.
- The historical figure and notebook figures were visually reviewed. Relative documentation links and publication files were checked before upload.

## Limits of verification

Unit tests and notebook execution do not independently audit provider prices or establish investability. Historical indices may contain back-calculated history. The validation period is retrospective. GBM and crash stresses are assumptions, not fitted forecasts. No licensed historical option-chain execution study has been performed, and no live trading record is claimed.

`python scripts/verify_results.py` checks the archived evidence offline. `python scripts/check_notebooks.py` executes the notebook suite. Historical source reproduction is a separate, explicitly network-dependent command.
