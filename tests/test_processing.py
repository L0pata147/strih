import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import processing as proc  # noqa: E402


def make_image(path: Path, size=(64, 48), fmt=None, mode="RGB"):
    Image.new(mode, size, (200, 30, 30)).save(path, format=fmt)
    return path


@pytest.mark.parametrize("ext,fmt", [(".jpg", "JPEG"), (".png", "PNG"), (".webp", "WEBP")])
def test_load_supported_formats(tmp_path, ext, fmt):
    img = proc.load_image(make_image(tmp_path / f"a{ext}", fmt=fmt))
    assert img.size == (64, 48)
    assert img.mode in ("RGB", "RGBA")


def test_palette_png_converted(tmp_path):
    img = proc.load_image(make_image(tmp_path / "p.png", mode="P"))
    assert img.mode == "RGB"


def test_rejects_unsupported_extension(tmp_path):
    p = make_image(tmp_path / "a.bmp", fmt="BMP")
    with pytest.raises(proc.ImageError, match="nepodporovaný formát"):
        proc.load_image(p)


def test_rejects_wrong_content(tmp_path):
    p = make_image(tmp_path / "fake.png", fmt="GIF")
    with pytest.raises(proc.ImageError, match="není JPG/PNG/WEBP"):
        proc.load_image(p)


def test_rejects_garbage(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_bytes(b"tohle neni obrazek")
    with pytest.raises(proc.ImageError, match="poškozený"):
        proc.load_image(p)


def test_rejects_truncated(tmp_path):
    p = make_image(tmp_path / "t.png", size=(400, 400))
    Image.effect_noise((400, 400), 50).save(p)
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    with pytest.raises(proc.ImageError, match="poškozený"):
        proc.load_image(p)


def test_rejects_truncated_jpeg(tmp_path):
    p = tmp_path / "t.jpg"
    Image.effect_noise((400, 400), 50).convert("RGB").save(p, quality=95)
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    with pytest.raises(proc.ImageError, match="poškozený"):
        proc.load_image(p)


def test_limit_size():
    big = Image.new("RGB", (4000, 1000))
    small = proc.limit_size(big)
    assert small.size == (2048, 512)
    same = Image.new("RGB", (2048, 100))
    assert proc.limit_size(same) is same


def test_hex_to_rgb():
    assert proc.hex_to_rgb("#ff8000") == (255, 128, 0)
    assert proc.hex_to_rgb("#fff") == (255, 255, 255)
    assert proc.hex_to_rgb("rgba(10, 20, 30, 1)") == (10, 20, 30)
    with pytest.raises(ValueError):
        proc.hex_to_rgb("#12")


def test_apply_background_and_preview():
    rgba = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    filled = proc.apply_background(rgba, (0, 255, 0))
    assert filled.mode == "RGB" and filled.getpixel((5, 5)) == (0, 255, 0)
    preview = proc.preview_on_checkerboard(rgba)
    assert preview.getpixel((0, 0)) == (255, 255, 255)
    assert preview.getpixel((20, 0)) == (204, 204, 204)


def test_unique_names():
    assert proc.unique_names(["a.png", "a.png", "A.png", "a_2.png"]) == [
        "a.png", "a_2.png", "A_3.png", "a_2_2.png"
    ]


def _result(name):
    return proc.Result(name, Image.new("RGB", (8, 8)), Image.new("RGBA", (8, 8), (1, 2, 3, 0)))


def test_save_single_png(tmp_path):
    out = proc.save_outputs([_result("x_bez_pozadi.png")], tmp_path)
    assert out.suffix == ".png"
    with Image.open(out) as im:
        assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0


def test_save_multiple_zip(tmp_path):
    out = proc.save_outputs([_result("x.png"), _result("x.png"), _result("y.png")], tmp_path)
    assert out.suffix == ".zip"
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["x.png", "x_2.png", "y.png"]
