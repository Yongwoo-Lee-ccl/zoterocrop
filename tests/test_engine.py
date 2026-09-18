import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import pymupdf as fitz
from PIL import Image, ImageDraw
from io import BytesIO

SCRIPT = Path(__file__).resolve().parents[1] / 'plugin/engine/pdf_common_crop.py'

class CropTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root/'input.pdf'
        self.out = self.root/'output.pdf'

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, sizes=((400,500),(400,500)), boxes=((40,80,250,350),(80,40,320,400)), rotation=0, offset=False, encrypted=False):
        with fitz.open() as doc:
            for i, size in enumerate(sizes):
                p = doc.new_page(width=size[0], height=size[1])
                if boxes[i]:
                    p.draw_rect(fitz.Rect(boxes[i]), fill=(0,0,0), color=None)
                if offset:
                    p.set_cropbox(fitz.Rect(20,20,size[0]-20,size[1]-20))
                p.set_rotation(rotation)
            if encrypted:
                doc.save(self.src, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
            else:
                doc.save(self.src)

    def run_cli(self, *args, ok=True, env=None):
        p = subprocess.run([sys.executable,str(SCRIPT),str(self.src),str(self.out),'--json',*args], capture_output=True,text=True,env=env)
        self.assertEqual(p.returncode == 0, ok, p.stderr)
        return json.loads(p.stdout) if ok else p

    def assert_uniform(self):
        with fitz.open(self.out) as doc:
            boxes = [tuple(p.cropbox) for p in doc]
            self.assertTrue(all(b == boxes[0] for b in boxes))
            self.assertTrue(all(p.rotation == 0 for p in doc))

    def test_union_not_intersection_and_margin(self):
        self.fixture()
        r = self.run_cli('--margin','10pt')
        for a,b in zip(r['crop_box_pt'],[29.5,29.5,330.5,410.5]):
            self.assertAlmostEqual(a,b,places=2)
        self.assert_uniform()

    def test_blank_page(self):
        self.fixture(boxes=((40,80,250,350),None))
        r=self.run_cli()
        self.assertIsNone(r['pages'][1]['content_box_pt'])
        self.assert_uniform()

    def test_all_blank(self):
        self.fixture(boxes=(None,None))
        self.assertEqual(self.run_cli()['crop_box_pt'],[0,0,400,500])

    def test_rotations(self):
        for angle in (90,180,270):
            with self.subTest(angle=angle):
                self.fixture(rotation=angle)
                r=self.run_cli('--force')
                self.assert_uniform()
                self.assertGreater(r['output_size_pt'][0], 200)

    def test_existing_crop_offset(self):
        self.fixture(offset=True)
        r=self.run_cli('--margin','10')
        self.assertAlmostEqual(r['crop_box_pt'][0],29.5)
        self.assert_uniform()

    def test_compatible_mixed_sizes(self):
        self.fixture(sizes=((400,500),(450,550)))
        self.run_cli()
        self.assert_uniform()

    def test_incompatible_mixed_sizes(self):
        self.fixture(sizes=((400,500),(600,500)), boxes=((40,40,300,300),(450,40,550,300)))
        self.assertIn('incompatible',self.run_cli(ok=False).stderr)
        self.assertFalse(self.out.exists())

    def test_margin_clamped(self):
        self.fixture()
        self.assertEqual(self.run_cli('--margin','999')['crop_box_pt'],[0,0,400,500])

    def test_dry_run(self):
        self.fixture()
        self.run_cli('--dry-run')
        self.assertFalse(self.out.exists())

    def test_overwrite_and_same_file(self):
        self.fixture()
        self.run_cli()
        self.assertIn('exists',self.run_cli(ok=False).stderr)
        self.run_cli('--force')
        self.out=self.src
        self.assertIn('different',self.run_cli('--force',ok=False).stderr)

    def test_invalid_arguments(self):
        self.fixture()
        for args in [('--margin','-1'),('--margin','nan'),('--dpi','0'),('--threshold','256'),('--max-pixels','1')]:
            self.run_cli(*args,ok=False)

    def test_bad_input(self):
        self.run_cli(ok=False)
        self.src.write_text('not a PDF')
        self.run_cli(ok=False)

    def test_password(self):
        self.fixture(encrypted=True)
        self.run_cli(ok=False)
        self.run_cli('--password-env','TEST_PDF_PASS',env={**os.environ,'TEST_PDF_PASS':'secret'})
        with fitz.open(self.out) as doc:
            self.assertTrue(doc.needs_pass)
            self.assertTrue(doc.authenticate('secret'))

    def test_scan_annotation_and_text_preserved(self):
        im=Image.new('RGB',(400,500),'white')
        ImageDraw.Draw(im).rectangle((100,100,299,349),fill='black')
        stream=BytesIO(); im.save(stream,format='PNG')
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500)
            p.insert_image(p.rect,stream=stream.getvalue())
            p.insert_text((50,60),'Searchable text')
            a=p.add_rect_annot(fitz.Rect(30,380,360,420)); a.update()
            doc.save(self.src)
        r=self.run_cli()
        self.assertLess(r['crop_box_pt'][0],30)
        self.assertGreater(r['crop_box_pt'][3],420)
        with fitz.open(self.out) as doc:
            self.assertIn('Searchable text',doc[0].get_text())
            self.assertEqual(len(list(doc[0].annots())),1)

    def test_nonstandard_user_unit(self):
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500)
            p.insert_text((50,50),"Units")
            doc.xref_set_key(p.xref,"UserUnit","2")
            doc.save(self.src)
        self.assertIn("UserUnit",self.run_cli(ok=False).stderr)

    def test_units(self):
        self.fixture()
        a=self.run_cli('--margin','1in','--dry-run')
        b=self.run_cli('--margin','25.4mm','--dry-run')
        self.assertEqual(a['crop_box_pt'],b['crop_box_pt'])

if __name__=='__main__':
    unittest.main(verbosity=2)
