@echo off
REM AI Trading Agent - Diagram Generation Script (Windows)
REM This script converts Mermaid diagrams to SVG format

echo 🎨 AI Trading Agent - Diagram Generation
echo ========================================

REM Check if mmdc (mermaid-cli) is installed
where mmdc >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Error: mermaid-cli (mmdc) is not installed
    echo 📦 Install it with: npm install -g @mermaid-js/mermaid-cli
    exit /b 1
)

REM Create output directory
if not exist "assets\images\diagrams" mkdir "assets\images\diagrams"

echo 📁 Created output directory

REM Convert system architecture diagram to SVG
echo 🔧 Converting system architecture diagram...
mmdc -i assets\diagrams\system-architecture.mmd -o assets\images\diagrams\system-architecture.svg -p assets\puppeteer-config.json

REM Convert workflow diagram to SVG
echo 🔄 Converting workflow diagram...
mmdc -i assets\diagrams\workflow-flow.mmd -o assets\images\diagrams\workflow-flow.svg -p assets\puppeteer-config.json

echo ✅ All diagrams generated successfully!
echo.
echo 📂 Generated files in: assets\images\diagrams\
echo    - system-architecture.svg
echo    - workflow-flow.svg

pause 