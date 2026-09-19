#!/usr/bin/env python3
"""Measure visible PDF content and apply one common CropBox to every page."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile


def margin_value(value):
    match = re.fullmatch(r'\s*(\d+(?:\.\d*)?|\.\d+)\s*(pt|mm|cm|in)?\s*', value, re.I)
    if not match:
        raise argparse.ArgumentTypeError('margin must be nonnegative, e.g. 10, 10pt, 3mm')
    result = float(match[1]) * {'pt': 1, 'mm': 72/25.4, 'cm': 72/2.54, 'in': 72}[ (match[2] or 'pt').lower() ]
    if not math.isfinite(result):
        raise argparse.ArgumentTypeError('margin must be finite')
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', nargs='?', type=Path, help='default: INPUT.cropped.pdf')
    p.add_argument('-m', '--margin', type=margin_value, default=0., help='remaining margin per side; default 0pt')
    p.add_argument('--dpi', type=int, default=144, help='measurement resolution, 36..1200 (default 144)')
    p.add_argument('--threshold', type=int, default=255, help='content if any RGB channel is below this, 1..255 (default 255)')
    p.add_argument('--max-pixels', type=int, default=40_000_000, help='maximum rendered pixels per page')
    p.add_argument('--password-env', help='environment variable containing PDF password')
    p.add_argument('--dry-run', action='store_true', help='measure only; write no PDF')
    p.add_argument('--json', action='store_true', help='print machine-readable report')
    p.add_argument('--preserve-coordinates', action='store_true',
                   help='retain PDF coordinates and rotations for Zotero annotations')
    p.add_argument('--annotations-json', type=Path,
                   help='JSON array of Zotero annotation positions to keep visible (requires --preserve-coordinates)')
    p.add_argument('--keep-arxiv-stamp', action='store_true',
                   help='treat the first-page vertical arXiv identifier as ordinary content')
    p.add_argument('-f', '--force', action='store_true', help='replace existing output (never input)')
    return p


def arxiv_stamps(page):
    """Recognize only isolated, vertical arXiv identifiers in the first left margin.

    These rectangles are ignored for measurement, never redacted from the PDF.
    Any overlapping text, image, drawing, or embedded annotation wins over the
    exception, so a false match cannot erase other visible content.
    """
    import pymupdf as fitz
    if page.number != 0:
        return []
    pattern = re.compile(
        r'arXiv:\s*(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.\-]*/\d{7})(?:v\d+)?'
        r'(?:\s+\[[a-z0-9.\- ]+\])?(?:\s+\d{1,2}\s+[a-z]{3}\s+\d{4})?', re.I)
    blocks = page.get_text('dict')['blocks']
    lines = [line for block in blocks for line in block.get('lines', [])]
    candidates = []
    matrix = page.rotation_matrix
    for line in lines:
        text = ''.join(span['text'] for span in line['spans']).strip()
        if not pattern.fullmatch(text):
            continue
        dx, dy = line['dir']
        display_dx, display_dy = dx*matrix.a+dy*matrix.c, dx*matrix.b+dy*matrix.d
        rect = fitz.Rect(line['bbox']) * matrix
        if (abs(display_dx) > 0.01 or abs(display_dy) < 0.99
                or rect.x0 < 0 or rect.x1 > min(72, page.rect.width * 0.15)
                or rect.height < 4 * rect.width):
            continue
        unrotated = fitz.Rect(line['bbox'])
        protected = [fitz.Rect(other['bbox']) for other in lines if other is not line]
        protected += [fitz.Rect(block['bbox']) for block in blocks if block.get('type') == 1]
        for drawing in page.get_drawings():
            pad = max((drawing.get('width') or 1) / 2, 0.5)
            protected.append(drawing['rect'] + (-pad, -pad, pad, pad))
        protected += [annotation.rect for annotation in page.annots()]
        protected_area = unrotated + (-0.5, -0.5, 0.5, 0.5)
        if any(protected_area.intersects(other) for other in protected):
            continue
        candidates.append({'text': text, 'rect': rect})
    return candidates


def measure(page, dpi, threshold, max_pixels, local=False, ignored=()):
    from PIL import Image, ImageChops, ImageDraw
    import pymupdf as fitz
    scale = dpi / 72
    if math.ceil(page.rect.width * scale) * math.ceil(page.rect.height * scale) > max_pixels:
        raise ValueError(f'page {page.number+1}: render exceeds --max-pixels; reduce --dpi')
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False, annots=True)
    im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    for stamp in ignored:
        box = stamp['rect']
        # Mask only the measurement raster. The PDF's text streams stay intact.
        ImageDraw.Draw(im).rectangle((math.floor(box.x0*scale), math.floor(box.y0*scale),
                                      math.ceil(box.x1*scale), math.ceil(box.y1*scale)), fill='white')
    r, g, b = im.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    bounds = darkest.point([255 if n < threshold else 0 for n in range(256)]).getbbox()
    if bounds is None:
        return None
    # Include a one-pixel guard for rounding and anti-aliasing. Convert to
    # unrotated CropBox coordinates, including an existing CropBox offset.
    box = page.rect if local else page.cropbox
    x0, y0, x1, y1 = bounds
    return fitz.Rect(max(box.x0, box.x0 + (x0-1)/scale),
                     max(box.y0, box.y0 + (y0-1)/scale),
                     min(box.x1, box.x0 + (x1+1)/scale),
                     min(box.y1, box.y0 + (y1+1)/scale))


def annotation_bounds(positions, page_count):
    """Validate reader geometry and collect bounds in original PDF user space."""
    import pymupdf as fitz
    if not isinstance(positions, list):
        raise ValueError('annotations must be an array of position objects')
    bounds = [[] for _ in range(page_count)]

    def numbers(values, length=None):
        if (not isinstance(values, list) or (length is not None and len(values) != length)
                or not values or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                    or not math.isfinite(v) for v in values)):
            raise ValueError('invalid annotation coordinates')
        return values

    def rectangles(values, page_index, rotation=0):
        if not isinstance(values, list) or not values:
            raise ValueError('invalid annotation rectangles')
        for value in values:
            rect = fitz.Rect(numbers(value, 4))
            if rect.is_empty or rect.is_infinite:
                raise ValueError('invalid annotation rectangle')
            if rotation:
                center = (rect.tl + rect.br) / 2
                transform = (fitz.Matrix(1, 0, 0, 1, -center.x, -center.y)
                             * fitz.Matrix(rotation)
                             * fitz.Matrix(1, 0, 0, 1, center.x, center.y))
                rect = rect * transform
            bounds[page_index].append(rect)

    for position in positions:
        if not isinstance(position, dict):
            raise ValueError('invalid annotation position')
        index = position.get('pageIndex')
        if type(index) is not int or not 0 <= index < page_count:
            raise ValueError('annotation page index is out of range')
        rotation = position.get('rotation', 0)
        numbers([rotation])
        if 'rects' in position:
            rectangles(position['rects'], index, rotation)
        elif 'paths' in position:
            width = position.get('width', 1)
            numbers([width])
            if width <= 0 or not isinstance(position['paths'], list) or not position['paths']:
                raise ValueError('invalid ink annotation')
            for path in position['paths']:
                numbers(path)
                if len(path) % 2:
                    raise ValueError('invalid ink annotation path')
                xs, ys = path[::2], path[1::2]
                bounds[index].append(fitz.Rect(min(xs)-width/2, min(ys)-width/2,
                                               max(xs)+width/2, max(ys)+width/2))
        else:
            raise ValueError('unsupported annotation geometry; original PDF must be retained')
        if 'nextPageRects' in position:
            if index + 1 >= page_count:
                raise ValueError('annotation next page is out of range')
            rectangles(position['nextPageRects'], index+1)
    return bounds


def process(args):
    import pymupdf as fitz
    if not 36 <= args.dpi <= 1200 or not 1 <= args.threshold <= 255 or args.max_pixels <= 0:
        raise ValueError('require --dpi 36..1200, --threshold 1..255, --max-pixels > 0')
    if args.annotations_json and not args.preserve_coordinates:
        raise ValueError('--annotations-json requires --preserve-coordinates')
    source = args.input.resolve()
    target = (args.output or args.input.with_name(args.input.stem + '.cropped.pdf')).absolute()
    if source == target.resolve() or (target.exists() and os.path.samefile(source, target)):
        raise ValueError('input and output must be different files')
    if not args.dry_run:
        if target.exists() and not args.force:
            raise ValueError(f'output exists: {target}; use --force to replace')
        if not target.parent.is_dir():
            raise ValueError(f'output directory does not exist: {target.parent}')
    with fitz.open(source) as doc:
        if not doc.is_pdf:
            raise ValueError('input must be a PDF')
        if doc.needs_pass:
            password = os.environ.get(args.password_env, '') if args.password_env else ''
            if not password or not doc.authenticate(password):
                raise ValueError('encrypted PDF: supply a valid password via --password-env VARIABLE')
        if not doc.page_count:
            raise ValueError('PDF has no pages')
        positions = json.loads(args.annotations_json.read_text()) if args.annotations_json else []
        annotation_boxes = annotation_bounds(positions, doc.page_count)
        common = None
        content = None
        pages = []
        crop_transforms = []
        ignored_stamps = []
        for page in doc:
            # Preserve visual appearance while making the shared box independent
            # of each page's /Rotate. PyMuPDF also adjusts links/annotations/widgets.
            rotation = page.rotation
            if not args.preserve_coordinates:
                page.remove_rotation()
                page = doc.reload_page(page)
            # Read the PDF -> local MuPDF transform at rotation zero. PyMuPDF's
            # rotated-page transform otherwise omits existing CropBox offsets.
            saved_rotation = page.rotation
            page.set_rotation(0)
            pdf_to_local = page.transformation_matrix
            unrotated_size = page.rect
            page.set_rotation(saved_rotation)
            box = page.cropbox
            if abs(unrotated_size.width - box.width) > 0.001 or abs(unrotated_size.height - box.height) > 0.001:
                raise ValueError(f'page {page.number+1}: nonstandard PDF UserUnit is unsupported; normalize page units first')
            available = fitz.Rect(page.rect if args.preserve_coordinates else box)
            crop_transforms.append(page.derotation_matrix * fitz.Matrix(1, 0, 0, 1, box.x0, box.y0))
            common = available if common is None else common & available
            stamps = [] if args.keep_arxiv_stamp else arxiv_stamps(page)
            for stamp in stamps:
                rect = stamp['rect'] + (available.x0, available.y0, available.x0, available.y0)
                ignored_stamps.append({'page': page.number+1, 'text': stamp['text'],
                                       'box_pt': list(rect)})
            bounds = measure(page, args.dpi, args.threshold, args.max_pixels, args.preserve_coordinates, stamps)
            if args.preserve_coordinates:
                for annotation in annotation_boxes[page.number]:
                    visible = (annotation * pdf_to_local * page.rotation_matrix) & available
                    if not visible.is_empty:
                        # Include antialiasing at the annotation boundary.
                        guard = 72 / args.dpi
                        visible = fitz.Rect(visible.x0-guard, visible.y0-guard,
                                            visible.x1+guard, visible.y1+guard) & available
                        bounds = visible if bounds is None else bounds | visible
            if bounds is not None:
                content = fitz.Rect(bounds) if content is None else content | bounds
            pages.append({'page': page.number+1, 'original_box_pt': list(available),
                          'rotation': rotation if args.preserve_coordinates else 0,
                          'content_box_pt': list(bounds) if bounds is not None else None})
        if common.is_empty or common.is_infinite:
            raise ValueError('pages have no common usable CropBox')
        if content is not None and not common.contains(content):
            raise ValueError('page sizes/origins are incompatible: a common CropBox would cut content; normalize page canvases first')
        warnings = []
        if content is None:
            crop = common
            warnings.append('All pages are blank under the chosen threshold; retaining the common visible area.')
        else:
            desired = fitz.Rect(content.x0-args.margin, content.y0-args.margin,
                                content.x1+args.margin, content.y1+args.margin)
            crop = desired & common
            if not common.contains(desired):
                warnings.append('Requested margin exceeds available space; clamped to the common original page area.')
        for stamp in ignored_stamps:
            rect = fitz.Rect(stamp['box_pt'])
            # A generous requested margin must not accidentally bring the stamp
            # back. Limit the left margin only when all actual content still fits.
            if crop.intersects(rect) and content is not None and content.x0 > rect.x1 + 72/args.dpi:
                crop.x0 = max(crop.x0, rect.x1 + 72/args.dpi)
            stamp['hidden_by_crop'] = not crop.intersects(rect)
            if not stamp['hidden_by_crop']:
                warnings.append('The arXiv side stamp cannot be fully cropped without cutting content or preserved annotations; keeping that area.')
        for page in doc:
            page_crop = crop * crop_transforms[page.number] if args.preserve_coordinates else crop
            page.set_cropbox(page_crop)
            pages[page.number]['output_crop_box_pt'] = list(page.cropbox)
        result = {'input': str(source), 'output': None if args.dry_run else str(target),
                  'preserves_coordinates': args.preserve_coordinates,
                  'crop_coordinate_space': 'display' if args.preserve_coordinates else 'unrotated-cropbox',
                  'page_count': len(doc), 'dpi': args.dpi, 'threshold': args.threshold,
                  'margin_pt': args.margin, 'pixel_guard_pt': 72/args.dpi,
                  'crop_box_pt': list(crop), 'output_size_pt': [crop.width, crop.height],
                  'warnings': warnings, 'pages': pages}
        result['ignored_arxiv_stamps'] = ignored_stamps
        if not args.dry_run:
            fd, temporary = tempfile.mkstemp(prefix='.pdf-crop-', suffix='.pdf', dir=target.parent)
            os.close(fd)
            try:
                doc.save(temporary, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                with fitz.open(temporary) as check:
                    if check.needs_pass:
                        check.authenticate(password)
                    for page in check:
                        expected = pages[page.number]
                        if (any(abs(a-b) > 0.001 for a,b in zip(page.cropbox, expected['output_crop_box_pt']))
                                or page.rotation != expected['rotation']
                                or abs(page.rect.width - crop.width) > 0.001
                                or abs(page.rect.height - crop.height) > 0.001):
                            raise ValueError('saved PDF failed common CropBox verification')
                if args.force:
                    os.replace(temporary, target)
                else:
                    # Atomic no-clobber publication, including a concurrent writer.
                    os.link(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = process(args)
    except ImportError as exc:
        print(f'error: missing dependency ({exc}); run python3 -m pip install -r requirements.txt', file=sys.stderr)
        return 2
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Pages: {result['page_count']}")
        for page in result['pages']:
            print(f"  {page['page']}: content = {page['content_box_pt'] or 'blank'}")
        print('Common CropBox (pt): ' + ', '.join(f'{v:.3f}' for v in result['crop_box_pt']))
        print('Uniform output size (pt): ' + ' x '.join(f'{v:.3f}' for v in result['output_size_pt']))
        print('Dry run: no PDF written.' if args.dry_run else f"Saved: {result['output']}")
    for warning in result['warnings']:
        print('warning: ' + warning, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
