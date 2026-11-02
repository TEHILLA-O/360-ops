$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\graph-service'; .\.venv\Scripts\python -m uvicorn app.main:app --port 8090"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"
