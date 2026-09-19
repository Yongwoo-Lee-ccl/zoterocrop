# ZoteroCrop

For Zotero mobile lovers! Auto-crop PDF margins and read comfortably.

A macOS plugin for Zotero that removes **margins that can be safely cropped across every page** of a PDF. The result is added as a new attachment, preserving the original file.

**Current version: 0.1.2 beta · Target: Zotero 9.0.x · Requires Python 3.10 or later**

[Releases and XPI downloads](https://github.com/Yongwoo-Lee-ccl/zoterocrop/releases) · [Report an issue](https://github.com/Yongwoo-Lee-ccl/zoterocrop/issues)

## Development and disclaimer

**This project was developed entirely using OpenAI Codex.**

This software is provided **AS IS**, without any express or implied warranties. The repository owner and maintainers accept no responsibility or liability for errors, data loss or corruption, interruptions, or any other problems or damages arising from the use of, or inability to use, this software. Use it at your own discretion and risk, and back up important PDFs and your Zotero library before use.

Passing automated tests or installation compatibility checks does not guarantee correct operation with every PDF or Zotero environment.

## Features

- Right-click a PDF attachment, specify the margin to retain, and add the cropped PDF as a new attachment
- Measure visible content on each page and apply **one identical CropBox** enclosing the union of all content bounds
- Keep output page sizes uniform while preserving searchable text and vector content
- Accept margins such as `10pt`, `10`, `3mm`, `0.5cm`, and `0.1in`
- Preserve the original PDF and the Zotero annotations associated with it
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
5. Open **Tools → PDF Common Crop: Python Setup…** and enter the Python path you copied.

You can also use an existing Python environment with PyMuPDF 1.26 or later and Pillow installed. Python itself is not bundled in the XPI.

Moving the folder after creating the virtual environment may break its paths. Run setup in the location where you intend to keep it.

## Usage

1. Expand a bibliographic item and select **one PDF attachment**. Standalone PDF items are also supported.
2. Right-click and choose **Crop Common PDF Margins…**.
3. Enter the margin to retain. The default is `10pt`.
4. The result is added as a new attachment named `Original title — cropped`.

Child attachments are added under the same parent item. Standalone PDFs are added to the same collections. Only one PDF is processed at a time.

**Existing Zotero highlights and notes are not copied to the new PDF.** They remain associated with the original attachment. Visible annotations already embedded in the PDF file are included in content detection.

## How it works and limitations

The engine computes the union of all page content bounding boxes and expands it by the requested margin. It then constrains this rectangle to the intersection of the original CropBoxes and applies the same rectangle to every page. If a PDF with mixed page sizes cannot be cropped this way without cutting content, processing stops with an error.

- Measurement is a pixel-based approximation at 144 dpi by default. Only pure white is treated as background, and a one-pixel (0.5 pt) protective margin is added.
- Colored backgrounds and scan noise may be detected as content. Detection of extremely small or faint content is not guaranteed.
- Requested margins are clamped to the available original page area. The plugin does not add new page area.
- Changing a CropBox does not delete hidden PDF data.
- The PDF must be downloaded locally, and you must have permission to add files to the library.
- The plugin UI does not accept passwords. For encrypted PDFs, use the standalone CLI's `--password-env` option.
- Nonstandard PDF UserUnit values are unsupported. Modifying a digitally signed PDF may invalidate its signature.
- Processing is limited to 10 minutes. Disabling the plugin stops any running Python job.

## Validation status

- All 16 Python engine tests passed
- All 12 bridge tests passed using mocked Zotero APIs and real Python processes
- A 31-page PDF test confirmed uniform output dimensions, preserved extracted text, and an unchanged original file
- All 31 output pages matched the corresponding original crop regions pixel for pixel at 144 dpi
- Package 0.1.1 passed the installation preflight check in a running Zotero 9.0.6 instance
- **Full integration testing of installation, menu actions, attachment import, restarts, and automatic updates in Zotero has not yet been completed.**

User PDFs and library data used during testing are not included in this repository.

## Troubleshooting

- **Installation rejected:** Check that you have the latest XPI and are running Zotero 9.0.x. Version 0.1.1 fixed the missing required update URL in 0.1.0.
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

Tests use Node.js 22 or later. Node.js is not required to use the plugin. Running the JavaScript tests without the environment variables skips the four tests that launch real Python processes.

`build.py` creates `dist/zoterocrop-VERSION.xpi` and an `updates.json` file containing its SHA-256 hash. To release a new version, bump the manifest version, build, and upload **that exact XPI** to the `vVERSION` GitHub Release. Commit the manifest and `updates.json` together. Do not distribute test documents, PDFs, or virtual environments.

The update URL is `https://raw.githubusercontent.com/Yongwoo-Lee-ccl/zoterocrop/main/updates.json`. The plugin retains the ID `pdf-common-crop@local.invalid` for continuity with existing installations. This ID is not an email contact or a server address.

Private development versions 0.1.0 and 0.1.1 do not have a working update URL, so their users must manually install the 0.1.2 XPI once. Subsequent versions use this repository's update information. Marking a GitHub release as a prerelease does not prevent Zotero updates: any version listed in `updates.json` becomes an update candidate for existing users.

See [the 0.1.2 release notes](docs/releases/v0.1.2.md) for the current beta's scope and limitations.

## Dependency licenses

PyMuPDF/MuPDF is available under the AGPL or a commercial license. See the [official PyMuPDF licensing information](https://pymupdf.readthedocs.io/en/latest/about.html). Pillow has its own license. The disclaimer above does not replace the license terms of these dependencies. This repository does not bundle the Python interpreter or dependency binaries.
