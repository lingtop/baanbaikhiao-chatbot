# เปิดระบบทั้งหมด 3 บริการ แต่ละตัวในหน้าต่าง PowerShell ของตัวเอง
#   RAG (LightRAG)   http://127.0.0.1:9621  (embedding bge-m3 ในเครื่อง)
#   Guard Service    http://127.0.0.1:8001
#   Chat API + เว็บ   http://localhost:8000
# ใช้งาน:  .\start.ps1      (ครั้งแรกต้อง index คลังความรู้ก่อน: cd rag; uv run python -m scripts.index_kb)

$root = $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
# ใช้ python -m uvicorn แทน uvicorn.exe เพราะ Windows Smart App Control อาจบล็อกไฟล์ .exe ใน .venv

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\rag'; `$host.UI.RawUI.WindowTitle='RAG :9621'; uv run python -m uvicorn main:app --host 127.0.0.1 --port 9621"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; `$host.UI.RawUI.WindowTitle='Guard :8001'; uv run python -m uvicorn guard.main:app --host 127.0.0.1 --port 8001"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; `$host.UI.RawUI.WindowTitle='Chat API :8000'; uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

Write-Host "กำลังเปิด 3 บริการ... รอประมาณ 10-20 วินาทีแล้วเปิด http://localhost:8000"
Start-Sleep -Seconds 12
Start-Process "http://localhost:8000"
