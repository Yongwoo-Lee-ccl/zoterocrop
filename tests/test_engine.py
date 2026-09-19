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

    def positions_file(self, positions):
        path = self.root/'annotations.json'
        path.write_text(json.dumps(positions))
        return str(path)

    def test_preserved_coordinates_and_embedded_highlights_all_rotations(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation):
                with fitz.open() as doc:
                    p=doc.new_page(width=400,height=500)
                    p.insert_text((90,110),'Annotation coordinate test')
                    p.add_highlight_annot(p.search_for('Annotation')[0]).update()
                    p.set_cropbox(fitz.Rect(20,30,380,470))
                    p.set_rotation(rotation)
                    doc.save(self.src)
                with fitz.open(self.src) as original:
                    contents=original[0].read_contents()
                    media=original[0].mediabox
                self.run_cli('--preserve-coordinates','--force')
                with fitz.open(self.out) as output:
                    self.assertEqual(output[0].rotation,rotation)
                    self.assertEqual(output[0].mediabox,media)
                    self.assertEqual(output[0].read_contents(),contents)
                    # Compare raw PDF QuadPoints: these must not move with CropBox.
                    with fitz.open(self.src) as original:
                        original_page, output_page = original[0], output[0]
                        self.assertEqual(original.xref_get_key(original_page.first_annot.xref,'QuadPoints'),
                                         output.xref_get_key(output_page.first_annot.xref,'QuadPoints'))
                    self.assertIn('Annotation coordinate test', output[0].get_text())

    def test_preserved_mixed_rotations_have_uniform_display_size(self):
        with fitz.open() as doc:
            for rotation in (0,90,180,270):
                p=doc.new_page(width=400,height=500)
                p.draw_rect(fitz.Rect(170,200,220,260),fill=(0,0,0))
                p.set_rotation(rotation)
            doc.save(self.src)
        report=self.run_cli('--preserve-coordinates','--margin','3mm')
        with fitz.open(self.out) as doc:
            for page,rotation in zip(doc,(0,90,180,270)):
                self.assertEqual(page.rotation,rotation)
                for a,b in zip((page.rect.width,page.rect.height),report['output_size_pt']):
                    self.assertAlmostEqual(a,b,places=3)

    def test_annotation_bounds_protect_marginal_notes_ink_and_next_page(self):
        self.fixture(boxes=((100,150,250,350),(100,150,250,350)))
        positions=[{'pageIndex':0,'rects':[[20,440,42,462]]},
                   {'pageIndex':0,'paths':[[340,40,355,60]],'width':8},
                   {'pageIndex':0,'rects':[[100,200,200,220]],'nextPageRects':[[15,200,100,220]]}]
        r=self.run_cli('--preserve-coordinates','--annotations-json',self.positions_file(positions))
        self.assertLess(r['crop_box_pt'][0],15)
        self.assertLess(r['crop_box_pt'][1],38)
        self.assertGreater(r['crop_box_pt'][2],359)
        self.assertGreater(r['crop_box_pt'][3],464)

    def test_annotation_mapping_with_crop_offset_and_rotation(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation):
                self.fixture(rotation=rotation,offset=True)
                pos={'pageIndex':0,'rects':[[25,450,45,475]]}
                r=self.run_cli('--preserve-coordinates','--annotations-json',self.positions_file([pos]),'--force')
                with fitz.open(self.out) as output:
                    page=output[0]
                    page.set_rotation(0)
                    visible=fitz.Rect(pos['rects'][0])*page.transformation_matrix
                    self.assertTrue(page.rect.contains(visible), (rotation,visible,page.rect))

    def test_rotated_text_annotation_bounds(self):
        self.fixture(boxes=((100,150,250,350),(100,150,250,350)))
        position={'pageIndex':0,'rects':[[40,380,140,400]],'rotation':90}
        r=self.run_cli('--preserve-coordinates','--annotations-json',self.positions_file([position]))
        self.assertLess(r['crop_box_pt'][0],80)
        self.assertLess(r['crop_box_pt'][1],60)

    def test_invalid_annotation_geometry_never_writes_output(self):
        self.fixture()
        cases=[{}, {'pageIndex':10,'rects':[[1,2,3,4]]},
               {'pageIndex':0,'rects':[[float('nan'),2,3,4]]},
               {'pageIndex':0,'paths':[[1,2,3]],'width':2},
               {'pageIndex':1,'rects':[[1,2,3,4]],'nextPageRects':[[1,2,3,4]]}]
        for position in cases:
            self.run_cli('--preserve-coordinates','--annotations-json',self.positions_file([position]),ok=False)
            self.assertFalse(self.out.exists())

    def test_annotations_require_preserved_coordinates(self):
        self.fixture()
        self.assertIn('requires',self.run_cli('--annotations-json',self.positions_file([]),ok=False).stderr)

    def arxiv_fixture(self, text='arXiv:2401.12345v2  [cs.CR]  2 Jan 2024', stamp_page=0, rotate=90, x=25, overlap=False):
        with fitz.open() as doc:
            for index in range(2):
                p=doc.new_page(width=400,height=500)
                p.draw_rect(fitz.Rect(80,80,320,400),fill=(0,0,0),color=None)
                if index == stamp_page:
                    p.insert_text((x,450),text,fontsize=12,rotate=rotate)
                    if overlap:
                        p.draw_line((15,20),(15,480),width=1)
            doc.save(self.src)

    def test_arxiv_stamp_cropped_and_original_streams_preserved(self):
        self.arxiv_fixture()
        before=self.src.read_bytes()
        r=self.run_cli('--preserve-coordinates','--margin','10pt')
        self.assertEqual(len(r['ignored_arxiv_stamps']),1)
        self.assertTrue(r['ignored_arxiv_stamps'][0]['hidden_by_crop'])
        self.assertGreater(r['crop_box_pt'][0],60)
        self.assertEqual(self.src.read_bytes(),before)
        with fitz.open(self.src) as original, fitz.open(self.out) as output:
            self.assertEqual(original[0].read_contents(),output[0].read_contents())
            self.assertNotIn('arXiv:',output[0].get_text())

    def test_arxiv_toggle_off_keeps_stamp(self):
        self.arxiv_fixture()
        r=self.run_cli('--preserve-coordinates','--keep-arxiv-stamp')
        self.assertEqual(r['ignored_arxiv_stamps'],[])
        self.assertLess(r['crop_box_pt'][0],25)
        with fitz.open(self.out) as doc:
            self.assertIn('arXiv:',doc[0].get_text())

    def test_arxiv_old_identifiers_and_large_margins(self):
        self.arxiv_fixture(text='arXiv:hep-th/9901001v1  1 Jan 1999')
        r=self.run_cli('--preserve-coordinates','--margin','200pt')
        self.assertEqual(len(r['ignored_arxiv_stamps']),1)
        self.assertTrue(r['ignored_arxiv_stamps'][0]['hidden_by_crop'])
        self.assertLess(r['crop_box_pt'][0],80)

    def test_arxiv_exception_does_not_hide_preserved_annotations(self):
        self.arxiv_fixture()
        pos=[{'pageIndex':0,'rects':[[10,200,32,222]]}]
        r=self.run_cli('--preserve-coordinates','--annotations-json',self.positions_file(pos))
        self.assertFalse(r['ignored_arxiv_stamps'][0]['hidden_by_crop'])
        self.assertLess(r['crop_box_pt'][0],10)
        self.assertTrue(any('cannot be fully cropped' in w for w in r['warnings']))

    def test_arxiv_exception_requires_first_page_vertical_margin_text(self):
        for kwargs in [{'stamp_page':1},{'rotate':0}, {'x':150},
                       {'text':'arXiv:2401.12345v2 explains our method'}, {'overlap':True}]:
            with self.subTest(kwargs=kwargs):
                self.arxiv_fixture(**kwargs)
                r=self.run_cli('--preserve-coordinates','--force')
                self.assertEqual(r['ignored_arxiv_stamps'],[])

if __name__=='__main__':
    unittest.main(verbosity=2)
