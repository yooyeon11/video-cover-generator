@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 打包视频封面生成器

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

echo === 安装依赖 ===
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo.
echo === PyInstaller 打包 ===
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "视频封面生成器" ^
  --icon "%CD%\app.ico" ^
  --collect-all tkinterdnd2 ^
  --distpath dist --workpath build --specpath build ^
  "视频封面生成器.pyw"
if errorlevel 1 goto fail

echo.
echo === 附带开源字体 ===
if not exist "dist\fonts" mkdir "dist\fonts"
copy /y "fonts\NotoSansSC-Regular.otf" "dist\fonts\" >nul
copy /y "fonts\OFL.txt" "dist\fonts\" >nul

echo.
echo 完成：dist\视频封面生成器.exe
echo 请把 dist\fonts 与 exe 放在同一目录，并自备 ffmpeg.exe / ffprobe.exe。
pause
exit /b 0

:fail
echo.
echo 打包失败，请检查上方错误信息。
pause
exit /b 1
