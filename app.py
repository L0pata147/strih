"""Střih – lokální odstranění pozadí z obrázků postav (Gradio UI)."""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # nic neodesílat ven

import gradio as gr  # noqa: E402

import processing as proc  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("strih")


def model_info(model_name: str) -> str:
    return f"💡 {proc.MODELS[model_name][1]}"


def run(files, model_name, alpha_matting, use_bg_color, bg_color, progress=gr.Progress()):
    if not files:
        raise gr.Error("Nejdřív nahraj alespoň jeden obrázek.")

    paths = [f if isinstance(f, str) else f.name for f in files]
    try:
        color = proc.hex_to_rgb(bg_color) if use_bg_color else None
    except ValueError:
        raise gr.Error(f"Neplatná barva pozadí: {bg_color}") from None

    progress(0, desc=f"Načítám model {model_name}…")
    try:
        proc.get_session(model_name)
    except Exception as exc:  # noqa: BLE001
        log.exception("Načtení modelu selhalo")
        raise gr.Error(
            f"Model {model_name} se nepodařilo načíst: {exc}. "
            "Při prvním použití se model stahuje z internetu – zkontroluj připojení."
        ) from None

    results: list[proc.Result] = []
    errors: list[str] = []
    notes: list[str] = []
    started = time.perf_counter()

    for i, path in enumerate(paths):
        name = Path(path).name
        progress(i / len(paths), desc=f"Zpracovávám {name} ({i + 1}/{len(paths)})")
        try:
            result = proc.process_file(path, model_name, alpha_matting, color)
        except proc.ImageError as exc:
            errors.append(f"**{name}**: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - nečekaná chyba nesmí shodit celou dávku
            log.exception("Chyba při zpracování %s", name)
            errors.append(f"**{name}**: neočekávaná chyba ({exc})")
            continue
        results.append(result)
        if result.resized_from:
            w, h = result.resized_from
            notes.append(f"{name}: zmenšeno z {w}×{h} na {result.original.width}×{result.original.height} px")

    for err in errors:
        gr.Warning(err.replace("**", ""), title="Upozornění")

    if not results:
        status = "### ❌ Nic se nezpracovalo\n" + "\n".join(f"- {e}" for e in errors)
        return [], [], None, status

    progress(1, desc="Ukládám…")
    out_dir = Path(tempfile.mkdtemp(prefix="strih_"))
    download = proc.save_outputs(results, out_dir)

    originals = [(r.original, r.name.replace("_bez_pozadi.png", "")) for r in results]
    previews = [
        (r.output if color else proc.preview_on_checkerboard(r.output), r.name) for r in results
    ]

    elapsed = time.perf_counter() - started
    kind = "ZIP" if download.suffix == ".zip" else "PNG"
    lines = [
        f"### ✅ Hotovo: {len(results)}/{len(paths)} obrázků za {elapsed:.1f} s "
        f"({proc.device_label()}) – stáhni {kind} níže"
    ]
    if notes:
        lines.append("ℹ️ " + "; ".join(notes))
    if errors:
        lines.append("**Chyby:**\n" + "\n".join(f"- ⚠️ {e}" for e in errors))
    return originals, previews, str(download), "\n\n".join(lines)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Střih – odstranění pozadí") as demo:
        gr.Markdown(
            "# ✂️ Střih – odstranění pozadí z obrázků postav\n"
            f"Běží lokálně na **{proc.device_label()}**. Podporované formáty: JPG, PNG, WEBP. "
            f"Obrázky delší než {proc.MAX_SIDE} px se před zpracováním zmenší."
        )
        with gr.Row():
            with gr.Column(scale=1, min_width=320):
                files = gr.File(
                    label="Obrázky (klikni nebo přetáhni, i více najednou)",
                    file_count="multiple",
                    file_types=sorted(proc.ALLOWED_EXTENSIONS),
                    type="filepath",
                )
                model = gr.Dropdown(
                    label="Model",
                    choices=[(label, key) for key, (label, _) in proc.MODELS.items()],
                    value=proc.DEFAULT_MODEL,
                )
                model_hint = gr.Markdown(model_info(proc.DEFAULT_MODEL))
                alpha = gr.Checkbox(
                    label="Alpha matting (jemnější okraje, vlasy)",
                    info="⏳ Výrazně pomalejší – zapni hlavně u vlasů a chlupů.",
                    value=False,
                )
                use_bg = gr.Checkbox(
                    label="Nahradit pozadí barvou",
                    info="Místo průhlednosti vyplní pozadí zvolenou barvou.",
                    value=False,
                )
                bg_color = gr.ColorPicker(label="Barva pozadí", value="#ffffff", visible=False)
                btn = gr.Button("✂️ Odstranit pozadí", variant="primary", size="lg")

            with gr.Column(scale=2):
                status = gr.Markdown("Nahraj obrázky a klikni na **Odstranit pozadí**.")
                with gr.Row(equal_height=True):
                    gallery_in = gr.Gallery(
                        label="Originál", columns=2, height=520, object_fit="contain", format="png"
                    )
                    gallery_out = gr.Gallery(
                        label="Výsledek", columns=2, height=520, object_fit="contain", format="png"
                    )
                download = gr.File(label="Stáhnout výsledek (PNG / ZIP)", interactive=False)

        model.change(model_info, model, model_hint)
        use_bg.change(lambda v: gr.update(visible=v), use_bg, bg_color)
        btn.click(
            run,
            inputs=[files, model, alpha, use_bg, bg_color],
            outputs=[gallery_in, gallery_out, download, status],
            concurrency_limit=1,  # jeden model v paměti najednou, ať nedojde VRAM/RAM
        )
    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Střih – odstranění pozadí")
    parser.add_argument("--port", type=int, default=None, help="port (výchozí 7860 nebo první volný)")
    parser.add_argument("--no-browser", action="store_true", help="neotevírat prohlížeč")
    args = parser.parse_args()

    log.info("Výpočetní zařízení: %s", proc.device_label())
    build_ui().queue().launch(
        server_name="127.0.0.1",
        server_port=args.port,
        inbrowser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
