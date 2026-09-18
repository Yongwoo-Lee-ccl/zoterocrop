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
    p.add_argument('-f', '--force', action='store_true', help='replace existing output (never input)')
    return p


def measure(page, dpi, threshold, max_pixels):
    from PIL import Image, ImageChops
    import pymupdf as fitz
    scale = dpi / 72
    if math.ceil(page.rect.width * scale) * math.ceil(page.rect.height * scale) > max_pixels:
        raise ValueError(f'page {page.number+1}: render exceeds --max-pixels; reduce --dpi')
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False, annots=True)
    im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    r, g, b = im.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    bounds = darkest.point([255 if n < threshold else 0 for n in range(256)]).getbbox()
    if bounds is None:
        return None
    # Include a one-pixel guard for rounding and anti-aliasing. Convert to
    # unrotated CropBox coordinates, including an existing CropBox offset.
    box = page.cropbox
    x0, y0, x1, y1 = bounds
    return fitz.Rect(max(box.x0, box.x0 + (x0-1)/scale),
                     max(box.y0, box.y0 + (y0-1)/scale),
                     min(box.x1, box.x0 + (x1+1)/scale),
                     min(box.y1, box.y0 + (y1+1)/scale))


def process(args):
    import pymupdf as fitz
    if not 36 <= args.dpi <= 1200 or not 1 <= args.threshold <= 255 or args.max_pixels <= 0:
        raise ValueError('require --dpi 36..1200, --threshold 1..255, --max-pixels > 0')
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
        common = None
        content = None
        pages = []
        for page in doc:
            # Preserve visual appearance while making the shared box independent
            # of each page's /Rotate. PyMuPDF also adjusts links/annotations/widgets.
            page.remove_rotation()
            page = doc.reload_page(page)
            available = fitz.Rect(page.cropbox)
            if abs(page.rect.width - available.width) > 0.001 or abs(page.rect.height - available.height) > 0.001:
                raise ValueError(f'page {page.number+1}: nonstandard PDF UserUnit is unsupported; normalize page units first')
            common = available if common is None else common & available
            bounds = measure(page, args.dpi, args.threshold, args.max_pixels)
            if bounds is not None:
                content = fitz.Rect(bounds) if content is None else content | bounds
            pages.append({'page': page.number+1, 'original_box_pt': list(available),
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
        for page in doc:
            page.set_cropbox(crop)
        result = {'input': str(source), 'output': None if args.dry_run else str(target),
                  'page_count': len(doc), 'dpi': args.dpi, 'threshold': args.threshold,
                  'margin_pt': args.margin, 'pixel_guard_pt': 72/args.dpi,
                  'crop_box_pt': list(crop), 'output_size_pt': [crop.width, crop.height],
                  'warnings': warnings, 'pages': pages}
        if not args.dry_run:
            fd, temporary = tempfile.mkstemp(prefix='.pdf-crop-', suffix='.pdf', dir=target.parent)
            os.close(fd)
            try:
                doc.save(temporary, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                with fitz.open(temporary) as check:
                    if check.needs_pass:
                        check.authenticate(password)
                    for page in check:
                        if any(abs(a-b) > 0.001 for a,b in zip(page.cropbox, crop)) or page.rotation != 0:
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
