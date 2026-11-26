@echo off
setlocal
echo ============================================
echo  Building PSA to SF1 Extractor (.exe)
echo ============================================

if not exist .venv (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller --noconfirm --onefile --windowed ^
    --name "PSA_SF1_Extractor" ^
    --collect-all rapidocr_onnxruntime ^
    --collect-all pypdfium2 ^
    app.py

echo.
echo Standalone executable is at: dist\PSA_SF1_Extractor.exe

if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    echo Building Windows Setup Installer...
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
    echo Installer is at: dist\PSA_SF1_Extractor_Setup.exe
) else (
    echo Note: Install Inno Setup 6 to also build dist\PSA_SF1_Extractor_Setup.exe from installer.iss
)
pause

