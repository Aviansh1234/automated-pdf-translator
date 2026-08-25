# Automated PDF Translator

Translate scanned/image-based PDFs by converting pages to images, sending each page through Google Translate image translation via Selenium, and rebuilding a translated PDF.

Primary use case: quickly reading foreign-language PDFs for personal study. This project was initially created to read Japanese Olympiad in Informatics editorials in English.

This project supports:
- GUI mode (default): launch without CLI arguments
- CLI mode: provide input and options as command-line arguments

## Features
- Converts each PDF page to PNG using `pdf2image`
- Translates pages with Google Translate image workflow
- Rebuilds translated pages into a PDF
- Falls back to original page image when translation fails
- Multi-worker processing for faster translation

## Requirements
- Python 3.9+
- Google Chrome installed
- Internet connection
- Poppler (required by `pdf2image`)

## Installation

1. Clone the repository:

```powershell
git clone https://github.com/Aviansh1234/automated-pdf-translator.git
cd automated-pdf-translator
```

Alternatively, download the ZIP from GitHub and open a terminal in the project root.

2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

## Install Poppler (Windows)

`pdf2image` needs Poppler binaries (especially `pdftoppm`) available on your system.

### Option A: Manual download (recommended)
1. Download a Windows Poppler build from:
   - https://github.com/oschwartz10612/poppler-windows/releases
2. Extract the archive (for example to `C:\tools\poppler`).
3. Add the Poppler `bin` folder to your PATH:
   - Example path: `C:\tools\poppler\Library\bin`

Temporary PATH for current PowerShell session:

```powershell
$env:Path += ";C:\tools\poppler\Library\bin"
```

Permanent PATH (user scope):

```powershell
[Environment]::SetEnvironmentVariable(
  "Path",
  $env:Path + ";C:\tools\poppler\Library\bin",
  "User"
)
```

Restart terminal after setting permanent PATH.

### Option B: Using package managers
If you use a package manager, one of these common options can install Poppler:

```powershell
choco install poppler
```

or

```powershell
scoop install poppler
```

After install, verify:

```powershell
pdftoppm -h
```

If the command is not found, Poppler is not on PATH yet.

## Usage

### GUI mode (default)
Run without arguments:

```powershell
python .\automated_pdf_translator.py
```

Then in the UI:
- Add one or more PDF files
- Configure DPI, workers, source language (`auto` recommended), and target language
- Start translation

### CLI mode
Show help:

```powershell
python .\automated_pdf_translator.py --help
```

Example:

```powershell
python .\automated_pdf_translator.py \
  --input .\input.pdf \
  --output .\output_translated.pdf \
  --source auto \
  --target en \
  --dpi 200 \
  --workers 4 \
  --max-attempts 0
```

Arguments:
- `--input`, `-i`: input PDF path (required)
- `--output`, `-o`: output PDF path (default: `translated_output.pdf`)
- `--source`, `-s`: source language code (default: `auto`)
- `--target`, `-t`: target language code (default: `en`)
- `--dpi`: page render DPI (default: `200`)
- `--workers`: concurrent worker count (default: `4`)
- `--max-attempts`: retry attempts per page (`0` means unlimited)
- `--keep-temp`: keep temporary image folders

## Notes
- First run may take longer due to browser startup.
- Google Translate UI changes can affect Selenium selectors over time.
- Translation quality depends on source image quality and detected language.
- Output format note: the generated PDF is a PDF of images, not selectable/searchable text.

## Troubleshooting
- `PDFInfoNotInstalledError` or Poppler errors:
  - Ensure Poppler is installed and `pdftoppm` is on PATH.
- Selenium/Chrome issues:
  - Ensure Chrome is installed and up to date.
- Empty or unchanged translated images:
  - Retry with higher DPI (e.g. 300) and verify source language settings.

## License
This project is licensed under the MIT License. See LICENSE for details.
