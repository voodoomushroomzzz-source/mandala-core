# MGE - Mandala Graph Explorer

Read-only tool for visualizing and analyzing Mandala structure.

## Work Reference

- Work: W-T-20261015-MGE
- Fruit: fruit-mge-001

## Usage

    python -m mge scan

From this directory, build the full dashboard with Python 3.12 or newer:

    python -m mge dashboard

Open the repository root's `index.html` in a browser. To build the same pages
into a separate static site root, as GitHub Pages does:

    python -m mge dashboard --output ../../../_site

The catalog pages embed their data and work from local files. The interactive
MGE graph loads vis-network from a CDN.
