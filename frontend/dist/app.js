'use strict';
const $ = id => document.getElementById(id);
const config = window.VERICLOUD || {};
const live = config.mode === 'live';
const files = {id:null,selfie:null};
const urls = {};
let busy = false;
let applicationId = '';
let run = 0;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function error(message) {$('uploadError').textContent = message;}
function ready() {$('submit').disabled = busy || !files.id || !files.selfie || !$('consent').checked;}
function show(view) {['upload','processing','result'].forEach(x => $(x+'View').classList.toggle('hidden', x !== view)); ['step0','step1','step2'].forEach((id,i) => $(id).classList.toggle('active', i === ['upload','processing','result'].indexOf(view)));}
async function choose(kind,file) {
 if(!file || busy) return;
 if(!['image/jpeg','image/png'].includes(file.type) || !/\.(jpe?g|png)$/i.test(file.name)) {error('请选择 JPG、JPEG 或 PNG 图片。');return;}
 if(!file.size || file.size > 10*1024*1024) {error('图片不能为空，每张大小不能超过 10 MB。');return;}
 const url=URL.createObjectURL(file);
 const img=new Image(); img.alt=kind==='id'?'所选证件照片预览':'所选自拍预览';
 img.src=url;
 try {await img.decode();} catch {URL.revokeObjectURL(url);error('这张图片无法打开，请重新选择完整、未损坏的图片。');return;}
 if(busy) {URL.revokeObjectURL(url);return;}
 if(urls[kind]) URL.revokeObjectURL(urls[kind]);
 urls[kind]=url;files[kind]=file;
 const text=document.createElement('span'); text.className='filename';text.textContent=file.name;
 const hint=document.createElement('small');hint.textContent='已选择 · 点击更换';
 $(kind+'Preview').replaceChildren(img,text,hint); error('');ready();
}
for (const kind of ['id','selfie']) {
 $(kind+'File').addEventListener('change',e=>choose(kind,e.target.files[0]));
 const drop=$(kind+'Drop');
 ['dragenter','dragover'].forEach(name=>drop.addEventListener(name,e=>{e.preventDefault();drop.classList.add('drag');}));
 ['dragleave','drop'].forEach(name=>drop.addEventListener(name,e=>{e.preventDefault();drop.classList.remove('drag');}));
 drop.addEventListener('drop',e=>choose(kind,e.dataTransfer.files[0]));
}
$('consent').addEventListener('change',ready);
$('helpButton').addEventListener('click',()=>$('help').showModal());
$('closeHelp').addEventListener('click',()=>$('help').close());
function progress(index) {
 for(let i=0;i<4;i++) {const el=$('p'+i);el.classList.toggle('done',i<index);el.classList.toggle('running',i===index);el.querySelector('.state-icon').textContent=i<index?'✓':i===index?'':String(i+1);}
}
function identifier() {
 if(crypto.randomUUID) return crypto.randomUUID();
 const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const h=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
function result(data) {
 const status=data.review_status;
 if(!['PASS','FAIL','NEEDS_HUMAN_REVIEW'].includes(status)) throw new Error('后端返回了无法识别的结果，请联系项目负责人。');
 const labels={PASS:'验证通过',FAIL:'验证未通过',NEEDS_HUMAN_REVIEW:'需要人工审核'};
 const reasons={auto_approved:'证件及人脸比对通过',ocr_failed:'证件信息识别失败',id_expired:'证件已过期',face_error:'无法完成人脸比对',similarity_below_80:'人脸相似度不足，需要进一步确认'};
 $('applicationId').textContent=applicationId;
 $('demoNotice').classList.toggle('hidden',live);
 $('resultTitle').textContent=live?labels[status]:'演示流程已完成';
 $('resultDescription').textContent=live?'本次验证结果已返回。':'您的照片没有上传，也没有进行真实识别。';
 $('resultSymbol').textContent=status==='PASS'?'✓':status==='FAIL'?'×':'…';
 $('reviewStatus').textContent=live?labels[status]:'演示：通过';
 $('reason').textContent=live?(reasons[data.reason]||data.reason||'未提供说明'):'模拟流程展示';
 $('processedAt').textContent=data.processed_at?new Date(data.processed_at).toLocaleString('zh-CN',{hour12:false}):'未提供';
 show('result');
}
$('submit').addEventListener('click',async()=>{
 if(busy || $('submit').disabled) return;
 const adapter=config.adapter;
 if(live && (!adapter || typeof adapter.createApplication!=='function'||typeof adapter.getResult!=='function')) {error('真实验证接口尚未配置，请联系项目负责人。');return;}
 busy=true;ready();applicationId=identifier();const current=++run;
 $('processError').textContent='';$('processingStatus').textContent='';$('back').classList.add('hidden');show('processing');progress(0);
 try {
  if(!live) {
   for(let i=0;i<4;i++){progress(i);await delay(850);}
   result({review_status:'PASS',processed_at:new Date().toISOString()});
  } else {
   const payload=await adapter.createApplication({application_id:applicationId,id_card_extension:extension(files.id),selfie_extension:extension(files.selfie)});
   if(!payload || !payload.id_card_url || !payload.selfie_url) throw new Error('上传接口没有返回完整的上传地址。');
   // 必须先完成证件上传，再上传自拍；自拍触发现有 AWS 流水线。
   await upload(payload.id_card_url,files.id);await upload(payload.selfie_url,files.selfie);progress(1);
   $('processingStatus').textContent='照片已上传，正在等待后端处理。';
   const deadline=Date.now()+120000;
   while(Date.now()<deadline && run===current) {
    const data=await adapter.getResult({application_id:applicationId});
    if(data && ['PASS','FAIL','NEEDS_HUMAN_REVIEW'].includes(data.review_status)){progress(4);result(data);return;}
    await delay(2500);
   }
   throw new Error('等待结果超时。申请编号：'+applicationId+'。请联系项目负责人查询此申请，重新提交会创建新的申请。');
  }
 } catch(e) {$('processError').textContent=e.message||'处理未完成，请稍后再试。';$('processingStatus').textContent='当前处理已停止。';progress(-1);$('back').classList.remove('hidden');}
 finally {busy=false;ready();}
});
function extension(file){return '.'+file.name.split('.').pop().toLowerCase();}
async function upload(url,file){if(!/^https:\/\//i.test(url))throw new Error('上传地址必须使用 HTTPS。');const response=await fetch(url,{method:'PUT',body:file,signal:AbortSignal.timeout(60000)});if(!response.ok)throw new Error('照片上传失败（'+response.status+'），请检查上传授权和跨域配置。');}
$('back').addEventListener('click',()=>show('upload'));
$('restart').addEventListener('click',()=>{for(const kind of ['id','selfie']){if(urls[kind])URL.revokeObjectURL(urls[kind]);files[kind]=null;$(kind+'File').value='';const strong=document.createElement('strong');strong.textContent=kind==='id'?'上传身份证照片':'上传正面自拍';const small=document.createElement('small');small.textContent='点击选择，或将图片拖到这里';$(kind+'Preview').replaceChildren(strong,small);}$('consent').checked=false;error('');ready();show('upload');});
$('copyId').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(applicationId);$('copyId').textContent='已复制';setTimeout(()=>$('copyId').textContent='复制申请编号',1800);}catch{$('copyId').textContent='请长按或选中上方编号复制';}});
if(live){$('modeLabel').textContent='真实验证';$('modeNote').textContent='提交后将上传至项目配置的验证服务，并进行真实识别';$('processingCaption').textContent='照片上传后由后端核验，请等待结果。';}
