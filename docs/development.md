# Development

## Project layout

```
main.py                     entry point
image_editor/
  app.py                    main window: menus, toolbar, wiring
  constants.py              supported extensions, app metadata
  core/                     image ops, document model, rename/stitch/autostack/triage engines
  models/file_model.py      folder listing & navigation
  widgets/                  image view, video view, thumbnails, adjustments panel
  workers/                  background batch / auto-stack workers
  dialogs/                  batch, join, auto-stack and triage dialogs
tests/                      unittest suite
docs/                       this documentation (MkDocs)
```

## Tests

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests
```

## Building these docs

```bash
pip install -r requirements-docs.txt
mkdocs serve          # live preview at http://127.0.0.1:8000
mkdocs build --strict
```

The site is deployed to GitHub Pages by `.github/workflows/docs.yml` on every push to `main` that touches the docs. Enable it once in **Settings → Pages → Source: GitHub Actions**.
