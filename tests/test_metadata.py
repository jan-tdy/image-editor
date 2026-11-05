import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageCms
from PIL.ExifTags import Base

from image_editor.core import image_ops
from image_editor.core.image_document import ImageDocument

EXIF_IFD = 0x8769
PIXEL_X = 0xA002
PIXEL_Y = 0xA003


def srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def camera_exif(orientation: int = 6, size=(40, 20)) -> bytes:
    exif = Image.Exif()
    exif[Base.Orientation] = orientation
    exif[Base.Make] = "TestCam"
    exif[Base.ImageWidth] = size[0]
    exif[Base.ImageLength] = size[1]
    sub = exif.get_ifd(EXIF_IFD)
    sub[PIXEL_X] = size[0]
    sub[PIXEL_Y] = size[1]
    return exif.tobytes()


class MetadataSaveTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name)

    def make_camera_jpeg(self, name="photo.jpg", size=(40, 20), orientation=6):
        path = self.folder / name
        Image.new("RGB", size, (200, 10, 10)).save(
            path, exif=camera_exif(orientation, size), icc_profile=srgb_profile(), quality=92
        )
        return path

    def test_jpeg_save_keeps_exif_and_icc_and_resets_orientation(self):
        source = self.make_camera_jpeg()
        document = ImageDocument(str(source))
        self.assertEqual(document.size, (20, 40))  # EXIF orientation 6 baked in

        out = document.save(str(self.folder / "out.jpg"))

        saved = Image.open(out)
        self.assertEqual(saved.size, (20, 40))
        self.assertEqual(saved.getexif().get(Base.Orientation), 1)  # pixels are already upright
        self.assertEqual(saved.getexif().get(Base.Make), "TestCam")
        self.assertTrue(saved.info.get("icc_profile"))

    def test_save_rewrites_pixel_dimension_tags_after_crop(self):
        source = self.make_camera_jpeg(orientation=1, size=(40, 20))
        document = ImageDocument(str(source))
        document.crop((0, 0, 10, 8))

        out = document.save(str(self.folder / "cropped.jpg"))

        exif = Image.open(out).getexif()
        self.assertEqual(exif.get(Base.ImageWidth), 10)
        self.assertEqual(exif.get(Base.ImageLength), 8)
        sub = exif.get_ifd(EXIF_IFD)
        self.assertEqual(sub.get(PIXEL_X), 10)
        self.assertEqual(sub.get(PIXEL_Y), 8)

    def test_save_strips_metadata_when_keep_metadata_is_off(self):
        source = self.make_camera_jpeg(orientation=1)
        document = ImageDocument(str(source))
        document.keep_metadata = False

        out = document.save(str(self.folder / "stripped.jpg"))

        saved = Image.open(out)
        self.assertIsNone(saved.getexif().get(Base.Make))
        self.assertFalse(saved.info.get("icc_profile"))

    def test_png_save_keeps_icc_and_exif(self):
        source = self.folder / "photo.png"
        Image.new("RGBA", (12, 6), (1, 2, 3, 255)).save(
            source, exif=camera_exif(orientation=1, size=(12, 6)), icc_profile=srgb_profile()
        )
        document = ImageDocument(str(source))

        out = document.save(str(self.folder / "out.png"))

        saved = Image.open(out)
        self.assertTrue(saved.info.get("icc_profile"))
        self.assertEqual(saved.getexif().get(Base.Make), "TestCam")

    def test_png_strip_does_not_auto_copy_icc(self):
        source = self.folder / "photo.png"
        Image.new("RGB", (12, 6), (1, 2, 3)).save(source, icc_profile=srgb_profile())
        document = ImageDocument(str(source))
        document.keep_metadata = False

        out = document.save(str(self.folder / "out.png"))

        self.assertFalse(Image.open(out).info.get("icc_profile"))

    def test_grayscale_source_does_not_carry_its_icc_profile(self):
        # The editor decodes grayscale to RGB without colour management, so an
        # RGB-tagged output must not inherit a grayscale profile.
        source = self.folder / "gray.png"
        Image.new("L", (6, 6), 128).save(source, icc_profile=srgb_profile())
        document = ImageDocument(str(source))
        self.assertIsNone(document.metadata.icc_profile)

    def test_unsupported_extension_gets_no_metadata_kwargs(self):
        self.assertEqual(image_ops.metadata_save_kwargs(image_ops.ImageMetadata(b"x", b"y"), ".gif", (4, 4)), {})

    def test_unparseable_exif_is_dropped_not_fatal(self):
        meta = image_ops.ImageMetadata(exif=b"\x00\x01garbage", icc_profile=None)
        kwargs = image_ops.metadata_save_kwargs(meta, ".jpg", (4, 4))
        self.assertEqual(kwargs["exif"], b"")


if __name__ == "__main__":
    unittest.main()
