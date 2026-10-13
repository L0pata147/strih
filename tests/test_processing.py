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


def _result(name, mask=False):
    out = Image.new("RGBA", (8, 8), (1, 2, 3, 0))
    return proc.Result(name, Image.new("RGB", (8, 8)), out, mask=out.getchannel("A") if mask else None)


def test_save_single_png(tmp_path):
    saved = proc.save_outputs([_result("x_bez_pozadi.png")], tmp_path)
    assert saved.zip is None and saved.downloads == saved.images
    with Image.open(saved.images[0]) as im:
        assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0


def test_save_multiple_zip(tmp_path):
    saved = proc.save_outputs([_result("x.png"), _result("x.png"), _result("y.png")], tmp_path)
    assert saved.downloads[0] == saved.zip
    with zipfile.ZipFile(saved.zip) as zf:
        assert sorted(zf.namelist()) == ["x.png", "x_2.png", "y.png"]


def test_save_with_mask_makes_zip(tmp_path):
    saved = proc.save_outputs([_result("a_bez_pozadi.png", mask=True)], tmp_path)
    assert [p.name for p in saved.masks] == ["a_maska.png"]
    with zipfile.ZipFile(saved.zip) as zf:
        assert sorted(zf.namelist()) == ["a_bez_pozadi.png", "a_maska.png"]


def _cutout():
    """100×80 průhledný obrázek s neprůhledným obdélníkem 20×40 na (30, 10)."""
    img = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (30, 10, 50, 50))
    return img


def test_subject_box_with_padding():
    assert proc.subject_box(_cutout(), 0) == (30, 10, 50, 50)
    assert proc.subject_box(_cutout(), 10) == (26, 6, 54, 54)  # 10 % ze 40 px
    assert proc.subject_box(Image.new("RGBA", (10, 10)), 5) is None


def test_process_file_crop_mask_and_bg(tmp_path, monkeypatch):
    monkeypatch.setattr(proc, "remove_background", lambda img, model, opts: _cutout())
    src = make_image(tmp_path / "postava.png", size=(100, 80), fmt="PNG")
    opts = proc.Options(crop=True, crop_padding=50, bg_color=(0, 255, 0), export_mask=True)
    r = proc.process_file(src, "isnet-anime", opts)
    assert r.output.size == r.original.size == r.mask.size == (60, 80)  # okraj 20 px přesahuje
    assert r.output.mode == "RGB" and r.output.getpixel((0, 0)) == (0, 255, 0)
    assert r.mask.getpixel((30, 40)) == 255 and r.mask.getpixel((0, 0)) == 0
    assert r.name == "postava_bez_pozadi.png"


@pytest.mark.parametrize("bg,pixel", [("white", (255, 255, 255)), ("black", (0, 0, 0)), ("checker", (255, 255, 255))])
def test_preview_on(bg, pixel):
    assert proc.preview_on(Image.new("RGBA", (40, 40)), bg).getpixel((1, 1)) == pixel


# --- volba GPU/CPU (GPU simulované falešnou session) ---------------------------------------


class FakeSession:
    def __init__(self, providers, hang=0.0, fail=False, silent_cpu=False):
        names = [p[0] if isinstance(p, tuple) else p for p in providers]
        if fail and "CUDAExecutionProvider" in names:
            raise RuntimeError("CUDA init failed")
        self.names = ["CPUExecutionProvider"] if silent_cpu else names
        self.hang = hang if "CUDAExecutionProvider" in self.names else 0.0
        self.inner_session = self

    def get_providers(self):
        return self.names

    def predict(self, img):
        import time
        time.sleep(self.hang)  # simulace kompilace CUDA jader při prvním výpočtu
        return [img]


@pytest.fixture
def fake_gpu(monkeypatch, tmp_path):
    import rembg

    monkeypatch.setattr(proc, "_providers", ["CUDAExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setattr(proc, "_sessions", {})
    monkeypatch.setattr(proc, "gpu_fallback_reason", None)
    monkeypatch.setattr(proc, "CPU_ONLY_MARKER", tmp_path / ".strih_cpu_only")
    monkeypatch.setattr(proc, "GPU_LOAD_TIMEOUT", 0.5)
    monkeypatch.setattr(proc, "_download_model", lambda name: None)

    def install(**behaviour):
        monkeypatch.setattr(rembg, "new_session", lambda name, providers: FakeSession(providers, **behaviour))

    return install


def test_gpu_ok(fake_gpu):
    fake_gpu()
    session = proc.get_session("isnet-anime")
    assert session.get_providers()[0] == "CUDAExecutionProvider"
    assert proc.device_label().startswith("GPU") and proc.gpu_fallback_reason is None


def test_gpu_hang_falls_back_to_cpu_and_remembers(fake_gpu):
    fake_gpu(hang=5)
    session = proc.get_session("isnet-anime")
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert proc.device_label() == "CPU"
    assert "déle než" in proc.gpu_fallback_reason
    assert proc.CPU_ONLY_MARKER.exists()


def test_gpu_error_falls_back_without_marker(fake_gpu):
    fake_gpu(fail=True)
    assert proc.get_session("isnet-anime").get_providers() == ["CPUExecutionProvider"]
    assert "CUDA init failed" in proc.gpu_fallback_reason
    assert not proc.CPU_ONLY_MARKER.exists()


def test_gpu_silently_on_cpu_detected(fake_gpu):
    fake_gpu(silent_cpu=True)
    proc.get_session("isnet-anime")
    assert proc.device_label() == "CPU" and "CUDA není funkční" in proc.gpu_fallback_reason


def test_cpu_forced_by_env_or_marker(monkeypatch, tmp_path):
    marker = tmp_path / ".strih_cpu_only"
    monkeypatch.setattr(proc, "CPU_ONLY_MARKER", marker)
    monkeypatch.setattr(proc, "_providers", None)
    monkeypatch.setenv("STRIH_CPU", "1")
    assert proc.get_providers() == ["CPUExecutionProvider"]
    monkeypatch.delenv("STRIH_CPU")
    monkeypatch.setattr(proc, "_providers", None)
    marker.write_text("x")
    assert proc.get_providers() == ["CPUExecutionProvider"]
