# PSA Birth Certificate to SF1 Excel Extractor

Windows desktop application that reads multiple Philippine Statistics Authority (PSA) Birth Certificate scans (`.jpg` or `.pdf`, 2007 or current format only), cleans them with OpenCV, extracts text via offline OCR, and maps the extracted fields into a clean DepEd SF1-style `.xlsx` file.

## Features
- **Multi-file Upload (`[Upload]`)**: Select multiple `.jpg`, `.jpeg`, or `.pdf` PSA Birth Certificate files at once.
- **OpenCV Image Cleaning**: Grayscale conversion, resolution upscaling, denoising, automatic deskewing, and CLAHE contrast enhancement.
- **Offline OCR**: Uses `rapidocr-onnxruntime` (works offline with no external Tesseract installation required; falls back to `pytesseract` if configured).
- **Strict 5-Field Extraction**: Extracts only:
  1. **Name** (`LAST, FIRST MIDDLE`)
  2. **Birthdate** (`MM/DD/YYYY`)
  3. **Sex** (`M` / `F`)
  4. **Father's Name** (`LAST, FIRST MIDDLE`)
  5. **Mother's Maiden Name** (`LAST, FIRST MIDDLE`)
- **SF1 Excel Mapping (`[Export]`)**: Maps those 5 fields into standard DepEd SF1 columns and leaves **LRN** and all other unextracted fields blank.
- **Post-Export Reminder**: Displays `"Export Successful! Please check for errors in the Excel file before submitting as SF1."` after exporting.

## Running on Windows (from source)
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Building a Standalone Windows `.exe`
Double-click `build_windows.bat` on a Windows machine with Python 3.10+ installed. It will produce:
`dist\PSA_SF1_Extractor.exe`

## Running Tests
```bash
pytest -v
```

