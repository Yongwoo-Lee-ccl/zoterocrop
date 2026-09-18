"""Create a synthetic PDF; no user library documents are used in tests."""
from pathlib import Path
import sys
import pymupdf as fitz

target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
with fitz.open() as doc:
    for i in range(3):
        page = doc.new_page(width=400, height=500)
        if i < 2:
            page.insert_text((50+i*20, 80+i*20), f'Common crop - page {i+1}', fontsize=18)
            page.draw_rect(fitz.Rect(45+i*15, 120, 330-i*10, 350+i*40), color=(0.1,0.3,0.7), width=2)
        page.set_rotation(90)
    doc.save(target)
