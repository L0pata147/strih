"""Instalace závislostí: zjistí NVIDIA GPU a podle toho nainstaluje onnxruntime-gpu nebo CPU verzi.

Spouští se z start.bat interpretem z virtuálního prostředí (.venv).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = Path(sys.prefix) / ".strih_installed"

# [cuda,cudnn] stáhne CUDA a cuDNN knihovny jako pip balíčky -> není potřeba instalovat CUDA Toolkit.
# onnxruntime-gpu >= 1.27 je postavené na CUDA 13 (ovladač 580+), starší verze na CUDA 12 (ovladač 528+).
ORT_GPU_CUDA13 = "onnxruntime-gpu[cuda,cudnn]>=1.27"
ORT_GPU_CUDA12 = "onnxruntime-gpu[cuda,cudnn]>=1.21,<1.27"
CUDA13_MIN_DRIVER = 580
ORT_CPU = "onnxruntime>=1.18"


def pip(*args: str) -> bool:
    cmd = [sys.executable, "-m", "pip", *args]
    print(">", " ".join(cmd), flush=True)
    return subprocess.call(cmd) == 0


def nvidia_driver_major() -> int | None:
    """Vrátí hlavní verzi ovladače NVIDIA (např. 572), nebo None, pokud GPU není."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run(
            [smi, "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if out.returncode != 0 or not lines:
        return None
    for line in lines:
        print("  nalezeno:", line)
    try:
        return int(lines[0].rsplit(",", 1)[1].strip().split(".")[0])
    except (IndexError, ValueError):
        return 0


def main() -> int:
    print("== Instalace zavislosti ==", flush=True)
    if not pip("install", "--upgrade", "pip"):
        print("Varovani: aktualizace pipu selhala, pokracuji.")
    if not pip("install", "-r", str(ROOT / "requirements.txt")):
        print("CHYBA: instalace zavislosti z requirements.txt selhala.")
        return 1

    driver = nvidia_driver_major()
    if driver is not None:
        ort_gpu = ORT_GPU_CUDA13 if driver >= CUDA13_MIN_DRIVER else ORT_GPU_CUDA12
        print(f"== NVIDIA GPU nalezena (ovladac {driver}) -> instaluji {ort_gpu} ==", flush=True)
        # CPU a GPU varianta spolu kolidují (sdílí modul onnxruntime)
        pip("uninstall", "-y", "onnxruntime")
        if not pip("install", ort_gpu):
            print("Varovani: onnxruntime-gpu se nepodarilo nainstalovat, pouziji CPU verzi.")
            pip("uninstall", "-y", "onnxruntime-gpu")
            if not pip("install", ORT_CPU):
                return 1
    else:
        print("== NVIDIA GPU nenalezena -> instaluji onnxruntime (CPU) ==", flush=True)
        if not pip("install", ORT_CPU):
            return 1

    MARKER.write_text("ok\n", encoding="utf-8")
    print("== Instalace dokoncena ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
