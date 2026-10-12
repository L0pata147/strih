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
    url, sample = sys.argv[1], sys.argv[2]
    wait_for(url)
    broken = Path(tempfile.mkdtemp()) / "poskozeny.png"
    broken.write_bytes(b"tohle neni obrazek")

    client = Client(url, verbose=False)
    originals, previews, download, status = client.predict(
        [handle_file(sample), handle_file(str(broken))],
        "isnet-anime", False, False, "#ffffff",
        api_name="/run",
    )
    print(status)
    assert "1/2" in status, status
    assert "poskozeny.png" in status, status
    assert len(originals) == len(previews) == 1
    with Image.open(download) as im:
        alpha = im.getchannel("A").getextrema()
        print("výstup:", Path(download).name, im.mode, im.size, "alpha", alpha)
        assert im.mode == "RGBA" and alpha == (0, 255), alpha
    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
