# Batch Rename & Edit

`Tools → Batch Rename & Edit...` (++ctrl+b++) — pick files (or start from the open folder), then combine any of the following.

## Rename

A token pattern: `{name} {ext} {n} {date} {parent} {orig}`, with start / step / digit padding for the sequence number, a case transform and find/replace (plain or regex). A live preview shows every resulting file name and flags conflicts *before* anything runs.

## Convert & resize

Change format (JPEG / PNG / BMP / TIFF / WEBP) and resize (fit within, exact size or scale %). JPEG quality is configurable.

## Adjust & rotate

The same brightness / contrast / saturation / RGB sliders as the editor, plus 90° / 180° / 270° rotation and flips, applied to every selected file. Video files are only renamed, never re-encoded.

## Output and undo

- **Overwrite / rename in place**, or write into a separate folder (non-destructive). Overwriting keeps `.bak` backups by default, so a run can be undone with **Undo Last Run**.
- Re-encoded files keep EXIF and the ICC profile unless you untick *Keep EXIF metadata and ICC colour profile*; renamed or copied files are never touched.
- Every run that changed files writes a hidden `.image-editor-batch-<timestamp>.json` **undo journal** next to its outputs. **Tools → Undo Last Batch** reverts the latest run from it, even after a restart. The journal is removed once the undo completes without warnings.
- Runs on a background thread with a progress bar and per-file log, and can be cancelled.
