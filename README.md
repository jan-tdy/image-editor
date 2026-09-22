# image-editor — PyView Editor

A fast, IrfanView-style image and video viewer/editor built with PyQt6.

## Part 1 — viewer & editor core

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

## Part 2 — batch tools & image joining

- **Batch Rename & Edit** (`Tools → Batch Rename & Edit...`, Ctrl+B) — pick
  files (or start from the open folder), then combine any of:
  - **Rename**: a token pattern (`{name} {ext} {n} {date} {parent} {orig}`),
    start/step/digit-padding for the sequence number, case transform, and
    find/replace (plain or regex). Live preview of every resulting filename,
    with conflicts flagged before anything runs.
  - **Convert & resize**: change format (JPEG/PNG/BMP/TIFF/WEBP), and resize
    (fit within, exact size, or scale %); JPEG quality is configurable.
  - **Adjust & rotate**: the same brightness/contrast/saturation/RGB sliders
    as the main editor, plus 90°/180°/270° rotation and flip — applied to
    every selected file. Video files are only renamed, never re-encoded.
  - **Output**: overwrite/rename in place, or write into a separate folder
    (non-destructive). Overwriting keeps `.bak` backups by default, so the
    whole run can be undone with one click (**Undo Last Run**).
  - Runs on a background thread with a progress bar and a per-file log, and
    can be cancelled mid-run.
- **Join Images** (`Tools → Join Images...`, Ctrl+J) — combine several images
  side by side:
  - Horizontal, vertical, or grid layout, with a reorderable (drag & drop)
    image list.
  - Spacing, alignment (top/center/bottom or left/center/right), background
    color or transparent background, and size normalization (match the
    smallest/largest image, or a custom size).
  - Debounced live preview, then Save As in any common format.

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
| Batch Rename & Edit | Ctrl+B |
| Join Images | Ctrl+J |

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
    rename_ops.py             batch rename pattern engine
    stitch_ops.py              image-joining/composition engine
  models/
    file_model.py             folder listing & navigation
  widgets/
    image_view.py             zoom/pan viewer + crop tool
    video_view.py              video playback widget
    thumbnail_panel.py         folder thumbnail browser
    adjustments_panel.py       brightness/contrast/RGB sliders
  workers/
    batch_worker.py             background batch rename/convert/resize/adjust
  dialogs/
    batch_dialog.py              Batch Rename & Edit dialog
    stitch_dialog.py             Join Images dialog
```

## Jadiv Code Master

This repo ships a `codemaster-metadata.json` so it's discoverable and
installable from [jan-tdy/codemaster](https://github.com/jan-tdy/codemaster).
