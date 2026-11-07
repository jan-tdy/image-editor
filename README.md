# image-editor — PyView Editor

A fast, IrfanView-style image and video viewer/editor built with PyQt6.

<img width="1406" height="949" alt="image" src="https://github.com/user-attachments/assets/cd2b490c-3ab3-4173-8f40-ad1e6a92a30a" />


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
- **Undo/redo** for every edit. History is capped by memory rather than
  step count (about 512 MB of pixel data; the oldest steps are dropped first,
  and the most recent one is always kept).
- **File ops** — save, save as (format conversion via extension), revert to
  original, rename, delete (uses the system trash via `send2trash` when
  available, otherwise asks before permanently deleting).
- **Metadata** — on save, EXIF (camera, date, GPS, ...) and the ICC colour
  profile are kept for JPEG, PNG, WebP and TIFF. The orientation tag is reset
  because pixels are already upright, and pixel-size tags are rewritten after
  crop or resize. Turn this off with **File → Keep Metadata on Save**.
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
    Re-encoded files keep their EXIF and ICC profile unless you untick
    *Keep EXIF metadata and ICC colour profile*; renamed or copied files are
    never touched.
  - Each run that changed files also writes a hidden
    `.image-editor-batch-<timestamp>.json` **undo journal** next to its
    outputs (the output folder, or the folder the sources share). **Tools →
    Undo Last Batch** reverts the most recent run from that journal, even
    after the dialog was closed or the app restarted. The journal is removed
    once the undo completes without warnings.
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
- **Auto-Stack / Smart Stitch** (`Tools → Auto-Stack (Smart Stitch)...`,
  Ctrl+Shift+J) — combine many overlapping photos of the same scene (e.g.
  dozens of garden shots taken from different spots above) into one large
  image, by matching visual patterns between photos rather than placing them
  on a fixed layout:
  - Add individual files or a whole folder; a background pass does the
    feature matching, alignment and blending (OpenCV's `Stitcher`), with
    per-file load progress and a busy indicator while it aligns/blends.
  - **Scene type**: "Auto" (default — tries "Overhead / flat scene" and
    "Rotating camera" and keeps whichever includes more of the photos),
    "Overhead / flat scene" (a garden, a field, a document), or "Rotating
    camera" for a classic panorama shot by turning on the spot.
  - **Working size** caps the resolution used for matching/blending (lower
    = faster and lighter on memory; "Full resolution" is slow and can use a
    lot of RAM with many large photos).
  - The underlying stitcher can leave photos out of the result without that
    being an error — e.g. a stack of 100+ handheld overhead shots usually
    doesn't form one single provable chain. When that happens, Auto-Stack
    says how many of the photos were actually used and greys out the
    left-out ones in the list, instead of silently handing back a small or
    distorted result with no indication anything was skipped.
  - On failure (not enough overlap/detail between photos) it reports why,
    instead of crashing — try the other scene type or add more overlap
    between shots.

- **Photo Triage** (`Tools → Photo Triage...`, Ctrl+Shift+K) — sort a folder
  of photos into **Keep / Favourite / Trash** one by one, then apply everything
  as a single reviewed batch:
  - Setup: photos folder, favourites folder, order (name / date taken /
    random, ascending or descending).
  - Review window: photo in the centre, info at the side, rename field on
    top, **Back** / **Next** at the bottom corners (Next postpones the photo
    to the end of the queue), and Keep (K) / Favourite (F) / Trash (T) buttons.
    A rename is applied together with any action, including Keep.
  - A summary of all changes is shown first; nothing touches the disk until
    you click *Apply all*. Favourite moves the file, Trash uses the system
    trash (`send2trash`). Full documentation: <https://jan-tdy.github.io/image-editor/> (MkDocs, source in `docs/`).

## Requirements

- Python 3.10+
- `PyQt6`, `Pillow`, `send2trash`, `opencv-python-headless` (see
  `requirements.txt`) — OpenCV is only used for Auto-Stack's feature
  matching.
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
| Auto-Stack (Smart Stitch) | Ctrl+Shift+J |

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
    autostack_ops.py           feature-matching stitch engine (OpenCV)
  models/
    file_model.py             folder listing & navigation
  widgets/
    image_view.py             zoom/pan viewer + crop tool
    video_view.py              video playback widget
    thumbnail_panel.py         folder thumbnail browser
    adjustments_panel.py       brightness/contrast/RGB sliders
  workers/
    batch_worker.py             background batch rename/convert/resize/adjust
    autostack_worker.py         background Auto-Stack load + stitch
  dialogs/
    batch_dialog.py              Batch Rename & Edit dialog
    stitch_dialog.py             Join Images dialog
    autostack_dialog.py          Auto-Stack (Smart Stitch) dialog
```

## Set as the system default image viewer (Linux)

```bash
./packaging/install.sh
```

This installs a `pyview-editor` launcher to `~/.local/bin`, registers a
desktop entry + icon under `~/.local/share`, and (unless you pass
`--no-default`) runs `xdg-mime default` so PyView Editor becomes the default
handler for every image type it supports (JPEG, PNG, BMP, GIF, WEBP, TIFF,
ICO, PPM/PGM/PBM). No `sudo` needed — everything is installed per-user.

To check or change the default handler for a single type later:

```bash
xdg-mime query default image/png
xdg-mime default org.gnome.eog.desktop image/png   # revert, e.g. to eog
```

## Jadiv Code Master

This repo ships a `codemaster-metadata.json` so it's discoverable and
installable from [jan-tdy/codemaster](https://github.com/jan-tdy/codemaster).
