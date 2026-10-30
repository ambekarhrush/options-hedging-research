"""Execute every notebook from a fresh kernel, export HTML, optionally save outputs."""
import argparse
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from jupyter_client import KernelManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Save executed outputs into source notebooks')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'outputs/notebook-validation'
    output.mkdir(parents=True, exist_ok=True)
    for path in sorted((root / 'notebooks').glob('*.ipynb')):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        manager = KernelManager(kernel_name='python3')
        manager.kernel_spec.argv[0] = sys.executable
        try:
            client = NotebookClient(notebook, timeout=600, km=manager,
                                    resources={'metadata': {'path': str(root)}})
            client.execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
                manager.cleanup_resources()
        figures = sum('image/png' in item.get('data', {})
                      for cell in notebook.cells for item in cell.get('outputs', []))
        assert figures > 0, f'{path.name} produced no rendered research figures'
        nbformat.write(notebook, output / path.name)
        html, _ = HTMLExporter().from_notebook_node(notebook)
        (output / f'{path.stem}.html').write_text(html)
        if args.write:
            nbformat.write(notebook, path)
        print(f'PASS {path.name}: executed all cells and exported HTML', flush=True)


if __name__ == '__main__':
    main()
