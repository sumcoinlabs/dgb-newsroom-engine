#!/usr/bin/env python3
"""Narrow, idempotent UI-only patch to the existing private editor.
The editor continues to own all public publishing and password checks.
"""
from pathlib import Path
P=Path('/root/digibytewallet-org-github/tools/newsroom-editor.py')
s=P.read_text(encoding='utf-8')

changes={
    '<button id="logout">Sign out</button>':
    '<a href="http://127.0.0.1:8878/" target="_blank" rel="noopener noreferrer" style="margin-right:16px">Story Radar ↗</a><button id="logout">Sign out</button>',
    "        if d.get('slug') != slug: raise ValueError('Draft mismatch')":
    "        if d.get('slug') != slug: raise ValueError('Draft mismatch')\n        if 'EDITORIAL WORKING DRAFT' in d.get('body','') or 'VERIFY BEFORE PUBLISHING' in d.get('body',''):\n            raise ValueError('Editorial working draft cannot be published. Verify and replace draft warnings first.')",
    "$('logout').onclick=async()=>{await api('/api/logout',{});location.href='/login'};":
    """$('logout').onclick=async()=>{await api('/api/logout',{});location.href='/login'};
// Accept only explicitly confirmed working drafts from the private SSH-tunneled Story Radar.
const dgbImportedTickets=new Map();
window.addEventListener('message',event=>{
  if(event.origin!=='http://127.0.0.1:8878'||!csrf)return;
  const msg=event.data;
  if(!msg||msg.type!=='dgb_engine_import'||msg.version!==1||typeof msg.ticket!=='string'||!/^dgb-[a-f0-9]{24}$/.test(msg.ticket))return;
  const d=msg.draft;
  if(!d||typeof d!=='object'||typeof d.title!=='string'||d.title.length>155||typeof d.slug!=='string'||!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(d.slug)||d.slug.length>85||typeof d.summary!=='string'||d.summary.length>360||typeof d.body!=='string'||d.body.length>100000)return;
  if(dgbImportedTickets.has(msg.ticket)){if(event.source)event.source.postMessage({type:'dgb_editor_imported',ticket:msg.ticket,accepted:dgbImportedTickets.get(msg.ticket)},event.origin);return;}
  let accepted=confirm('Import this researched working draft? Unsaved text currently in the editor will be replaced. It will NOT be published.');
  if(accepted){
    apply({title:d.title,slug:d.slug,summary:d.summary,body:d.body,category:d.category||'Development update',tags:d.tags||'DigiByte, DGB, DigiByte Wallet',image_alt:'',focus_x:'50',focus_y:'50'});
    announce('Working draft imported. Verify the sources, edit the text, add an original image and click Save draft.');
  }
  dgbImportedTickets.set(msg.ticket,accepted);
  if(event.source)event.source.postMessage({type:'dgb_editor_imported',ticket:msg.ticket,accepted:accepted},event.origin);
});""",
}
if 'const dgbImportedTickets=new Map();' in s:
    print('PASS: Private editor already integrated with Story Radar')
else:
    for old,new in changes.items():
        if s.count(old)!=1:
            raise SystemExit('Editor source drift detected; refusing patch at expected anchor')
        s=s.replace(old,new)
    compile(s,str(P),'exec')
    P.write_text(s,encoding='utf-8')
    print('PASS: Private editor now accepts confirmed local draft handoff; publication guard active')
