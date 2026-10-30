# Research notebooks

Open the numbered notebooks in order. Saved outputs are included for immediate review; all default cells run offline.

From the repository root:

```bash
pip install ".[notebooks]"
jupyter lab notebooks/
python scripts/check_notebooks.py
```

The checker uses a fresh Python kernel for each notebook and exports HTML to ignored `outputs/notebook-validation/`. Add `--write` to refresh the saved notebook outputs after a deliberate change. Optional historical-source downloads are disabled by default. Synthetic experiments are labelled in titles and conclusions.
