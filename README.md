Website `gaston-fernandez.github.io`

## Folder structure

- `assets/js/`: front-end scripts used by the pages.
- `css/`: site stylesheets.
- `data/`: structured data files consumed by front-end scripts.
- `files/`: static assets (PDFs, images, icons, BibTeX files).
- `scripts/`: maintenance scripts used locally or in GitHub Actions.
- `.github/workflows/`: automation workflows (daily citation refresh).

## Research page citation badges

Published papers on `research.html` include a citation badge loaded from:

- `data/scholar_citations.json`

This file is updated by:

- `scripts/update_scholar_citations.py`
- `.github/workflows/update-scholar-citations.yml` (daily + manual trigger)

To update locally (with internet access):

```bash
python3 scripts/update_scholar_citations.py \
  --config data/scholar_publications.json \
  --output data/scholar_citations.json
```
