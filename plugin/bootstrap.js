/* PDF Common Crop: Zotero 9 / macOS. No shell commands are constructed. */
var CommonCrop = {
  id: 'pdf-common-crop@local.invalid',
  pref: 'extensions.pdf-common-crop.',
  rootURI: '',
  menus: [],
  busy: false,
  stopped: false,
  process: null,
  job: null,

  isPDF(item) {
    return !!item && item.isAttachment() && item.attachmentContentType === 'application/pdf'
      && !item.deleted;
  },

  margin(value) {
    const text = String(value).trim();
    const match = /^(\d+(?:\.\d*)?|\.\d+)\s*(pt|mm|cm|in)?$/i.exec(text);
    if (!match || !Number.isFinite(Number(match[1]))) {
      throw new Error('여백은 0 이상의 숫자로 입력하세요. 예: 10, 10pt, 3mm');
    }
    return text;
  },

  window(event) {
    return event?.target?.ownerGlobal || Zotero.getMainWindow();
  },

  alert(win, text) {
    Services.prompt.alert(win, 'PDF Common Crop', text);
  },

  async configure(win) {
    const field = { value: Zotero.Prefs.get(this.pref + 'python', true) || '' };
    if (!Services.prompt.prompt(win, 'PDF Common Crop: Python 설정',
      'setup.command 실행 후 표시된 Python 경로를 붙여 넣으세요.\n예: /Users/me/Downloads/zotero-common-crop/.venv/bin/python\n\nPyMuPDF와 Pillow가 설치된 Python 3.10 이상이 필요합니다.',
      field, null, {})) return false;
    const python = field.value.trim();
    if (!python.startsWith('/') || !(await IOUtils.exists(python))) {
      throw new Error('존재하는 Python 실행 파일의 절대 경로를 입력하세요.');
    }
    const probe = await this.execute(python, ['-c',
      'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"; import pymupdf, PIL; assert hasattr(pymupdf.Page, "remove_rotation"), "PyMuPDF 1.26+ required"; print("OK")']);
    if (probe.code || probe.stdout.trim() !== 'OK') {
      throw new Error('Python 환경 확인 실패:\n' + (probe.stderr || probe.stdout).slice(-5000));
    }
    Zotero.Prefs.set(this.pref + 'python', python, true);
    this.alert(win, 'Python 환경을 확인하고 저장했습니다.\nPDF 첨부파일을 우클릭해 “공통 여백 자르기”를 선택하세요.');
    return true;
  },

  async drain(pipe) {
    let output = '';
    for (;;) {
      const part = await pipe.readString();
      if (!part) break;
      // Keep draining even past the cap to prevent child-process deadlock.
      if (output.length < 16_000_000) output += part;
    }
    return output;
  },

  async execute(python, args) {
    if (this.stopped) throw new Error('플러그인이 비활성화되어 작업을 중단했습니다.');
    const { Subprocess } = ChromeUtils.importESModule('resource://gre/modules/Subprocess.sys.mjs');
    const process = await Subprocess.call({command: python, arguments: args, stderr: 'pipe',
      environment: { PYTHONIOENCODING: 'utf-8' }, environmentAppend: true});
    if (this.stopped) {
      await process.kill();
      throw new Error('플러그인이 비활성화되어 작업을 중단했습니다.');
    }
    this.process = process;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; process.kill().catch(Zotero.logError); }, 10 * 60 * 1000);
    try {
      const [stdout, stderr, status] = await Promise.all([
        this.drain(process.stdout), this.drain(process.stderr), process.wait()
      ]);
      if (timedOut) throw new Error('처리 시간이 10분을 초과해 중단했습니다.');
      if (this.stopped) throw new Error('플러그인이 비활성화되어 작업을 중단했습니다.');
      return {stdout, stderr, code: status.exitCode};
    }
    finally {
      clearTimeout(timer);
      if (this.process === process) this.process = null;
    }
  },

  async cropAttachment(item, margin) {
    if (this.busy) throw new Error('이미 다른 PDF를 처리하고 있습니다. 완료 후 다시 시도하세요.');
    this.busy = true;
    let job;
    try {
      margin = this.margin(margin);
      if (!this.isPDF(item)) throw new Error('PDF 첨부파일 하나를 선택하세요.');
      const library = Zotero.Libraries.get(item.libraryID);
      if (!library?.editable || !library.filesEditable) {
        throw new Error('이 라이브러리에 첨부파일을 추가할 권한이 없습니다.');
      }
      const python = Zotero.Prefs.get(this.pref + 'python', true);
      if (!python) throw new Error('도구 메뉴의 “PDF Common Crop: Python 설정”을 먼저 실행하세요.');
      const input = await item.getFilePathAsync();
      if (!input || !(await IOUtils.exists(input))) {
        throw new Error('PDF가 로컬에 없습니다. Zotero에서 파일을 다운로드한 뒤 다시 시도하세요.');
      }
      const id = Services.uuid.generateUUID().toString().replace(/[{}]/g, '');
      job = PathUtils.join(PathUtils.tempDir, 'zotero-common-crop-' + id);
      await IOUtils.makeDirectory(job, {permissions: 0o700});
      this.job = job;
      const engine = PathUtils.join(job, 'pdf_common_crop.py');
      const output = PathUtils.join(job, 'cropped.pdf');
      await IOUtils.writeUTF8(engine, await Zotero.File.getResourceAsync(this.rootURI + 'engine/pdf_common_crop.py'));
      const run = await this.execute(python, [engine, input, output, '--margin', margin, '--json']);
      if (run.code !== 0) throw new Error('PDF 처리 실패:\n' + (run.stderr || run.stdout).slice(-5000));
      const report = JSON.parse(run.stdout);
      if (!report.page_count || !(await IOUtils.exists(output))) throw new Error('출력 PDF를 확인하지 못했습니다.');
      if (this.stopped) throw new Error('작업이 중단되었습니다.');
      // Preserve the original attachment and its Zotero annotation items.
      const title = (item.getField('title') || 'PDF') + ' — cropped';
      const options = { file: output, libraryID: item.libraryID, title, contentType: 'application/pdf' };
      if (item.parentID) options.parentItemID = item.parentID;
      else options.collections = item.getCollections();
      const attachment = await Zotero.Attachments.importFromFile(options);
      return { attachment, report };
    }
    finally {
      if (job) {
        try { await IOUtils.remove(job, {recursive: true, ignoreAbsent: true}); }
        catch (error) { Zotero.logError(error); }
      }
      this.job = null;
      this.busy = false;
    }
  },

  async run(win, items) {
    try {
      if (this.busy) throw new Error('이미 PDF를 처리 중입니다.');
      if (items.length !== 1 || !this.isPDF(items[0])) throw new Error('PDF 첨부파일 하나를 선택하세요.');
      if (!Zotero.Prefs.get(this.pref + 'python', true) && !(await this.configure(win))) return;
      const field = {value: Zotero.Prefs.get(this.pref + 'margin', true) || '10pt'};
      if (!Services.prompt.prompt(win, 'PDF 공통 여백 자르기',
        '잘라낸 뒤 남길 여백을 입력하세요. 예: 10pt, 10, 3mm\n\n결과는 새 첨부파일로 추가됩니다. 원본 PDF와 Zotero 하이라이트·메모는 그대로 유지되며, 기존 하이라이트·메모는 새 PDF로 복사되지 않습니다.',
        field, null, {})) return;
      const margin = this.margin(field.value);
      Zotero.Prefs.set(this.pref + 'margin', margin, true);
      const progress = new Zotero.ProgressWindow({closeOnClick: false});
      progress.changeHeadline('PDF 공통 여백을 계산하고 있습니다…');
      progress.addDescription('완료되면 결과를 새 첨부파일로 추가합니다.');
      progress.show();
      let result;
      try { result = await this.cropAttachment(items[0], margin); }
      finally { progress.close(); }
      if (this.stopped) return;
      const [width, height] = result.report.output_size_pt;
      const warnings = result.report.warnings.join('\n');
      this.alert(win, `${result.report.page_count}페이지 처리 완료\n모든 페이지 크기: ${width.toFixed(1)} × ${height.toFixed(1)}pt\n새 첨부파일: ${result.attachment.getField('title')}` + (warnings ? '\n\n' + warnings : ''));
    }
    catch (error) {
      Zotero.logError(error);
      if (!this.stopped) this.alert(win, error.message || String(error));
    }
  },

  addWindow(win) {
    win.MozXULElement.insertFTLIfNeeded('pdf-common-crop.ftl');
  },

  async start(data) {
    this.rootURI = data.rootURI;
    this.stopped = false;
    for (const win of Zotero.getMainWindows()) this.addWindow(win);
    this.menus.push(Zotero.MenuManager.registerMenu({
      menuID: 'pdf-common-crop-run', pluginID: this.id, target: 'main/library/item', menus: [{
        menuType: 'menuitem', l10nID: 'pdf-common-crop-run',
        onShowing: (_event, context) => {
          context.setVisible(context.items?.length === 1 && this.isPDF(context.items[0]));
          context.setEnabled(!this.busy);
        },
        onCommand: (event, context) => { void this.run(this.window(event), context.items || []); }
      }]
    }));
    this.menus.push(Zotero.MenuManager.registerMenu({
      menuID: 'pdf-common-crop-settings', pluginID: this.id, target: 'main/menubar/tools', menus: [{
        menuType: 'menuitem', l10nID: 'pdf-common-crop-settings',
        onShowing: (_event, context) => context.setEnabled(!this.busy),
        onCommand: (event) => { const win = this.window(event); this.configure(win).catch(error => this.alert(win, error.message)); }
      }]
    }));
  },

  async stop() {
    this.stopped = true;
    for (const id of this.menus) Zotero.MenuManager.unregisterMenu(id);
    this.menus = [];
    if (this.process) await this.process.kill();
    for (const win of Zotero.getMainWindows()) {
      win.document.querySelector('link[rel="localization"][href="pdf-common-crop.ftl"]')?.remove();
    }
  }
};

function install() {}
function uninstall() {}
async function startup(data) { await CommonCrop.start(data); }
async function shutdown() { await CommonCrop.stop(); }
function onMainWindowLoad({window}) { CommonCrop.addWindow(window); }
function onMainWindowUnload() {}
