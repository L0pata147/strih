# ✂️ Střih – odstranění pozadí z obrázků postav

Lokální aplikace pro Windows, která odstraní pozadí z obrázků postav pomocí knihovny
[rembg](https://github.com/danielgatis/rembg). Ovládá se v prohlížeči (Gradio UI na
`http://127.0.0.1:7860`), ale vše běží jen na tvém PC – nic se nikam neposílá.

## Spuštění

1. Nainstaluj [Python 3.11](https://www.python.org/downloads/) (zaškrtni *Add python.exe to PATH*).
2. Dvakrát klikni na **`start.bat`**.
   - **První spuštění** vytvoří virtuální prostředí `.venv`, nainstaluje závislosti a spustí aplikaci.
     Pokud máš NVIDIA kartu (najde `nvidia-smi`), nainstaluje se `onnxruntime-gpu` včetně CUDA
     knihoven – stahuje se cca 2–3 GB. Bez NVIDIA karty se použije CPU verze.
   - **Další spuštění** už jen otevřou aplikaci.
3. Aplikace se sama otevře v prohlížeči. Ukončíš ji zavřením okna konzole.

Modely se stahují automaticky při prvním použití do `%USERPROFILE%\.u2net`
(isnet-anime a isnet-general-use ≈ 170 MB, birefnet-portrait ≈ 900 MB).

## Použití

1. Přetáhni jeden nebo více obrázků (JPG, PNG, WEBP).
2. Vyber model:
   | Model | Kdy použít |
   |---|---|
   | **isnet-anime** (výchozí) | anime, manga, kreslené postavy, ilustrace |
   | **birefnet-portrait** | fotky lidí, portréty, cosplay (pomalejší) |
   | **isnet-general-use** | vše ostatní – figurky, 3D rendery, zvířata, předměty |
3. Volitelně zapni **Alpha matting** (jemnější okraje vlasů, ale výrazně pomalejší)
   nebo **Nahradit pozadí barvou**.
4. Klikni na **Odstranit pozadí**. Vedle originálu uvidíš výsledek na šachovnici
   a stáhneš PNG s průhledností (u více obrázků ZIP).

Obrázky s delší stranou nad 2048 px se před zpracováním zmenší.

## Řešení problémů

- **Instalace se nepovedla / chci přeinstalovat:** smaž složku `.venv` a spusť `start.bat` znovu.
- **Jiný port:** `start.bat --port 7861`; bez otevírání prohlížeče: `start.bat --no-browser`.
- **GPU se nepoužije:** v hlavičce aplikace je vidět, zda běží na GPU nebo CPU. Pokud se model na GPU
  nepodaří spustit, aplikace automaticky přepne na CPU. Pomáhá aktualizovat ovladač NVIDIA.

## Pro vývojáře

```bat
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest
```

Struktura: `app.py` (UI), `processing.py` (zpracování obrázků, cache modelů, detekce GPU),
`install_deps.py` (instalace podle GPU), `start.bat` (spouštěč).
