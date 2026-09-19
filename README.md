# Crop Margins

For Zotero mobile lovers! Auto-crop PDF margins and read comfortably.

A macOS plugin for Zotero that removes **margins that can be safely cropped across every page** of a PDF. The result is added as a new attachment. Optional settings copy existing annotations and move the original attachment to Zotero Trash after success.

**Current version: 0.2.0 beta · Target: Zotero 9.0.x–10.0.x · Requires Python 3.10 or later**

[Releases and XPI downloads](https://github.com/Yongwoo-Lee-ccl/zoterocrop/releases) · [Report an issue](https://github.com/Yongwoo-Lee-ccl/zoterocrop/issues)

## Development and disclaimer

**This project was developed entirely using OpenAI Codex.**

This software is provided **AS IS**, without any express or implied warranties. The repository owner and maintainers accept no responsibility or liability for errors, data loss or corruption, interruptions, or any other problems or damages arising from the use of, or inability to use, this software. Use it at your own discretion and risk, and back up important PDFs and your Zotero library before use.

Passing automated tests or installation compatibility checks does not guarantee correct operation with every PDF or Zotero environment.

## Features

- Right-click a PDF attachment, specify the margin to retain, and add the cropped PDF as a new attachment
- Measure visible content on every page and apply one common crop in displayed page coordinates
- Keep output page sizes uniform while preserving searchable text and vector content
- Accept margins such as `10pt`, `10`, `3mm`, `0.5cm`, and `0.1in`
- Preserve original PDF coordinates, page rotation, embedded annotations, searchable text, and vector content
- Independently enable **Preserve existing annotations** and **Remove the original PDF after success**; both default to **off**
- **Crop the vertical arXiv identifier** is a separate setting, enabled by default
- Process PDFs locally; new attachments follow your existing Zotero sync settings

## Installation

1. Download the [repository ZIP](https://github.com/Yongwoo-Lee-ccl/zoterocrop/archive/refs/heads/main.zip) and extract it to a permanent location.
2. Install Python 3.10 or later, open a terminal in the extracted folder, and run:

   ```sh
   zsh setup.command
   ```

   This installs PyMuPDF and Pillow in a local virtual environment. The initial download requires an internet connection. Copy the **full path** to `.venv/bin/python` printed when setup finishes.

3. Download the latest XPI from [Releases](https://github.com/Yongwoo-Lee-ccl/zoterocrop/releases).
4. Drag the XPI into Zotero's **Tools → Plugins** window to install it.
5. Open **Tools → Crop Margins: Settings… → Configure and verify Python…** and enter the Python path you copied.

You can also use an existing Python environment with PyMuPDF 1.26 or later and Pillow installed. Python itself is not bundled in the XPI.

Moving the folder after creating the virtual environment may break its paths. Run setup in the location where you intend to keep it.

## Usage

1. Expand a bibliographic item and select **one PDF attachment**. Standalone PDF items are also supported.
2. Right-click and choose **Crop PDF Margins…**.
3. Enter the margin to retain. The default is `10pt`.
4. The result is added as a new attachment named `Original title — cropped`.

Child attachments are added under the same parent item. Standalone PDFs are added to the same collections. Only one PDF is processed at a time.

### Independent settings

Open **Tools → Crop Margins: Settings…**, or **Zotero Settings → Crop Margins**.

| Preserve existing annotations | Remove the original PDF | Result |
| --- | --- | --- |
| Off (default) | Off (default) | New cropped PDF; original and its Zotero annotations stay in the library |
| On | Off | Copy annotations to the new PDF; keep the original |
| Off | On | New PDF without copied Zotero annotations; original and its annotations move to Trash |
| On | On | Copy annotations, then move the original and its annotations to Trash |

Preservation copies all six Zotero PDF annotation types: highlights, underlines, notes, text, images, and ink, including comments, tags, colors, page labels, and displayed authorship. The attachment note is copied too. Annotation bounds participate in crop detection, including marginal notes, ink stroke width, rotated text, and highlights spanning two pages. Original PDF coordinates and rotations remain unchanged, so copied positions stay aligned.

The original is moved to **Zotero Trash**, never permanently erased by the plugin, and can be restored. External linked PDF files remain at their external location. Annotation copying and trashing the original share a database transaction. If copying, saving, or cropping fails, the original is retained. If source annotations or the source file change during processing, processing stops before replacing the original.

**Crop the vertical arXiv identifier** defaults to **on** and can be turned off independently. It recognizes a vertical arXiv identifier in the left margin of the first page (both modern and legacy arXiv IDs), ignores it during margin measurement, and hides it with the CropBox. The underlying PDF text is not erased. A large requested left margin can be reduced to keep the identifier outside the visible page. Text, diagrams, embedded annotations, and preserved Zotero annotations take priority; if the identifier cannot be safely hidden, the area is retained with a warning. Scanned stamps without extractable text are not detected. The CLI equivalent for turning this behavior off is `--keep-arxiv-stamp`.

Embedded PDF annotations are retained regardless of the preservation toggle. The toggle controls Zotero annotations stored separately from the PDF. Links already inserted into other notes still point to the original attachment; those notes are not rewritten. Image/ink annotation previews may be regenerated by Zotero when the new PDF is opened.

## How it works and limitations

The plugin computes the union of visible content and, when preservation is enabled, annotation bounds in displayed page coordinates. It expands this by the requested margin and constrains it to the common available page area. The same displayed crop is mapped back to each page’s original coordinate system. Output pages have uniform displayed dimensions; raw CropBoxes can differ when source rotations or offsets differ. If mixed page sizes cannot be cropped without cutting visible content, processing stops with an error.

The standalone CLI retains its legacy rotation-normalizing mode by default. Use `--preserve-coordinates` for the plugin’s coordinate-preserving behavior, and optionally `--annotations-json positions.json` with an array of Zotero annotation position objects.

- Measurement is a pixel-based approximation at 144 dpi by default. Only pure white is treated as background, and a one-pixel (0.5 pt) protective margin is added.
- Colored backgrounds and scan noise may be detected as content. Detection of extremely small or faint content is not guaranteed.
- Requested margins are clamped to the available original page area. The plugin does not add new page area.
- Changing a CropBox does not delete hidden PDF data.
- The PDF must be downloaded locally, and you must have permission to add files to the library.
- The plugin UI does not accept passwords. For encrypted PDFs, use the standalone CLI's `--password-env` option.
- Nonstandard PDF UserUnit values are unsupported. Modifying a digitally signed PDF may invalidate its signature.
- Processing is limited to 10 minutes. Disabling the plugin stops any running Python job.

## Validation status

- All 28 Python engine tests passed, including all four rotations, existing CropBox offsets, embedded highlight coordinates, marginal annotations, ink, and rotated text
- All 23 plugin bridge tests passed, including every toggle combination and rollback/error handling
- Package 0.2.0 installed and ran in Zotero 10.0.3; all four preservation/removal combinations and all six Zotero annotation types were checked
- A real 15-page arXiv PDF test hid the first-page side identifier and preserved every page’s content streams, MediaBox, and rotation
- Native Zotero integration results are documented in the [0.2.0 release notes](docs/releases/v0.2.0.md)
- Automatic update delivery and a full application restart have not been tested end to end

Automated tests use synthetic PDFs; the additional arXiv check used a public sample. User PDFs and library data are not included in this repository.

## Troubleshooting

- **Installation rejected:** Check that you have the latest XPI and are running Zotero 9.0.x or 10.0.x.
- **Python environment check failed:** Run your chosen Python executable with `-m pip install -r requirements.txt`, then enter its full path again.
- **Menu missing:** Select exactly one PDF attachment, rather than its parent bibliographic item.
- **File missing:** Open the original PDF in Zotero first to download it.
- **Common crop not possible:** Normalize the page sizes and coordinate systems before retrying.

When reporting an issue, include your Zotero, macOS, and plugin versions, along with the error message. Do not attach sensitive PDFs or library data to public issues.

## Development and releases

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/make_fixture.py work/test.pdf
CROP_TEST_PYTHON="$PWD/.venv/bin/python" \
CROP_TEST_PDF="$PWD/work/test.pdf" \
CROP_TEST_PAGES=3 node --test tests/test_plugin.cjs
python build.py
```

Tests use Node.js 22 or later. Node.js is not required to use the plugin. Running the JavaScript tests without the environment variables skips the tests that launch real Python processes.

`build.py` creates `dist/crop-margins-VERSION.xpi` and an `updates.json` file containing its SHA-256 hash. To release a new version, bump the manifest version, build, and upload **that exact XPI** to the `vVERSION` GitHub Release. Commit the manifest and `updates.json` together. Do not distribute test documents, PDFs, or virtual environments.

The update URL is `https://raw.githubusercontent.com/Yongwoo-Lee-ccl/zoterocrop/main/updates.json`. The plugin retains the ID `pdf-common-crop@local.invalid` for continuity with existing installations. This ID is not an email contact or a server address.

Private development versions 0.1.0 and 0.1.1 do not have a working update URL, so their users must manually install the latest XPI once. Subsequent versions use this repository's update information. Marking a GitHub release as a prerelease does not prevent Zotero updates: any version listed in `updates.json` becomes an update candidate for existing users.

See [the 0.2.0 release notes](docs/releases/v0.2.0.md) for the current beta’s scope and limitations. The display name is now **Crop Margins**; the repository URL and internal plugin ID are unchanged so existing installations can update.

## Dependency licenses

PyMuPDF/MuPDF is available under the AGPL or a commercial license. See the [official PyMuPDF licensing information](https://pymupdf.readthedocs.io/en/latest/about.html). Pillow has its own license. The disclaimer above does not replace the license terms of these dependencies. This repository does not bundle the Python interpreter or dependency binaries.
