# ✂️ Střih – odstranění pozadí z obrázků postav

Lokální aplikace pro Windows, která odstraní pozadí z obrázků postav pomocí knihovny
[rembg](https://github.com/danielgatis/rembg). Ovládá se v prohlížeči (Gradio UI na
`http://127.0.0.1:7860`), ale vše běží jen na tvém PC – nic se nikam neposílá.

## Spuštění – přenosná verze (doporučeno, nic se neinstaluje)

1. Stáhni **[Strih-portable-win64.zip](https://github.com/L0pata147/strih/releases/download/portable/Strih-portable-win64.zip)**
   (obsahuje Python, všechny knihovny i výchozí model).
2. Rozbal ho kamkoli, třeba na plochu.
3. Dvakrát klikni na **`start.bat`** ve složce `Strih`. Aplikace se sama otevře v prohlížeči.
   Ukončíš ji zavřením černého okna.

Pokud máš NVIDIA kartu, při prvním spuštění se zeptá, jestli stáhnout GPU zrychlení
(jednorázově cca 2–3 GB). Když odpovíš ne, aplikace normálně běží na CPU.
Výchozí model isnet-anime je přibalený. Další modely se stáhnou samy při prvním použití
do složky `models` (isnet-general-use ≈ 170 MB, birefnet-portrait ≈ 900 MB).

Windows může při prvním spuštění zobrazit „Systém Windows ochránil váš počítač“, protože
soubor není podepsaný. Klikni na *Další informace* → *Přesto spustit*.

## Spuštění ze zdrojového kódu (pro vývojáře)

1. Nainstaluj [Python 3.11](https://www.python.org/downloads/) (zaškrtni *Add python.exe to PATH*).
2. Spusť **`start.bat`** v kořeni repozitáře. Při prvním spuštění vytvoří `.venv`, nainstaluje závislosti
   (s NVIDIA kartou i `onnxruntime-gpu` s CUDA knihovnami) a spustí aplikaci. Další spuštění už jen otevřou
   aplikaci. Modely se ukládají do `%USERPROFILE%\.rembg\models`.

## Použití

1. **Obrázky** – přetáhni jeden nebo více obrázků (JPG, PNG, WEBP). Hned uvidíš náhledy
   a upozornění na vadné soubory.
2. **Model**:
   | Model | Kdy použít |
   |---|---|
   | 🎨 **isnet-anime** (výchozí) | anime, manga, kreslené postavy, ilustrace |
   | 🧑 **birefnet-portrait** | fotky lidí, portréty, cosplay (pomalejší) |
   | 🧩 **isnet-general-use** | vše ostatní – figurky, 3D rendery, zvířata, předměty |
3. **Výstup** – volitelně *Alpha matting* (jemnější vlasy, pomalejší) a *Pozadí výsledku*:
   průhledné, nebo barva (předvolby bílá / černá / green screen nebo vlastní).
   V části **Pokročilé** je oříznutí na postavu s okrajem, vyhlazení masky a uložení černobílé masky.
4. Klikni na **Odstranit pozadí** (nebo <kbd>Ctrl</kbd>+<kbd>Enter</kbd>).

Výsledek porovnáš s originálem posuvníkem. Kliknutím na náhled ve výsledcích přepneš obrázek
a přepínačem *Pozadí náhledu* (šachovnice / bílá / černá / šedá) zkontroluješ okraje.
Stáhnout jde ZIP se vším i každý soubor zvlášť. Výsledky se navíc ukládají do složky
`vystupy` vedle aplikace (tlačítko *Otevřít složku s výsledky*). Nastavení si aplikace pamatuje.

Obrázky s delší stranou nad 2048 px se před zpracováním zmenší.

## Řešení problémů

- **Instalace se nepovedla / chci přeinstalovat:** u verze ze zdrojáků smaž složku `.venv`,
  u přenosné verze soubor `python\.strih_installed`, a spusť `start.bat` znovu.
- **Jiný port:** `start.bat --port 7861`; bez otevírání prohlížeče: `start.bat --no-browser`.
- **GPU se nepoužije / zasekává se:** v hlavičce aplikace je vidět, zda běží na GPU nebo CPU. Pokud se model
  na GPU nepodaří spustit nebo se do 60 s nenačte (u některých karet ovladač poprvé dlouho kompiluje
  CUDA jádra), aplikace přepne na CPU a zapamatuje si to v souboru `python\.strih_cpu_only`
  (u verze ze zdrojáků `.venv\.strih_cpu_only`). Smazáním souboru se GPU zkusí znovu.
  Pomáhá aktualizovat ovladač NVIDIA. Vynutit CPU jde přes `start.bat --cpu`.

## Pro vývojáře

```bat
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest
```

Struktura: `app.py` (UI), `processing.py` (zpracování obrázků, cache modelů, detekce GPU),
`install_deps.py` (instalace podle GPU), `start.bat` (spouštěč), `tools/build_portable.ps1`
(sestavení přenosné verze, spouští ho GitHub Actions při každém pushi).
