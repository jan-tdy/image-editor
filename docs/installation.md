# Installation

## Requirements

- Python 3.10+
- `PyQt6`, `Pillow`, `send2trash`, `opencv-python-headless` (see `requirements.txt`). OpenCV is only used by [Auto-Stack](autostack.md).
- For video playback Qt's multimedia backend needs the usual system codec libraries (`ffmpeg` / `gstreamer` plugins). Without them the app still runs — video files just show a notice.

## Run

```bash
git clone https://github.com/jan-tdy/image-editor.git
cd image-editor
pip install -r requirements.txt
python3 main.py
```

You can also drag & drop a file or folder onto the window to open it.

## Set as the system default image viewer (Linux)

```bash
./packaging/install.sh
```

This installs a `pyview-editor` launcher to `~/.local/bin`, registers a desktop entry and icon under `~/.local/share`, and (unless you pass `--no-default`) runs `xdg-mime default` so PyView Editor becomes the default handler for JPEG, PNG, BMP, GIF, WEBP, TIFF, ICO and PPM/PGM/PBM. No `sudo` needed — everything is per-user.

Check or change the default for one type later:

```bash
xdg-mime query default image/png
xdg-mime default org.gnome.eog.desktop image/png   # revert, e.g. to eog
```
