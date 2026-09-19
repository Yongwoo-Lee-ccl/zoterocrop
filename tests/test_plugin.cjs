const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const vm = require('node:vm');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const source = path.resolve(__dirname, '../plugin/bootstrap.js');
const python = process.env.CROP_TEST_PYTHON;
const input = process.env.CROP_TEST_PDF;

async function sandbox() {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'crop-plugin-test-'));
  const prefs = new Map();
  const imported = [];
  const menus = [];
  const removed = [];
  const errors = [];
  const annotations = [];
  const copies = [];
  const trashed = [];
  const item = {
    id:1, libraryID:1, parentID:10, deleted:false, attachmentContentType:'application/pdf',
    isAttachment:()=>true, getFilePathAsync:async()=>input,
    getField:()=> '테스트 PDF', getCollections:()=>[15],
    getAnnotations:()=>annotations,getTags:()=>[{tag:'source tag'}],getNote:()=>'<p>Attachment note</p>'
  };
  function pipe(readable) {
    readable.setEncoding('utf8');
    const iterator = readable[Symbol.asyncIterator]();
    return {readString:async()=>{const r=await iterator.next();return r.done?'':r.value;}};
  }
  const Subprocess = {call:async options=>{
    const child = spawn(options.command,options.arguments,{env:{...process.env,...options.environment},stdio:['ignore','pipe','pipe']});
    const finished = new Promise((resolve,reject)=>{
      child.once('error',reject);child.once('close',code=>resolve({exitCode:code}));
    });
    return {stdout:pipe(child.stdout),stderr:pipe(child.stderr),wait:()=>finished,kill:async()=>{child.kill();return finished;}};
  }};
  const context = vm.createContext({
    setTimeout,clearTimeout,console,
    Services:{uuid:{generateUUID:()=>crypto.randomUUID()},prompt:{alert:()=>{},prompt:()=>false}},
    ChromeUtils:{importESModule:()=>({Subprocess})},
    PathUtils:{tempDir:temp,join:path.join},
    IOUtils:{
      exists:async p=>{try{await fs.access(p);return true;}catch{return false;}},
      stat:async p=>{const st=await fs.stat(p);return {size:st.size,lastModified:st.mtimeMs};},
      makeDirectory:(p,options)=>fs.mkdir(p,{mode:options.permissions}),
      writeUTF8:(p,s)=>fs.writeFile(p,s),
      remove:(p,options)=>fs.rm(p,{recursive:options.recursive,force:options.ignoreAbsent})
    },
    Zotero:{
      Prefs:{get:k=>prefs.get(k),set:(k,v)=>prefs.set(k,v)},
      Libraries:{get:()=>({editable:true,filesEditable:true})},
      DB:{executeTransaction:async fn=>{
        const copyCount=copies.length,trashCount=trashed.length;
        try{return await fn();}catch(error){copies.length=copyCount;trashed.length=trashCount;throw error;}
      }},
      Items:{trash:async id=>trashed.push(id),trashTx:async id=>trashed.push(id)},
      Annotations:{toJSONSync:a=>({authorName:a.annotationAuthorName})},
      PreferencePanes:{register:async()=> 'pdf-common-crop-preferences'},
      File:{getResourceAsync:async()=>fs.readFile(path.resolve(__dirname,'../plugin/engine/pdf_common_crop.py'),'utf8')},
      Attachments:{importFromFile:async options=>{
        const copied=path.join(temp,`imported-${imported.length}.pdf`);
        await fs.copyFile(options.file,copied);
        imported.push({...options,copied});
        return {id:100+imported.length,parentID:options.parentItemID,getField:()=>options.title,
          setTags(tags){this.tags=tags;},setNote(note){this.note=note;},save:async()=>{}};
      }},
      MenuManager:{registerMenu:m=>{menus.push(m);return m.menuID;},unregisterMenu:id=>removed.push(id)},
      getMainWindows:()=>[],getMainWindow:()=>null,logError:e=>errors.push(e)
    }
  });
  vm.runInContext(await fs.readFile(source,'utf8'),context);
  const plugin = context.CommonCrop;
  plugin.rootURI='file:///mock/plugin/';
  prefs.set(plugin.pref+'python',python);
  return {temp,plugin,context,prefs,item,imported,menus,removed,errors,annotations,copies,trashed,
    addAnnotation(type='highlight') {
      const annotation={annotationType:type,annotationPosition:JSON.stringify({pageIndex:0,rects:[[30,420,120,445]]}),
        annotationIsExternal:false,annotationAuthorName:'Original author',
        toJSON(){return {type:this.annotationType,position:this.annotationPosition};},
        clone(){const copy={...this,save:async()=>copies.push(copy)};return copy;}};
      annotations.push(annotation);return annotation;
    },cleanup:()=>fs.rm(temp,{recursive:true,force:true})};
}

async function withSandbox(fn) {const s=await sandbox();try{await fn(s);}finally{await s.cleanup();}}

test('margin accepts supported units and rejects invalid values',()=>withSandbox(async s=>{
  for(const value of ['0','10','10pt','3mm','.5cm','1in']) assert.equal(s.plugin.margin(value),value);
  for(const value of ['-1','NaN','Infinity','1px','1; touch /tmp/x','1e999']) assert.throws(()=>s.plugin.margin(value));
}));
test('PDF selection rejects deleted/non-PDF items',()=>withSandbox(async s=>{
  assert.equal(s.plugin.isPDF(s.item),true);
  assert.equal(s.plugin.isPDF({...s.item,deleted:true}),false);
  assert.equal(s.plugin.isPDF({...s.item,attachmentContentType:'text/html'}),false);
}));
test('registers two menus and unregisters on stop',()=>withSandbox(async s=>{
  await s.plugin.start({rootURI:'file:///plugin/'});
  assert.equal(s.menus.length,2);
  let visible,enabled;
  s.menus[0].menus[0].onShowing(null,{items:[s.item],setVisible:v=>visible=v,setEnabled:v=>enabled=v});
  assert.equal(visible,true); assert.equal(enabled,true);
  s.plugin.busy=true;
  s.menus[0].menus[0].onShowing(null,{items:[],setVisible:v=>visible=v,setEnabled:v=>enabled=v});
  assert.equal(visible,false); assert.equal(enabled,false);
  await s.plugin.stop();assert.equal(s.removed.length,2);
}));
test('read-only library rejected without import',()=>withSandbox(async s=>{
  s.context.Zotero.Libraries.get=()=>({editable:false,filesEditable:false});
  await assert.rejects(s.plugin.cropAttachment(s.item,'10'),/권한/);
  assert.equal(s.imported.length,0);assert.equal(s.plugin.busy,false);
}));
test('missing Python configuration rejected',()=>withSandbox(async s=>{
  s.prefs.clear();await assert.rejects(s.plugin.cropAttachment(s.item,'10'),/설정/);
}));
test('missing attachment rejected',()=>withSandbox(async s=>{
  s.item.getFilePathAsync=async()=>'/nonexistent/crop-test.pdf';
  await assert.rejects(s.plugin.cropAttachment(s.item,'10'),/로컬/);
}));
test('concurrent processing is rejected',()=>withSandbox(async s=>{
  s.plugin.busy=true;await assert.rejects(s.plugin.cropAttachment(s.item,'10'),/이미/);
}));
test('drains all chunks, not only the first one',()=>withSandbox(async s=>{
  const chunks=['a','b','c',''];assert.equal(await s.plugin.drain({readString:async()=>chunks.shift()}),'abc');
}));
test('real Python engine output imported as sibling; original unchanged', {skip:!python||!input},()=>withSandbox(async s=>{
  const before=await fs.readFile(input);
  const result=await s.plugin.cropAttachment(s.item,'10pt');
  assert.equal(result.report.page_count,Number(process.env.CROP_TEST_PAGES || 3));
  assert.equal(s.imported.length,1);
  assert.equal(s.imported[0].parentItemID,10);
  assert.equal(s.imported[0].title,'테스트 PDF — cropped');
  assert.deepEqual(await fs.readFile(input),before);
  assert.equal(await s.context.IOUtils.exists(s.imported[0].file),false);
  assert.equal(s.plugin.busy,false);assert.equal(s.plugin.job,null);
}));
test('standalone attachment keeps collections', {skip:!python||!input},()=>withSandbox(async s=>{
  s.item.parentID=null;
  await s.plugin.cropAttachment(s.item,'3mm');
  assert.deepEqual(s.imported[0].collections,[15]);
  assert.equal(s.imported[0].parentItemID,undefined);
}));
test('engine failure does not import and cleans work folder', {skip:!python||!input},()=>withSandbox(async s=>{
  const bad=path.join(s.temp,'invalid.pdf');await fs.writeFile(bad,'bad');
  s.item.getFilePathAsync=async()=>bad;
  await assert.rejects(s.plugin.cropAttachment(s.item,'10'),/PDF 처리 실패/);
  assert.equal(s.imported.length,0);assert.equal(s.plugin.job,null);assert.equal(s.plugin.busy,false);
  assert.deepEqual(await fs.readdir(s.temp),['invalid.pdf']);
}));
test('import failure cleans temporary files and releases busy flag', {skip:!python||!input},()=>withSandbox(async s=>{
  s.context.Zotero.Attachments.importFromFile=async()=>{throw new Error('import rejected');};
  await assert.rejects(s.plugin.cropAttachment(s.item,'10'),/import rejected/);
  assert.equal(s.plugin.busy,false);assert.deepEqual(await fs.readdir(s.temp),[]);
}));

test('both annotation preservation and original removal default off',()=>withSandbox(async s=>{
  assert.equal(s.plugin.options().preserveAnnotations,false);
  assert.equal(s.plugin.options().removeOriginal,false);
  assert.equal(s.plugin.options().cropArxivStamp,true);
}));
test('arXiv preference can be independently disabled', {skip:!python||!input},()=>withSandbox(async s=>{
  s.prefs.set(s.plugin.pref+'cropArxivStamp',false);
  const execute=s.plugin.execute.bind(s.plugin);
  s.plugin.execute=async(command,args)=>{
    assert.ok(args.includes('--keep-arxiv-stamp'));
    return execute(command,args);
  };
  await s.plugin.cropAttachment(s.item,'10pt');
  assert.equal(s.plugin.options().preserveAnnotations,false);
  assert.equal(s.plugin.options().removeOriginal,false);
}));
for(const preserveAnnotations of [false,true]) for(const removeOriginal of [false,true]) {
  test(`independent options: preserve=${preserveAnnotations}, remove=${removeOriginal}`, {skip:!python||!input},()=>withSandbox(async s=>{
    const original=s.addAnnotation();
    s.prefs.set(s.plugin.pref+'preserveAnnotations',preserveAnnotations);
    s.prefs.set(s.plugin.pref+'removeOriginal',removeOriginal);
    const result=await s.plugin.cropAttachment(s.item,'10pt');
    assert.equal(result.report.preserves_coordinates,true);
    assert.equal(result.copiedAnnotations,preserveAnnotations?1:0);
    assert.equal(s.copies.length,preserveAnnotations?1:0);
    assert.deepEqual(s.trashed,removeOriginal?[s.item.id]:[]);
    assert.equal(result.attachment.note,preserveAnnotations?s.item.getNote():undefined);
    assert.deepEqual(result.attachment.tags,s.item.getTags());
    if(preserveAnnotations) {
      assert.equal(s.copies[0].parentID,result.attachment.id);
      assert.equal(s.copies[0].annotationPosition,original.annotationPosition);
      assert.equal(s.copies[0].annotationAuthorName,original.annotationAuthorName);
    }
  }));
}
test('annotation copy failure rolls back copies and retains original', {skip:!python||!input},()=>withSandbox(async s=>{
  s.addAnnotation();
  const second=s.addAnnotation('note');
  second.clone=()=>({save:async()=>{throw new Error('copy failed');}});
  await assert.rejects(s.plugin.cropAttachment(s.item,'10pt',{preserveAnnotations:true,removeOriginal:true}),/copy failed/);
  assert.deepEqual(s.copies,[]);
  assert.deepEqual(s.trashed,[101]);
  assert.equal(s.plugin.busy,false);
}));
test('original trash failure rolls back copies and retains original', {skip:!python||!input},()=>withSandbox(async s=>{
  s.addAnnotation();
  s.context.Zotero.Items.trash=async()=>{throw new Error('trash failed');};
  await assert.rejects(s.plugin.cropAttachment(s.item,'10pt',{preserveAnnotations:true,removeOriginal:true}),/trash failed/);
  assert.deepEqual(s.copies,[]);assert.deepEqual(s.trashed,[101]);
}));
test('annotations changed during processing prevent import and removal', {skip:!python||!input},()=>withSandbox(async s=>{
  const annotation=s.addAnnotation();
  const execute=s.plugin.execute.bind(s.plugin);
  s.plugin.execute=async(...args)=>{const run=await execute(...args);annotation.annotationPosition='{}';return run;};
  await assert.rejects(s.plugin.cropAttachment(s.item,'10pt',{preserveAnnotations:true,removeOriginal:true}),/변경/);
  assert.deepEqual(s.imported,[]);assert.deepEqual(s.trashed,[]);
}));
test('malformed annotation geometry prevents import and removal', {skip:!python||!input},()=>withSandbox(async s=>{
  s.addAnnotation().annotationPosition=JSON.stringify({pageIndex:0,unknown:[1,2]});
  await assert.rejects(s.plugin.cropAttachment(s.item,'10pt',{preserveAnnotations:true,removeOriginal:true}),/PDF 처리 실패/);
  assert.deepEqual(s.imported,[]);assert.deepEqual(s.trashed,[]);
}));
test('Zotero 10 menu contexts never read removed collectionTreeRow getter',()=>withSandbox(async s=>{
  await s.plugin.start({rootURI:'file:///plugin/'});
  const context={items:[s.item],collectionTreeRows:[{},{}],setVisible(v){this.visible=v;},setEnabled(v){this.enabled=v;}};
  Object.defineProperty(context,'collectionTreeRow',{get(){throw new Error('removed API');}});
  s.menus[0].menus[0].onShowing(null,context);
  assert.equal(context.visible,true);assert.equal(context.enabled,true);
}));
