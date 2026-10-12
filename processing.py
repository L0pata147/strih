"""Logika odstranění pozadí: načtení a validace obrázků, cache modelů, rembg, náhledy, export."""

from __future__ import annotations

import logging
import os
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)

MAX_SIDE = 2048
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO = JPEG z některých fotoaparátů

# Klíč = název modelu v rembg, hodnota = (popisek v UI, kdy ho použít)
MODELS: dict[str, tuple[str, str]] = {
    "isnet-anime": (
        "isnet-anime – anime a kreslené postavy",
        "Pro anime, manga, kreslené postavy, fanart a ilustrace s výraznými obrysy.",
    ),
    "birefnet-portrait": (
        "birefnet-portrait – lidé z fotek",
        "Pro fotky lidí (portréty, cosplay). Nejlepší na vlasy, ale pomalejší a větší model.",
    ),
    "isnet-general-use": (
        "isnet-general-use – obecný",
        "Univerzální volba pro cokoliv dalšího: figurky, 3D rendery, zvířata, předměty.",
    ),
}
DEFAULT_MODEL = "isnet-anime"


class ImageError(Exception):
    """Chyba vstupního souboru, kterou lze srozumitelně zobrazit uživateli."""


# ---------------------------------------------------------------------------
# Detekce GPU a cache modelů
# ---------------------------------------------------------------------------

_providers: list[str] | None = None
_sessions: dict[str, object] = {}
_session_lock = threading.Lock()

# Načtení modelu na GPU (vč. zkušebního výpočtu) trvá normálně pár sekund. U některých karet
# ovladač při prvním použití kompiluje CUDA jádra i desítky minut -> po limitu přepneme na CPU.
GPU_LOAD_TIMEOUT = 60
# Po selhání GPU si to zapamatujeme, ať další starty nečekají znovu (smazáním se GPU zase zapne)
CPU_ONLY_MARKER = Path(sys.prefix) / ".strih_cpu_only"
# Hláška pro UI, proč se přešlo na CPU (aplikace ji zobrazí jednou)
gpu_fallback_reason: str | None = None

CUDA_PROVIDER = (
    "CUDAExecutionProvider",
    # bez vyčerpávajícího hledání cuDNN algoritmů -> rychlejší první výpočet
    {"cudnn_conv_algo_search": "HEURISTIC"},
)


def get_providers() -> list[str]:
    """Vrátí execution providery pro onnxruntime: CUDA, pokud je k dispozici, jinak CPU."""
    global _providers
    if _providers is not None:
        return _providers

    if os.environ.get("STRIH_CPU") or CPU_ONLY_MARKER.exists():
        _providers = ["CPUExecutionProvider"]
        return _providers

    import onnxruntime as ort

    # onnxruntime-gpu >= 1.21 umí načíst CUDA/cuDNN knihovny z pip balíčků nvidia-*,
    # takže není potřeba mít CUDA Toolkit nainstalovaný systémově.
    if hasattr(ort, "preload_dlls"):
        try:
            ort.preload_dlls()
        except Exception as exc:  # noqa: BLE001 - jen informativní
            log.debug("preload_dlls selhalo: %s", exc)

    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        _providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    else:
        _providers = ["CPUExecutionProvider"]
    return _providers


def uses_gpu() -> bool:
    return "CUDAExecutionProvider" in get_providers()


def device_label() -> str:
    return "GPU (NVIDIA CUDA)" if uses_gpu() else "CPU"


def _disable_gpu(reason: str, remember: bool) -> None:
    global _providers, gpu_fallback_reason
    log.warning("%s Přepínám na CPU.", reason)
    _providers = ["CPUExecutionProvider"]
    gpu_fallback_reason = reason
    if remember:
        try:
            CPU_ONLY_MARKER.write_text(reason + "\n", encoding="utf-8")
        except OSError:
            pass


def _download_model(model_name: str) -> None:
    """Stáhne model předem, aby se stahování nepočítalo do limitu pro načtení na GPU."""
    from rembg.sessions import sessions_class

    for cls in sessions_class:
        if cls.name() == model_name:
            cls.download_models()
            return


def _load_on_gpu(model_name: str, timeout: float):
    """Načte model na GPU a udělá zkušební výpočet. Vrací session, nebo None při selhání/timeoutu."""
    from rembg import new_session

    result: dict[str, object] = {}

    def worker():
        try:
            session = new_session(model_name, providers=[CUDA_PROVIDER, "CPUExecutionProvider"])
            if "CUDAExecutionProvider" not in session.inner_session.get_providers():
                # onnxruntime při chybějících CUDA knihovnách často jen tiše přejde na CPU
                result["error"] = "CUDA není funkční (chybí knihovny nebo ovladač?)."
                return
            session.predict(Image.new("RGB", (64, 64)))  # první výpočet = kompilace jader
            result["session"] = session
        except Exception as exc:  # noqa: BLE001
            log.debug("Načtení na GPU selhalo", exc_info=True)
            result["error"] = f"Model se nepodařilo spustit na GPU ({exc})."

    # daemon: když se GPU zasekne, vlákno nebrání ukončení aplikace
    thread = threading.Thread(target=worker, name=f"gpu-load-{model_name}", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        _disable_gpu(
            f"Načtení modelu na GPU trvalo déle než {timeout:.0f} s (ovladač nejspíš kompiluje "
            "CUDA jádra pro tuto kartu). Aplikace teď běží na CPU.",
            remember=True,
        )
        return None
    if "error" in result:
        _disable_gpu(str(result["error"]), remember=False)
        return None
    return result["session"]


def get_session(model_name: str):
    """Načte model jednou a dál ho vrací z cache. Když GPU selže nebo se zasekne, přepne na CPU."""
    if model_name not in MODELS:
        raise ValueError(f"Neznámý model: {model_name}")

    with _session_lock:
        if model_name in _sessions:
            return _sessions[model_name]

        from rembg import new_session

        session = None
        if uses_gpu():
            _download_model(model_name)
            session = _load_on_gpu(model_name, GPU_LOAD_TIMEOUT)
        if session is None:
            session = new_session(model_name, providers=["CPUExecutionProvider"])

        _sessions[model_name] = session
        return session


# ---------------------------------------------------------------------------
# Načtení a úprava obrázků
# ---------------------------------------------------------------------------


def load_image(path: str | Path) -> Image.Image:
    """Načte a ověří obrázek. Vyhazuje ImageError se srozumitelnou hláškou."""
    path = Path(path)
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImageError(
            f"nepodporovaný formát „{path.suffix or 'bez přípony'}“ (povoleno: JPG, PNG, WEBP)"
        )
    try:
        with Image.open(path) as img:
            if img.format not in ALLOWED_FORMATS:
                raise ImageError(
                    f"soubor není JPG/PNG/WEBP (rozpoznáno jako {img.format or 'neznámý formát'})"
                )
            img.load()  # vynutí dekódování -> odhalí poškozená/useknutá data
            img = ImageOps.exif_transpose(img)  # otočení podle EXIF (fotky z mobilu)
    except ImageError:
        raise
    except Image.DecompressionBombError:
        raise ImageError("obrázek je extrémně velký (podezření na decompression bomb)") from None
    except UnidentifiedImageError:
        raise ImageError("soubor není platný obrázek nebo je poškozený") from None
    except (OSError, SyntaxError, ValueError) as exc:
        raise ImageError(f"soubor je poškozený nebo neúplný ({exc})") from None

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
    return img


def limit_size(img: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    """Zmenší obrázek tak, aby delší strana měla nejvýš max_side px (poměr stran zachován)."""
    if max(img.size) <= max_side:
        return img
    img = img.copy()
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img


def checkerboard(size: tuple[int, int], square: int = 16) -> Image.Image:
    """Šachovnice (světle/tmavě šedá) pro zobrazení průhlednosti."""
    w, h = size
    tile = Image.new("RGB", (square * 2, square * 2), (255, 255, 255))
    tile.paste((204, 204, 204), (square, 0, square * 2, square))
    tile.paste((204, 204, 204), (0, square, square, square * 2))
    board = Image.new("RGB", size)
    for y in range(0, h, square * 2):
        for x in range(0, w, square * 2):
            board.paste(tile, (x, y))
    return board


def preview_on_checkerboard(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    board = checkerboard(rgba.size).convert("RGBA")
    return Image.alpha_composite(board, rgba).convert("RGB")


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Převede barvu z ColorPickeru (#rrggbb, #rgb nebo rgba(...)) na RGB tuple."""
    color = (color or "").strip()
    if color.startswith("rgb"):
        parts = color[color.index("(") + 1 : color.rindex(")")].split(",")
        return tuple(int(round(float(p))) for p in parts[:3])  # type: ignore[return-value]
    color = color.lstrip("#")
    if len(color) in (3, 4):
        color = "".join(c * 2 for c in color[:3])
    if len(color) < 6:
        raise ValueError(f"Neplatná barva: {color!r}")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def apply_background(img: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Nahradí průhledné pozadí plnou barvou."""
    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (*color, 255))
    return Image.alpha_composite(bg, rgba).convert("RGB")


# ---------------------------------------------------------------------------
# Zpracování
# ---------------------------------------------------------------------------


def remove_background(img: Image.Image, model_name: str, alpha_matting: bool) -> Image.Image:
    from rembg import remove

    session = get_session(model_name)
    kwargs = {}
    if alpha_matting:
        kwargs = dict(
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
    result = remove(img, session=session, **kwargs)
    return result.convert("RGBA")


@dataclass
class Result:
    name: str  # název výstupního souboru (…_bez_pozadi.png)
    original: Image.Image
    output: Image.Image  # RGBA, nebo RGB pokud bylo pozadí nahrazeno barvou
    resized_from: tuple[int, int] | None = None


def process_file(
    path: str | Path,
    model_name: str,
    alpha_matting: bool,
    bg_color: tuple[int, int, int] | None = None,
) -> Result:
    path = Path(path)
    img = load_image(path)
    orig_size = img.size
    img = limit_size(img)
    output = remove_background(img, model_name, alpha_matting)
    if bg_color is not None:
        output = apply_background(output, bg_color)
    return Result(
        name=f"{path.stem}_bez_pozadi.png",
        original=img,
        output=output,
        resized_from=orig_size if img.size != orig_size else None,
    )


def unique_names(names: list[str]) -> list[str]:
    """Zajistí unikátní názvy souborů (obrazek.png, obrazek_2.png, …)."""
    used: set[str] = set()
    out = []
    for name in names:
        stem, ext = Path(name).stem, Path(name).suffix
        candidate, i = name, 2
        while candidate.lower() in used:
            candidate, i = f"{stem}_{i}{ext}", i + 1
        used.add(candidate.lower())
        out.append(candidate)
    return out


def save_outputs(results: list[Result], out_dir: Path) -> Path:
    """Uloží výsledky jako PNG; při více obrázcích vrátí cestu k ZIP, jinak k PNG."""
    out_dir.mkdir(parents=True, exist_ok=True)
    names = unique_names([r.name for r in results])
    paths = []
    for result, name in zip(results, names):
        p = out_dir / name
        result.output.save(p, format="PNG", optimize=True)
        paths.append(p)

    if len(paths) == 1:
        return paths[0]

    zip_path = out_dir / "bez_pozadi.zip"
    # PNG už je komprimované, ZIP_STORED je rychlejší a velikost skoro stejná
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for p in paths:
            zf.write(p, arcname=p.name)
    return zip_path
