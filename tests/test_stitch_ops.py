import unittest

from PIL import Image

from image_editor.core.stitch_ops import StitchOptions, compose


def solid(size, color):
    return Image.new("RGB", size, color)


class StitchOpsTests(unittest.TestCase):
    def test_empty_composition_returns_background_pixel(self):
        result = compose([], StitchOptions(background=(1, 2, 3, 4)))
        self.assertEqual(result.size, (1, 1))
        self.assertEqual(result.getpixel((0, 0)), (1, 2, 3, 4))

    def test_horizontal_layout_accounts_for_spacing(self):
        result = compose(
            [solid((2, 3), "red"), solid((4, 2), "blue")],
            StitchOptions(direction="horizontal", spacing=2, align="top"),
        )
        self.assertEqual(result.size, (8, 3))
        self.assertEqual(result.getpixel((0, 0))[:3], (255, 0, 0))
        self.assertEqual(result.getpixel((4, 0))[:3], (0, 0, 255))

    def test_negative_spacing_is_treated_as_zero(self):
        result = compose(
            [solid((2, 1), "red"), solid((3, 1), "blue")],
            StitchOptions(direction="horizontal", spacing=-10),
        )
        self.assertEqual(result.size, (5, 1))

    def test_horizontal_bottom_alignment_leaves_background_above_short_image(self):
        result = compose(
            [solid((1, 3), "red"), solid((1, 1), "blue")],
            StitchOptions(direction="horizontal", spacing=0, align="bottom", background=(9, 8, 7, 255)),
        )
        self.assertEqual(result.getpixel((1, 0)), (9, 8, 7, 255))
        self.assertEqual(result.getpixel((1, 2))[:3], (0, 0, 255))

    def test_vertical_right_alignment_positions_narrow_image(self):
        result = compose(
            [solid((3, 1), "red"), solid((1, 2), "blue")],
            StitchOptions(direction="vertical", spacing=1, align="right"),
        )
        self.assertEqual(result.size, (3, 4))
        self.assertEqual(result.getpixel((2, 2))[:3], (0, 0, 255))

    def test_match_smallest_normalizes_horizontal_heights(self):
        result = compose(
            [solid((8, 4), "red"), solid((3, 2), "blue")],
            StitchOptions(direction="horizontal", spacing=0, resize_mode="match_smallest"),
        )
        self.assertEqual(result.size, (7, 2))

    def test_match_largest_normalizes_vertical_widths(self):
        result = compose(
            [solid((2, 4), "red"), solid((4, 2), "blue")],
            StitchOptions(direction="vertical", spacing=0, resize_mode="match_largest"),
        )
        self.assertEqual(result.size, (4, 10))

    def test_custom_size_is_clamped_to_one_pixel(self):
        result = compose(
            [solid((4, 2), "red")],
            StitchOptions(direction="horizontal", resize_mode="custom", custom_size=0),
        )
        self.assertEqual(result.size, (2, 1))

    def test_grid_dimensions_and_centering_for_incomplete_last_row(self):
        result = compose(
            [solid((4, 4), "red"), solid((2, 2), "blue"), solid((1, 3), "green")],
            StitchOptions(direction="grid", columns=2, spacing=1, background=(10, 10, 10, 255)),
        )
        self.assertEqual(result.size, (9, 9))
        self.assertEqual(result.getpixel((6, 1))[:3], (0, 0, 255))
        self.assertEqual(result.getpixel((0, 5)), (10, 10, 10, 255))

    def test_grid_columns_are_clamped_to_one(self):
        result = compose(
            [solid((2, 1), "red"), solid((2, 1), "blue")],
            StitchOptions(direction="grid", columns=0, spacing=2),
        )
        self.assertEqual(result.size, (2, 4))


if __name__ == "__main__":
    unittest.main()
