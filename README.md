# image-editor — PyView Editor

A fast, IrfanView-style image and video viewer/editor built with PyQt6.

## Part 1 (this release)

- **Browser** — open a folder and browse its images and videos as a
  thumbnail strip (async-loaded thumbnails, natural sort order).
- **Viewer** — zoom in/out, fit-to-window, 100% view, mouse-wheel zoom,
  click-and-drag panning.
- **Video playback** — play/pause, seek, volume, via Qt Multimedia. If the
  system's multimedia backend/codecs aren't available, the app degrades
  gracefully instead of crashing (video files just show a notice).
- **Rotate / flip** — lossless 90° rotate left/right, flip horizontal/vertical.
- **Crop** — interactive crop rectangle with draggable handles.
- **Adjustments** — live brightness, contrast, saturation and independent
  R/G/B channel sliders, with Apply/Reset/Cancel.
- **Undo/redo** for every edit.
- **File ops** — save, save as (format conversion via extension), revert to
  original, rename, delete (uses the system trash via `send2trash` when
  available, otherwise asks before permanently deleting).
- **Navigation** — next/previous within the folder, slideshow with a
  configurable interval.
- Fullscreen mode, drag & drop to open a file or folder, EXIF orientation is
  respected on load.

## Not yet implemented (Part 2 — pending confirmation)

- Batch editing: rename patterns, resize/convert/adjust many files at once.
- An image-joining/stitching canvas to combine several images side by side.

## Requirements

- Python 3.10+
- `PyQt6`, `Pillow`, `send2trash` (see `requirements.txt`)
- For video playback, Qt's multimedia backend needs its usual system codec
  libraries (e.g. `ffmpeg`/`gstreamer` plugins) — the app runs fine without
  them, just without video playback.

## Run

```bash
pip install -r requirements.txt
python3 main.py
```

## Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Open file / folder | Ctrl+O / Ctrl+Shift+O |
| Save / Save As | Ctrl+S / Ctrl+Shift+S |
| Undo / Redo | Ctrl+Z / Ctrl+Shift+Z |
| Rotate left / right | Ctrl+L / Ctrl+R |
| Flip horizontal / vertical | H / V |
| Crop | C (Enter to apply, Esc to cancel) |
| Adjustments panel | Ctrl+U |
| Zoom in / out | Ctrl++ / Ctrl+- |
| Fit to window / 100% | Ctrl+0 / Ctrl+1 |
| Next / previous | → / ← |
| Delete file | Del |
| Rename file | F2 |
| Fullscreen | F11 |
| Slideshow | F5 |

## Project layout

```
main.py                     entry point
image_editor/
  app.py                    main window: menus, toolbar, wiring
  constants.py               supported extensions, app metadata
  core/
    image_ops.py             Pillow-based edit operations
    image_document.py        editable document model (undo/redo, adjustments)
    convert.py                PIL <-> Qt pixmap conversion
  models/
    file_model.py             folder listing & navigation
  widgets/
    image_view.py             zoom/pan viewer + crop tool
    video_view.py              video playback widget
    thumbnail_panel.py         folder thumbnail browser
    adjustments_panel.py       brightness/contrast/RGB sliders
```

## Jadiv Code Master

This repo ships a `codemaster-metadata.json` so it's discoverable and
installable from [jan-tdy/codemaster](https://github.com/jan-tdy/codemaster).
