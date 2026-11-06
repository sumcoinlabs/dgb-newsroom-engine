#!/usr/bin/env python3
"""Targeted, fail-closed patch of e888d39 newsroom editor.
Run only after installer verified the public editor Git HEAD and clean status.
Does not touch any existing draft JSON, password, or publication.
"""
from pathlib import Path
import sys

p=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/root/digibytewallet-org-github/tools/newsroom-editor.py')
s=p.read_text('utf-8')

def change(old,new):
    global s
    n=s.count(old)
    if n!=1:raise SystemExit('Editor patch aborted: unexpected source anchor ('+str(n)+') '+old[:90])
    s=s.replace(old,new)

change('import secrets\n','import secrets\nimport sqlite3\n')
change("IMAGES = HOME / 'images'\n", "IMAGES = HOME / 'images'\nSESSION_FILE = HOME / 'sessions.sqlite3'\n")

anchor='''def safe_slug(s):
'''
helpers='''def auth_revision():
    # A password change invalidates all surviving sessions, including saved ones.
    try:return hashlib.sha256(AUTH.read_bytes()).hexdigest()
    except OSError:return ''


def session_database():
    mkdir()
    with LOCK:
        with sqlite3.connect(str(SESSION_FILE),timeout=5) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL,auth_revision TEXT NOT NULL)')
            conn.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            conn.commit()
    os.chmod(str(SESSION_FILE),0o600)


def remember_session(key,session):
    session_database()
    with sqlite3.connect(str(SESSION_FILE),timeout=5) as conn:
        conn.execute('INSERT OR REPLACE INTO sessions (token_hash,csrf,expires,auth_revision) VALUES (?,?,?,?)',
             (key,session['csrf'],session['expires'],session['auth_revision']))
        conn.commit()


def forget_session(key):
    with LOCK:S.pop(key,None)
    if SESSION_FILE.exists():
        with sqlite3.connect(str(SESSION_FILE),timeout=5) as conn:
            conn.execute('DELETE FROM sessions WHERE token_hash=?',(key,));conn.commit()


def stored_session(key):
    if not SESSION_FILE.exists():return None
    with sqlite3.connect(str(SESSION_FILE),timeout=5) as conn:
        row=conn.execute('SELECT csrf,expires,auth_revision FROM sessions WHERE token_hash=?',(key,)).fetchone()
    if not row:return None
    return {'csrf':row[0],'expires':row[1],'auth_revision':row[2]}


'''
change(anchor,helpers+anchor)

old='''        with LOCK:
            session=S.get(h)
            if not session:return None
            if session['expires']<time.time():S.pop(h,None);return None
            return session'''
new='''        with LOCK:
            session=S.get(h) or stored_session(h)
            if not session:return None
            if session['expires']<time.time() or session.get('auth_revision') != auth_revision():
                forget_session(h)
                return None
            S[h]=session
            return session'''
change(old,new)

old='''                    S[hashlib.sha256(token.encode()).hexdigest()]={'csrf':secrets.token_hex(24),'expires':time.time()+8*3600}'''
new='''                    session={'csrf':secrets.token_hex(24),'expires':time.time()+8*3600,'auth_revision':auth_revision()}
                    token_hash=hashlib.sha256(token.encode()).hexdigest()
                    S[token_hash]=session
                    remember_session(token_hash,session)'''
change(old,new)
old="""                    with LOCK:S.pop(hashlib.sha256(m.group(1).encode()).hexdigest(),None)"""
new="""                    forget_session(hashlib.sha256(m.group(1).encode()).hexdigest())"""
change(old,new)

# Separate private verification metadata from the public article body.
old="""        if 'EDITORIAL WORKING DRAFT' in d.get('body','') or 'VERIFY BEFORE PUBLISHING' in d.get('body',''):
            raise ValueError('Editorial working draft cannot be published. Verify and replace draft warnings first.')"""
new="""        if 'EDITORIAL WORKING DRAFT' in d.get('body','') or 'VERIFY BEFORE PUBLISHING' in d.get('body',''):
            raise ValueError('Legacy working-draft warnings must be removed after factual review.')
        if d.get('review_required') is True and d.get('review_confirmed') is not True:
            raise ValueError('Verify the private source checklist and approve the AI draft before publishing.')"""
change(old,new)
# On save, reject malformed AI review metadata: private notes do not go into publisher HTML.
old='''                # Validate all textual fields before saving.
                markdown_source(v)'''
new='''                # Validate all textual fields and private editorial metadata before saving.
                for flag in ('review_required','review_confirmed'):
                    if flag in v and type(v[flag]) is not bool:
                        raise ValueError('Invalid private review status')
                checks=v.get('verification',[])
                if not isinstance(checks,list) or len(checks)>12 or not all(isinstance(item,str) and len(item)<300 for item in checks):
                    raise ValueError('Invalid private verification checklist')
                markdown_source(v)'''
change(old,new)
old="""const $=id=>document.getElementById(id), fields=['title','slug','summary','category','tags','body','image_alt','focus_x','focus_y'];let slugLocked=false;let preview=false;let csrf='';let imageData=null;let hasServerImage=false;"""
new="""const $=id=>document.getElementById(id), fields=['title','slug','summary','category','tags','body','image_alt','focus_x','focus_y'];let slugLocked=false;let preview=false;let csrf='';let imageData=null;let hasServerImage=false;let reviewRequired=false;let reviewVerification=[];"""
change(old,new)
old="""function data(){let o={};for(let key of fields)o[key]=$(key).value.trim();return o}"""
new="""function data(){let o={};for(let key of fields)o[key]=$(key).value.trim();o.review_required=reviewRequired;o.review_confirmed=reviewRequired?$('reviewchecked').checked:false;o.verification=reviewVerification;return o}"""
change(old,new)
old="""function apply(d){for(let key of fields)$(key).value=d[key]||((key==='focus_x'||key==='focus_y')?'50':'');$('slug').dataset.original=d.slug||'';slugLocked=!!d.slug;hasServerImage=!!d.has_image;imageData=null;$('image').value='';$('imgpreview').style.display='none';preview=false;$('preview').style.display='none';$('body').style.display='block';$('togglepreview').textContent='Preview';announce('Draft loaded')}"""
new="""function apply(d){for(let key of fields)$(key).value=d[key]||((key==='focus_x'||key==='focus_y')?'50':'');$('slug').dataset.original=d.slug||'';slugLocked=!!d.slug;hasServerImage=!!d.has_image;imageData=null;$('image').value='';$('imgpreview').style.display='none';preview=false;$('preview').style.display='none';$('body').style.display='block';$('togglepreview').textContent='Preview';reviewRequired=d.review_required===true;reviewVerification=Array.isArray(d.verification)?d.verification:[];$('reviewpanel').style.display=reviewRequired?'block':'none';$('reviewchecked').checked=reviewRequired&&d.review_confirmed===true;const details=$('reviewnotes');details.replaceChildren();reviewVerification.forEach(v=>{const li=document.createElement('li');li.textContent=v;details.append(li)});announce('Draft loaded')}"""
change(old,new)
# private review UI after article editing controls, no new third-party scripts
anchor='''<textarea id="body" placeholder="Write your story here. You can use the toolbar for headings, emphasis, links, and lists."></textarea><div id="preview"></div>'''
new='''<textarea id="body" placeholder="Write your story here. You can use the toolbar for headings, emphasis, links, and lists."></textarea><div id="preview"></div><div id="reviewpanel" class="panel" style="display:none;margin-top:14px;background:#112b3e"><strong>Private source verification</strong><p class="notice">These notes are private and are never added to the published article.</p><ul id="reviewnotes" style="font-size:13px;padding-left:20px"></ul><label style="display:flex;gap:10px;align-items:center"><input id="reviewchecked" type="checkbox" style="width:auto">I have checked the claims, links, release status and artwork.</label></div>'''
change(anchor,new)
old="""apply({title:d.title,slug:d.slug,summary:d.summary,body:d.body,category:d.category||'Development update',tags:d.tags||'DigiByte, DGB, DigiByte Wallet',image_alt:d.image_alt||'',focus_x:'50',focus_y:'50'});"""
new="""apply({title:d.title,slug:d.slug,summary:d.summary,body:d.body,category:d.category||'Development update',tags:d.tags||'DigiByte, DGB, DigiByte Wallet',image_alt:d.image_alt||'',focus_x:'50',focus_y:'50',review_required:d.review_required===true||d.ai_generated===true,review_confirmed:false,verification:d.verification||[]});"""
change(old,new)
# Public publish confirmation still required; private review status is checked server-side.
assert "if(!confirm('Publish this article publicly" in s
assert "event.origin!=='http://127.0.0.1:8878'" in s
assert "if path=='/api/publish'" in s
compile(s,str(p),'exec')
if '--check' not in sys.argv:
    p.write_text(s,'utf-8')
print('PASS: Editor patch checks'+(' (dry run)' if '--check' in sys.argv else ': changes written'))
