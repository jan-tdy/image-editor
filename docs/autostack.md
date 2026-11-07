# Auto-Stack (Smart Stitch)

`Tools → Auto-Stack (Smart Stitch)...` (++ctrl+shift+j++) combines many overlapping photos of the same scene (e.g. dozens of garden shots taken from different spots) into one large image by matching visual features between photos, using OpenCV's `Stitcher`.

- Add individual files or a whole folder; loading, alignment and blending run in the background with progress.
- **Scene type:** *Auto* (tries both and keeps the one that uses more photos), *Overhead / flat scene* (garden, field, document) or *Rotating camera* (classic panorama).
- **Working size** caps the resolution used for matching and blending. Lower is faster and lighter; *Full resolution* is slow and can use a lot of RAM.

!!! note "Not every photo is always used"
    The stitcher may leave photos out without it being an error — a stack of 100+ handheld overhead shots usually doesn't form one provable chain. Auto-Stack tells you how many photos were used and greys out the left-out ones.

If stitching fails (not enough overlap or detail) the reason is reported instead of crashing — try the other scene type or add more overlap between shots.
