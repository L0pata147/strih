"""Smoke test běžící aplikace přes Gradio API: zpracuje vzorový obrázek + poškozený soubor.

Použití: python tools/smoke_test.py http://127.0.0.1:7860 vzor.jpg
"""

import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from gradio_client import Client, handle_file
from PIL import Image


def wait_for(url: str, timeout: float = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=5)
            return
        except OSError:
            time.sleep(2)
    raise SystemExit(f"Aplikace na {url} nenaběhla do {timeout} s")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # konzole na Windows bývá cp1252
    url, sample = sys.argv[1], sys.argv[2]
    wait_for(url)
    broken = Path(tempfile.mkdtemp()) / "poskozeny.png"
    broken.write_bytes(b"tohle neni obrazek")

    client = Client(url, verbose=False)
    gallery, _slider, downloads, status, *_ = client.predict(
        [handle_file(sample), handle_file(str(broken))],
        "isnet-anime", False, 10, "Průhledné", "#ffffff", False, 5, False, True, "checker",
        api_name="/run",
    )
    print(status)
    assert "1/2" in status, status
    assert "poskozeny.png" in status, status
    names = sorted(Path(d).name for d in downloads)
    print("ke stažení:", names)
    stem = Path(sample).stem
    assert names == sorted(["bez_pozadi.zip", f"{stem}_bez_pozadi.png", f"{stem}_maska.png"]), names
    with Image.open(next(d for d in downloads if d.endswith("_bez_pozadi.png"))) as im:
        alpha = im.getchannel("A").getextrema()
        print("výstup:", im.mode, im.size, "alpha", alpha)
        assert im.mode == "RGBA" and alpha == (0, 255), alpha
    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
