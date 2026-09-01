"""Choosing which side of the page the text stands on."""
from __future__ import annotations

from PIL import Image, ImageDraw

from glanceboard import composition


def picture(left_tone: int, right_tone: int, size=(400, 300)) -> Image.Image:
    """A drawing with a known amount of ink in each half."""
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size[0] // 2, size[1]), fill=left_tone)
    draw.rectangle((size[0] // 2, 0, size[0], size[1]), fill=right_tone)
    return image


def test_ink_is_measured_per_half():
    left, right = composition.ink_by_half(picture(0, 255))
    assert left > 0.9 and right < 0.1


def test_the_text_goes_where_there_is_less_ink():
    assert composition.quieter_side(picture(0, 255)) == composition.RIGHT
    assert composition.quieter_side(picture(255, 0)) == composition.LEFT


def test_a_near_tie_leaves_the_layout_alone():
    """A board that swaps sides every morning on a hair's difference is harder
    to read than one that stays put."""
    almost_equal = picture(200, 205)
    assert composition.quieter_side(almost_equal, current=composition.RIGHT) == composition.RIGHT
    assert composition.quieter_side(almost_equal, current=composition.LEFT) == composition.LEFT


def test_the_model_wins_when_it_has_an_opinion():
    """It knows a hatched sky is busy but unimportant, and the count does not."""
    busy_on_the_right = picture(255, 0)  # ink says: put the text left
    assert composition.side_away_from("left", busy_on_the_right) == composition.RIGHT


def test_centre_is_not_an_answer_the_layout_can_use():
    assert composition.side_away_from("centre", picture(0, 255)) == composition.RIGHT


def test_no_opinion_falls_back_to_the_ink():
    assert composition.side_away_from(None, picture(0, 255)) == composition.RIGHT


def test_a_blank_picture_changes_nothing():
    blank = Image.new("L", (200, 200), 255)
    assert composition.quieter_side(blank, current=composition.RIGHT) == composition.RIGHT
