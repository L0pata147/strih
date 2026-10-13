"""Střih – lokální odstranění pozadí z obrázků postav (Gradio UI)."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # nic neodesílat ven

import gradio as gr  # noqa: E402
from PIL import Image  # noqa: E402

import processing as proc  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("strih")

APP_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("STRIH_OUTPUT_DIR") or APP_DIR / "vystupy")

MODEL_UI = {  # emoji + krátký název do dropdownu, velikost pro hlášku o stahování
    "isnet-anime": ("🎨 Anime a kreslené postavy", "170 MB"),
    "birefnet-portrait": ("🧑 Lidé z fotek (portrét)", "900 MB"),
    "isnet-general-use": ("🧩 Obecný – cokoliv jiného", "170 MB"),
}
BG_TRANSPARENT, BG_COLOR = "Průhledné", "Barva"
PREVIEW_CHOICES = [("Šachovnice", "checker"), ("Bílá", "white"), ("Černá", "black"), ("Šedá", "gray")]
SWATCHES = [("⬜ Bílá", "#ffffff"), ("⬛ Černá", "#000000"), ("🟩 Green screen", "#00b140")]

STATUS_IDLE = (
    "<div class='status-card idle'><b>Nahraj obrázky</b> vlevo a klikni na <b>Odstranit pozadí</b> "
    "<span class='kbd'>Ctrl</span>+<span class='kbd'>Enter</span></div>"
)

# Výchozí nastavení (ukládá se v prohlížeči, aby si ho aplikace pamatovala)
DEFAULTS = {
    "model": proc.DEFAULT_MODEL,
    "alpha": False,
    "erode": 10,
    "bg_mode": BG_TRANSPARENT,
    "bg_color": "#ffffff",
    "crop": False,
    "padding": 5,
    "smooth": False,
    "export_mask": False,
    "preview_bg": "checker",
}

CSS = """
.gradio-container { max-width: 1320px !important; margin: 0 auto !important; }
#hero { padding: 18px 22px; border-radius: 18px; margin-bottom: 4px;
  background: linear-gradient(120deg, rgba(139,92,246,.18), rgba(236,72,153,.14) 55%, rgba(249,115,22,.12)); }
#hero h1 { margin: 0; font-size: 1.9rem; line-height: 1.2; font-weight: 800; letter-spacing: -.02em; }
#hero h1 .grad { background: linear-gradient(90deg,#8b5cf6,#ec4899,#f97316);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
#hero p { margin: 6px 0 10px; opacity: .8; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px;
  font-size: .82rem; font-weight: 600; border: 1px solid var(--border-color-primary);
  background: var(--background-fill-primary); }
.badge.gpu { color: #16a34a; border-color: rgba(22,163,74,.45); }
.badge.cpu { color: #d97706; border-color: rgba(217,119,6,.45); }
.step-title { margin: 4px 0 -4px !important; font-weight: 700; font-size: .95rem; opacity: .85; }
.step-title .num { display: inline-flex; width: 22px; height: 22px; border-radius: 50%; margin-right: 6px;
  align-items: center; justify-content: center; font-size: .8rem; color: white;
  background: linear-gradient(135deg,#8b5cf6,#ec4899); }
#model-hint { font-size: .88rem; opacity: .85; padding: 0 4px; }
.swatches button { min-width: 0 !important; }
#run-btn { font-size: 1.1rem !important; font-weight: 700 !important; min-height: 52px; }
.status-card { padding: 12px 16px; border-radius: 14px; border: 1px solid var(--border-color-primary);
  background: var(--background-fill-secondary); }
.status-card.ok { border-color: rgba(22,163,74,.5); }
.status-card.err { border-color: rgba(220,38,38,.5); }
.status-card.warn { border-color: rgba(217,119,6,.55); }
.status-card table { margin-top: 8px; font-size: .88rem; width: 100%; border-collapse: collapse; border: none !important; }
.status-card td, .status-card th { padding: 4px 12px 4px 0 !important; text-align: left;
  border: none !important; border-bottom: 1px solid var(--border-color-primary) !important; background: none !important; }
.status-card th { font-weight: 600; opacity: .7; }
.status-card tr { border: none !important; }
/* ImageSlider má výchozí silný 3px rámeček */
#compare { border-width: 1px !important; border-color: var(--border-color-primary) !important; }
.status-card ul { margin: 6px 0 0; }
.kbd { display: inline-block; padding: 0 6px; border-radius: 6px; font-size: .8em;
  border: 1px solid var(--border-color-primary); background: var(--background-fill-primary); }
.hint { font-size: .85rem; opacity: .75; }
/* pozadí náhledů průhledných výsledků (přepínač nad porovnáním) */
:root { --pv-bg: repeating-conic-gradient(#d4d4d4 0% 25%, #ffffff 0% 50%) 50% / 20px 20px; }
html[data-preview-bg="white"] { --pv-bg: #ffffff; }
html[data-preview-bg="black"] { --pv-bg: #000000; }
html[data-preview-bg="gray"] { --pv-bg: #808080; }
#results img { background: var(--pv-bg) !important; }
/* kompaktní mřížka náhledů místo dvou obřích dlaždic */
#results .grid-wrap { height: auto !important; min-height: 0 !important; max-height: 420px; }
#results .grid-container { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)) !important; }
#results .thumbnail-item { aspect-ratio: 1 / 1; height: auto !important; }
#results .thumbnail-item.selected { box-shadow: 0 0 0 3px #8b5cf6 !important; }
footer { opacity: .6; }
"""

HEAD = """
<script>
// Ctrl+Enter spustí zpracování. Zachytává se dřív než u prvků (capture), jinak by
// Enter zároveň přepnul zaměřený checkbox.
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const b = document.querySelector('#run-btn');
    if (b) { e.preventDefault(); e.stopPropagation(); b.click(); }
  }
}, true);
</script>
"""

THEME = gr.themes.Soft(
    primary_hue="violet",
    secondary_hue="pink",
    neutral_hue="slate",
    radius_size="lg",
    # systémová písma -> nic se nestahuje z internetu
    font=["Segoe UI", "system-ui", "-apple-system", "Roboto", "sans-serif"],
    font_mono=["Consolas", "ui-monospace", "monospace"],
)


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------


def header_html() -> str:
    gpu = proc.uses_gpu()
    device = (
        "<span class='badge gpu'>⚡ GPU (NVIDIA CUDA)</span>"
        if gpu
        else "<span class='badge cpu'>🖥️ CPU</span>"
    )
    return f"""
<div id="hero">
  <h1>✂️ <span class="grad">Střih</span> – odstranění pozadí z postav</h1>
  <p>Nahraj obrázky, vyber model a stáhni výřez s průhledným pozadím.</p>
  <div class="badges">
    {device}
    <span class="badge">🔒 100 % lokálně</span>
    <span class="badge">🖼️ JPG · PNG · WEBP</span>
    <span class="badge">📐 max {proc.MAX_SIDE} px</span>
  </div>
</div>"""


def model_hint(model_name: str) -> str:
    hint = proc.MODELS[model_name][1]
    if not proc.model_is_downloaded(model_name):
        hint += f" <i>Při prvním použití se stáhne (~{MODEL_UI[model_name][1]}).</i>"
    return f"💡 {hint}"


def file_paths(files) -> list[str]:
    return [f if isinstance(f, str) else f.name for f in files or []]


def slider_value(item: dict, preview_bg: str):
    original = Image.open(item["original"])
    output = Image.open(item["output"])
    return proc.preview_on(original, preview_bg), proc.preview_on(output, preview_bg)


def open_folder(path: str | None) -> None:
    if not path:
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        gr.Warning(f"Složku se nepodařilo otevřít: {exc}")


# ---------------------------------------------------------------------------
# Události UI
# ---------------------------------------------------------------------------


def on_upload(files):
    """Po nahrání hned ukáže náhledy a zkontroluje soubory."""
    paths = file_paths(files)
    if not paths:
        return gr.update(value=[], label="Výsledky"), None, STATUS_IDLE
    thumbs, bad = [], []
    for p in paths:
        try:
            img = proc.load_image(p)
            img.thumbnail((512, 512))
            thumbs.append((img, Path(p).name))
        except proc.ImageError as exc:
            bad.append(f"<li>⚠️ <b>{Path(p).name}</b>: {exc}</li>")
    msg = f"<b>{len(thumbs)} {plural(len(thumbs))} připraveno.</b> Klikni na <b>Odstranit pozadí</b>."
    if bad:
        msg += f"<ul>{''.join(bad)}</ul>Tyto soubory se přeskočí."
    css = "err" if bad and not thumbs else "idle"
    return gr.update(value=thumbs, label="Nahrané obrázky"), None, f"<div class='status-card {css}'>{msg}</div>"


def plural(n: int) -> str:
    return "obrázek" if n == 1 else "obrázky" if 2 <= n <= 4 else "obrázků"


def run(files, model_name, alpha, erode, bg_mode, bg_color, crop, padding, smooth, export_mask,
        preview_bg, progress=gr.Progress()):
    paths = file_paths(files)
    if not paths:
        raise gr.Error("Nejdřív nahraj alespoň jeden obrázek.")
    try:
        color = proc.hex_to_rgb(bg_color) if bg_mode == BG_COLOR else None
    except ValueError:
        raise gr.Error(f"Neplatná barva pozadí: {bg_color}") from None
    opts = proc.Options(
        alpha_matting=alpha, matting_erode=int(erode), smooth_mask=smooth, crop=crop,
        crop_padding=int(padding), bg_color=color, export_mask=export_mask,
    )

    if not proc.model_is_downloaded(model_name):
        progress(0, desc=f"Stahuji model {model_name} (~{MODEL_UI[model_name][1]}, jen poprvé)…")
    elif proc.uses_gpu() and model_name not in proc._sessions:
        progress(0, desc=f"Načítám model {model_name} na GPU (poprvé to může trvat až minutu)…")
    else:
        progress(0, desc=f"Načítám model {model_name}…")
    try:
        proc.get_session(model_name)
    except Exception as exc:  # noqa: BLE001
        log.exception("Načtení modelu selhalo")
        raise gr.Error(
            f"Model {model_name} se nepodařilo načíst: {exc}. "
            "Při prvním použití se model stahuje z internetu – zkontroluj připojení."
        ) from None
    if proc.gpu_fallback_reason:
        gr.Warning(proc.gpu_fallback_reason, title="GPU nepoužito", duration=None)
        proc.gpu_fallback_reason = None

    results: list[proc.Result] = []
    errors: list[str] = []
    started = time.perf_counter()
    for i, path in enumerate(paths):
        name = Path(path).name
        progress(i / len(paths), desc=f"Zpracovávám {name} ({i + 1}/{len(paths)})")
        try:
            results.append(proc.process_file(path, model_name, opts))
        except proc.ImageError as exc:
            errors.append(f"<b>{name}</b>: {exc}")
        except Exception as exc:  # noqa: BLE001 - nečekaná chyba nesmí shodit celou dávku
            log.exception("Chyba při zpracování %s", name)
            errors.append(f"<b>{name}</b>: neočekávaná chyba ({exc})")

    if not results:
        status = "<div class='status-card err'><b>❌ Nic se nezpracovalo</b><ul>" + "".join(
            f"<li>{e}</li>" for e in errors) + "</ul></div>"
        return [], gr.update(value=[], label="Výsledky"), None, None, status, header_html(), None, \
            gr.update(visible=False)

    progress(1, desc="Ukládám…")
    out_dir = OUTPUT_ROOT / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    saved = proc.save_outputs(results, out_dir)
    preview_dir = Path(tempfile.mkdtemp(prefix="strih_nahled_"))
    items = []
    for i, (r, img_path) in enumerate(zip(results, saved.images)):
        orig_path = preview_dir / f"{i}.png"
        r.original.save(orig_path)
        items.append({"original": str(orig_path), "output": str(img_path), "name": img_path.name})

    elapsed = time.perf_counter() - started
    try:
        shown_dir = out_dir.relative_to(APP_DIR)
    except ValueError:
        shown_dir = out_dir
    rows = "".join(
        f"<tr><td>{p.name}</td><td>{r.output.width}×{r.output.height}</td><td>{r.seconds:.1f} s</td>"
        f"<td class='hint'>{'zmenšeno z %d×%d' % r.resized_from if r.resized_from else ''}</td></tr>"
        for r, p in zip(results, saved.images)
    )
    status = (
        f"<div class='status-card {'warn' if errors else 'ok'}'>"
        f"<b>✅ Hotovo: {len(results)}/{len(paths)} {plural(len(paths))} za {elapsed:.1f} s</b> "
        f"<span class='hint'>({proc.device_label()} · uloženo do <code>{shown_dir}</code>)</span>"
        f"<table><tr><th>Soubor</th><th>Rozměr</th><th>Čas</th><th></th></tr>{rows}</table>"
    )
    if errors:
        status += "<b>Přeskočeno:</b><ul>" + "".join(f"<li>⚠️ {e}</li>" for e in errors) + "</ul>"
    status += "</div>"

    gallery = gr.update(value=[(it["output"], it["name"]) for it in items],
                        label="Výsledky – klikni na obrázek pro porovnání", selected_index=None)
    return (
        items, gallery, slider_value(items[0], preview_bg),
        [str(p) for p in saved.downloads], status, header_html(), str(out_dir), gr.update(visible=True),
    )


def on_select(items, preview_bg, evt: gr.SelectData):
    if not items or evt.index is None or evt.index >= len(items):
        return gr.skip(), 0
    return slider_value(items[evt.index], preview_bg), evt.index


def on_preview_bg(items, selected, preview_bg):
    if not items:
        return gr.skip()
    return slider_value(items[min(selected or 0, len(items) - 1)], preview_bg)


# ---------------------------------------------------------------------------
# Rozložení
# ---------------------------------------------------------------------------


def step(num: int, title: str) -> None:
    gr.HTML(f"<div class='step-title'><span class='num'>{num}</span>{title}</div>")


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Střih – odstranění pozadí") as demo:
        items_state = gr.State([])
        selected_state = gr.State(0)
        out_dir_state = gr.State(None)
        saved_settings = gr.BrowserState(DEFAULTS, storage_key="strih-nastaveni")

        header = gr.HTML(header_html())

        with gr.Row(equal_height=False):
            # ---------------- levý panel: nastavení ----------------
            with gr.Column(scale=4, min_width=330):
                step(1, "Obrázky")
                files = gr.File(
                    label="Klikni nebo přetáhni sem (i více najednou)",
                    file_count="multiple",
                    file_types=sorted(proc.ALLOWED_EXTENSIONS),
                    type="filepath",
                    height=150,
                )

                step(2, "Model")
                with gr.Group():
                    model = gr.Dropdown(
                        show_label=False,
                        choices=[(MODEL_UI[k][0], k) for k in proc.MODELS],
                        value=proc.DEFAULT_MODEL,
                    )
                    hint = gr.HTML(model_hint(proc.DEFAULT_MODEL), elem_id="model-hint", padding=True)

                step(3, "Výstup")
                with gr.Group():
                    alpha = gr.Checkbox(
                        label="Alpha matting – jemnější okraje (vlasy, chlupy)",
                        info="⏳ Výrazně pomalejší. První použití navíc trvá déle (příprava knihovny).",
                    )
                    erode = gr.Slider(
                        1, 40, value=10, step=1, visible=False,
                        label="Síla zjemnění okrajů",
                        info="Větší hodnota = širší pás okraje, který se dopočítává.",
                    )
                    bg_mode = gr.Radio(
                        [BG_TRANSPARENT, BG_COLOR], value=BG_TRANSPARENT, label="Pozadí výsledku",
                    )
                    with gr.Row(visible=False, elem_classes="swatches") as color_row:
                        bg_color = gr.ColorPicker(value="#ffffff", show_label=False, scale=0, min_width=60)
                        swatch_btns = [gr.Button(n, size="sm", scale=1, min_width=0) for n, _ in SWATCHES]

                with gr.Accordion("⚙️ Pokročilé", open=False):
                    crop = gr.Checkbox(label="Oříznout na postavu",
                                       info="Odstraní prázdné okolí, výsledek je jen postava s okrajem.")
                    padding = gr.Slider(0, 30, value=5, step=1, label="Okraj kolem postavy (%)", visible=False)
                    smooth = gr.Checkbox(label="Vyhladit masku",
                                         info="Odstraní drobné zbytky a zubaté hrany (rychlé).")
                    export_mask = gr.Checkbox(label="Uložit i masku",
                                              info="Černobílá maska navíc (pro úpravy v grafickém editoru).")

                with gr.Row():
                    run_btn = gr.Button("✂️ Odstranit pozadí", variant="primary", size="lg",
                                        elem_id="run-btn", scale=3)
                    clear_btn = gr.Button("🗑️ Vymazat", variant="secondary", size="lg", scale=1)
                gr.HTML("<div class='hint'>Tip: <span class='kbd'>Ctrl</span>+<span class='kbd'>Enter</span> "
                        "spustí zpracování. Nastavení si aplikace pamatuje.</div>")

            # ---------------- pravý panel: výsledky ----------------
            with gr.Column(scale=7):
                status = gr.HTML(STATUS_IDLE)
                with gr.Group():
                    preview_bg = gr.Radio(PREVIEW_CHOICES, value="checker", label="Pozadí náhledu",
                                          info="Jen pro kontrolu okrajů – stažený soubor zůstává průhledný.")
                    slider = gr.ImageSlider(
                        label="Porovnání – posuň jezdcem (vlevo originál, vpravo výsledek)",
                        interactive=False, height=520, type="pil", format="png", elem_id="compare",
                    )
                gallery = gr.Gallery(
                    label="Výsledky", elem_id="results", columns=5, height="auto", object_fit="contain",
                    allow_preview=False, format="png",
                )
                downloads = gr.File(label="⬇️ Stáhnout (ZIP se vším + jednotlivé soubory)",
                                    file_count="multiple", interactive=False)
                open_btn = gr.Button("📂 Otevřít složku s výsledky", size="sm", visible=False)

        # ---------------- události ----------------
        model.change(model_hint, model, hint)
        alpha.change(lambda v: gr.update(visible=v), alpha, erode)
        crop.change(lambda v: gr.update(visible=v), crop, padding)
        bg_mode.change(lambda m: gr.update(visible=m == BG_COLOR), bg_mode, color_row)
        for btn, (_, hex_color) in zip(swatch_btns, SWATCHES):
            btn.click(lambda c=hex_color: c, None, bg_color)

        files.change(on_upload, files, [gallery, slider, status])
        run_event = gr.on(
            [run_btn.click],
            run,
            inputs=[files, model, alpha, erode, bg_mode, bg_color, crop, padding, smooth, export_mask, preview_bg],
            outputs=[items_state, gallery, slider, downloads, status, header, out_dir_state, open_btn],
            api_name="run",
            concurrency_limit=1,  # jeden model v paměti najednou, ať nedojde VRAM/RAM
        )
        run_event.then(lambda: 0, None, selected_state)
        gallery.select(on_select, [items_state, preview_bg], [slider, selected_state])
        preview_bg.change(
            on_preview_bg, [items_state, selected_state, preview_bg], slider,
            js="(items, sel, bg) => { document.documentElement.dataset.previewBg = bg; return [items, sel, bg]; }",
        )
        open_btn.click(open_folder, out_dir_state, None)
        clear_btn.click(
            lambda: (None, gr.update(value=[], label="Výsledky"), None, None, STATUS_IDLE, [], 0,
                     gr.update(visible=False)),
            None, [files, gallery, slider, downloads, status, items_state, selected_state, open_btn],
        )

        # zapamatování nastavení v prohlížeči
        settings = {"model": model, "alpha": alpha, "erode": erode, "bg_mode": bg_mode,
                    "bg_color": bg_color, "crop": crop, "padding": padding, "smooth": smooth,
                    "export_mask": export_mask, "preview_bg": preview_bg}
        keys, comps = list(settings), list(settings.values())

        def restore(saved):
            saved = {**DEFAULTS, **(saved or {})}
            if saved["model"] not in proc.MODELS:
                saved["model"] = proc.DEFAULT_MODEL
            return [saved[k] for k in keys] + [header_html()]

        demo.load(restore, saved_settings, comps + [header])
        gr.on([c.change for c in comps], lambda *v: dict(zip(keys, v)), comps, saved_settings)
    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Střih – odstranění pozadí")
    parser.add_argument("--port", type=int, default=None, help="port (výchozí 7860 nebo první volný)")
    parser.add_argument("--no-browser", action="store_true", help="neotevírat prohlížeč")
    parser.add_argument("--cpu", action="store_true", help="nepoužívat GPU")
    args = parser.parse_args()
    if args.cpu:
        os.environ["STRIH_CPU"] = "1"

    log.info("Výpočetní zařízení: %s", proc.device_label())
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    build_ui().queue().launch(
        server_name="127.0.0.1",
        server_port=args.port,
        inbrowser=not args.no_browser,
        theme=THEME,
        css=CSS,
        head=HEAD,
        allowed_paths=[str(OUTPUT_ROOT)],
    )


if __name__ == "__main__":
    main()
