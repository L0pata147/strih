"""Instalace závislostí: zjistí NVIDIA GPU a podle toho nainstaluje onnxruntime-gpu nebo CPU verzi.

Spouští se ze start.bat:
- vývojový režim (.venv): nainstaluje vše z requirements.txt + onnxruntime (CPU/GPU),
- přenosný režim (--portable, vložený Python ve složce python/): vše už je přibalené,
  jen při nalezení NVIDIA GPU nabídne stažení GPU zrychlení.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
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


def install_gpu(driver: int) -> bool:
    """Vymění onnxruntime (CPU) za onnxruntime-gpu. Při neúspěchu zůstane CPU verze funkční."""
    ort_gpu = ORT_GPU_CUDA13 if driver >= CUDA13_MIN_DRIVER else ORT_GPU_CUDA12
    print(f"== Stahuji {ort_gpu} ==", flush=True)
    with tempfile.TemporaryDirectory(prefix="strih_gpu_") as tmp:
        # Nejdřív vše stáhnout; CPU verzi odinstalovat až když máme GPU balíčky v ruce
        if not pip("download", "--dest", tmp, ort_gpu):
            return False
        # CPU a GPU varianta spolu kolidují (sdílí modul onnxruntime)
        pip("uninstall", "-y", "onnxruntime", "onnxruntime-gpu")
        if pip("install", "--no-index", "--find-links", tmp, ort_gpu):
            return True
    print("Varovani: instalace GPU verze selhala, vracim CPU verzi.")
    pip("uninstall", "-y", "onnxruntime-gpu")
    pip("install", ORT_CPU)
    return False


def ask_yes_no(question: str) -> bool:
    try:
        return input(f"{question} [a/N]: ").strip().lower() in ("a", "ano", "y", "yes")
    except EOFError:  # bez konzole (např. CI) -> ne
        return False


def main_portable() -> int:
    """Přenosná verze: knihovny i CPU onnxruntime jsou přibalené, řeší se jen volitelné GPU."""
    driver = nvidia_driver_major()
    if driver is not None:
        print()
        print("Nalezena NVIDIA GPU. Aplikace funguje i bez ni (na CPU), ale GPU je mnohem rychlejsi.")
        print("GPU zrychleni vyzaduje jednorazove stazeni cca 2-3 GB.")
        if ask_yes_no("Stahnout GPU zrychleni?"):
            if install_gpu(driver):
                print("== GPU zrychleni nainstalovano ==")
            else:
                print("GPU zrychleni se nepodarilo nainstalovat, aplikace pobezi na CPU.")
        else:
            print("Preskoceno. Pozdeji to zapnes smazanim souboru python\\.strih_installed.")
    MARKER.write_text("ok\n", encoding="utf-8")
    return 0


def main() -> int:
    if "--portable" in sys.argv:
        return main_portable()

    print("== Instalace zavislosti ==", flush=True)
    if not pip("install", "--upgrade", "pip"):
        print("Varovani: aktualizace pipu selhala, pokracuji.")
    if not pip("install", "-r", str(ROOT / "requirements.txt")):
        print("CHYBA: instalace zavislosti z requirements.txt selhala.")
        return 1
    if not pip("install", ORT_CPU):
        return 1

    driver = nvidia_driver_major()
    if driver is not None:
        print(f"== NVIDIA GPU nalezena (ovladac {driver}) -> instaluji onnxruntime-gpu ==", flush=True)
        if not install_gpu(driver):
            print("Varovani: onnxruntime-gpu se nepodarilo nainstalovat, pouziji CPU verzi.")
    else:
        print("== NVIDIA GPU nenalezena -> pouziji onnxruntime (CPU) ==", flush=True)

    MARKER.write_text("ok\n", encoding="utf-8")
    print("== Instalace dokoncena ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
