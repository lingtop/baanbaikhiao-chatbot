"""สร้างภาพประกอบเอกสาร (แผนภาพ + ภาพ mockup) จากไฟล์ HTML ด้วย Edge แบบ headless

ใช้งาน:  uv run --no-project --with pillow python docs/report/build_images.py
ผลลัพธ์อยู่ใน docs/report/img/
"""

import subprocess
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SCALE = 2

# (ไฟล์ html, กว้าง, สูง) ต้องตรงกับขนาด body ใน html
PAGES = [("architecture.html", 1480, 1030), ("dataflow.html", 1100, 1190), ("mockups.html", 1340, 4820),
         ("chat_flow.html", 1500, 1440)]


def shot(name, w, h):
    out = IMG / name.replace(".html", ".png")
    subprocess.run([
        EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}", f"--window-size={w},{h}",
        "--virtual-time-budget=8000", f"--screenshot={out}", (HERE / name).as_uri(),
    ], check=True, capture_output=True)
    return out


def crop_screens(sheet):
    """mockups.html วางหน้าจอเว็บ 1280x760 เรียงลงมา 6 จอ ห่างกัน 40 px"""
    im = Image.open(sheet)
    for i in range(6):
        x = 30 * SCALE
        y = (30 + i * 800) * SCALE
        im.crop((x, y, x + 1280 * SCALE, y + 760 * SCALE)).save(IMG / f"mockup_{i + 1}.png")


def main():
    IMG.mkdir(exist_ok=True)
    for name, w, h in PAGES:
        path = shot(name, w, h)
        print("saved", path.name)
    crop_screens(IMG / "mockups.png")
    print("saved mockup_1..6.png")


if __name__ == "__main__":
    main()
