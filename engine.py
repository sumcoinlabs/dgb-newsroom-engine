#!/usr/bin/env python3
"""DigiByte Newsroom Engine v0.1: review-first, source-linked discovery.

No automated public publishing, social scraping, image scraping, or credentials.
Python 3.8+ stdlib only. Runs as unprivileged user on loopback.
"""
import argparse
import datetime as dt
from contextlib import closing
import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

APP = Path(__file__).resolve().parent
SOURCES = APP / 'sources.json'
STATE = Path(os.environ.get('DGB_ENGINE_STATE', '/var/lib/dgb-newsroom-engine'))
DBFILE = STATE / 'stories.sqlite3'
PORT = int(os.environ.get('DGB_ENGINE_PORT', '8770'))
MAX_RSS = 1_500_000
MAX_POST = 12_000
CSRF = secrets.token_hex(24)
LOCK = threading.RLock()
IS_SCANNING = False
SCAN_REPORT = {'last_scan':None,'new':0,'errors':[],'running':False}
ALLOWED_HOSTS = frozenset(('github.com','api.github.com'))
ALLOWED_MANUAL_DOMAINS = frozenset(('github.com','reddit.com','x.com','twitter.com','facebook.com','digibyte.org','digibyte.io','digibytewallet.org','www.digibytewallet.org','medium.com','youtube.com','youtu.be'))
TITLE_LIMIT = 180
ATOM = '{http://www.w3.org/2005/Atom}'

class StripHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments = []
    def handle_data(self, d):
        self.fragments.append(d)

def clean(raw, limit=700):
    p = StripHTML()
    p.feed(str(raw or ''))
    return re.sub(r'\s+', ' ', html.unescape(' '.join(p.fragments))).strip()[:limit]

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def parse_time(st):
    if not st: return ''
    try:
        return dt.datetime.fromisoformat(str(st).replace('Z','+00:00')).isoformat()
    except ValueError:
        return str(st)[:40]

def hostname(url):
    p=urlparse(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None,443):
        raise ValueError('Expected safe HTTPS URL')
    host=(p.hostname or '').lower()
    if not host or host.endswith('.'):
        raise ValueError('Invalid hostname')
    try: ipaddress.ip_address(host)
    except ValueError: pass
    else: raise ValueError('IP addresses forbidden')
    return host

def allowed_manual(url):
    try:
        host=hostname(url)
        return host in ALLOWED_MANUAL_DOMAINS or host.endswith('.reddit.com') or host.endswith('.facebook.com') or host.endswith('.digibyte.org')
    except (ValueError, TypeError):
        return False

def trusted_source(url):
    return hostname(url) in ALLOWED_HOSTS

def get_db():
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    conn=sqlite3.connect(str(DBFILE),timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS stories (
       id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
       title TEXT NOT NULL, url TEXT UNIQUE NOT NULL, summary TEXT NOT NULL,
       published TEXT, first_seen TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
       manual INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS drafts (
       story_id TEXT PRIMARY KEY REFERENCES stories(id), content TEXT NOT NULL,
       generated_at TEXT NOT NULL)''')
    conn.commit()
    return conn

def atom_entries(raw, source, kind):
    if len(raw)>MAX_RSS or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unacceptable XML feed')
    root=ET.fromstring(raw)
    if root.tag != ATOM+'feed':
        raise ValueError('Expected Atom feed')
    for e in root.findall(ATOM+'entry')[:20]:
        url=''
        for link in e.findall(ATOM+'link'):
            if link.get('rel','alternate')=='alternate' and link.get('href','').startswith('https://'):
                url=link.get('href','');break
        if not url or not trusted_source(url): continue
        title=clean(e.findtext(ATOM+'title') or '',TITLE_LIMIT)
        if not title: continue
        summary=clean(e.findtext(ATOM+'summary') or e.findtext(ATOM+'content') or '',1000)
        published=parse_time(e.findtext(ATOM+'published') or e.findtext(ATOM+'updated'))
        yield {'id':hashlib.sha256(url.encode()).hexdigest()[:32], 'title':title,'url':url,
               'summary':summary,'published':published,'source':source,'kind':kind}

def load_sources():
    result=json.loads(SOURCES.read_text('utf-8'))
    if not isinstance(result,list) or len(result)>20: raise ValueError('Invalid source configuration')
    for row in result:
        if set(row) != {'name','url','kind'} or row['kind'] not in ('release','development') or not trusted_source(row['url']):
            raise ValueError('Unsafe source configuration')
    return result

def fetch_feed(url):
    if not trusted_source(url): raise ValueError('Source not allowlisted')
    req=Request(url,headers={'User-Agent':'DigiByteNewsroomResearch/0.1 (+https://www.digibytewallet.org/news/about.html)','Accept':'application/atom+xml,application/xml;q=0.8'})
    with urlopen(req,timeout=9) as resp:
        # Refuse cross-domain redirects and non-200 responses.
        if not trusted_source(resp.url): raise ValueError('Unexpected feed redirect')
        raw=resp.read(MAX_RSS+1)
    if len(raw)>MAX_RSS:raise ValueError('Feed exceeded size limit')
    return raw

def scan_once(fetcher=fetch_feed):
    global IS_SCANNING,SCAN_REPORT
    with LOCK:
        if IS_SCANNING: return {'running':True}
        IS_SCANNING=True
        SCAN_REPORT['running']=True
    new=0; errors=[]
    try:
        with closing(get_db()) as conn:
            for src in load_sources():
                try:
                    raw=fetcher(src['url'])
                    for x in atom_entries(raw,src['name'],src['kind']):
                        cur=conn.execute('''INSERT OR IGNORE INTO stories (id,source,kind,title,url,summary,published,first_seen)
                                VALUES (:id,:source,:kind,:title,:url,:summary,:published,:first_seen)''',dict(x,first_seen=now()))
                        new += cur.rowcount
                    conn.commit()
                except Exception as e:
                    errors.append(src['name']+': '+type(e).__name__+': '+str(e)[:170])
            # Cap at 1500 old dismissed leads, never discard active leads.
            conn.execute("DELETE FROM stories WHERE status='dismissed' AND id IN (SELECT id FROM stories WHERE status='dismissed' ORDER BY first_seen DESC LIMIT -1 OFFSET 1500)")
            conn.commit()
    finally:
        with LOCK:
            IS_SCANNING=False
            SCAN_REPORT={'last_scan':now(),'new':new,'errors':errors,'running':False}
    return dict(SCAN_REPORT)

def scan_worker():
    try:scan_once()
    except Exception as exc:
        with LOCK:
            global SCAN_REPORT,IS_SCANNING
            IS_SCANNING=False
            SCAN_REPORT={'last_scan':now(),'new':0,'errors':['Scanner: '+type(exc).__name__],'running':False}

def start_scan():
    with LOCK:
        if IS_SCANNING:return False
    threading.Thread(target=scan_worker,daemon=True,name='feed-scan').start()
    return True

def story_list(limit=120):
    with closing(get_db()) as c:
        return [dict(row) for row in c.execute("SELECT * FROM stories ORDER BY CASE status WHEN 'new' THEN 0 WHEN 'drafted' THEN 1 ELSE 2 END, COALESCE(published,first_seen) DESC LIMIT ?",(limit,))]

def make_slug(text):
    v=re.sub(r'[^a-z0-9]+','-',text.lower()).strip('-')[:76].strip('-')
    return v or 'digibyte-development-update'

def make_draft(story):
    """Conservative source-briefing template, not a finished researched article."""
    title=story['title'].strip()[:145]
    release=(story['kind']=='release' and story['manual']==0)
    action='published a release entry' if release else 'recorded an update'
    summary=("A source-linked overview of the development activity titled '"+title+"', with follow-up verification still required.")[:300]
    url=story['url']
    name=story['source']
    when=story.get('published') or 'Publication timestamp not available'
    text=(
        "**EDITORIAL WORKING DRAFT — VERIFY BEFORE PUBLISHING.**\n\n"
        "The source ["+name+"]("+url+") "+action+" titled **"+title+"**. "
        "The original entry is dated "+when+". This information comes from the linked source; "
        "it has not yet been independently verified for publication.\n\n"
        "## What the source says\n\n"
        + (story['summary'][:650] if story['summary'] else "The source preview does not include enough detail for independent reporting.")
        + "\n\n## What needs verification\n\n"
        "Before publishing, inspect the original source, verify its actual claims and publication status, "
        "confirm version numbers, and find corroborating evidence where needed. "
        "A commit does not necessarily indicate a shipped release.\n\n"
        "## Reference\n\n"
        "- ["+name+" — original announcement or activity]("+url+")\n\n"
        "Remove this editorial warning and replace unverified material with accurate, independently written reporting before publication."
    )
    return {'title':title,'slug':make_slug(title), 'summary':summary,'category':'Release' if release else 'Development update',
            'tags':'DigiByte, DGB, DigiByte Wallet','image_alt':'','focus_x':'50','focus_y':'50','body':text}

def draft_for(story_id):
    if not re.fullmatch(r'[0-9a-f]{32}',story_id): raise ValueError('Invalid story id')
    with closing(get_db()) as c:
        story=c.execute('SELECT * FROM stories WHERE id=?',(story_id,)).fetchone()
        if not story:raise ValueError('Story not found')
        if story['status']=='dismissed':raise ValueError('Dismissed story')
        draft=make_draft(dict(story))
        c.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?)',(story_id,json.dumps(draft,ensure_ascii=False),now()))
        c.execute("UPDATE stories SET status='drafted' WHERE id=?",(story_id,))
        c.commit()
    return draft

def get_draft(story_id):
    with closing(get_db()) as c:
        r=c.execute('SELECT content FROM drafts WHERE story_id=?',(story_id,)).fetchone()
        return json.loads(r['content']) if r else None

def dismiss(story_id):
    if not re.fullmatch(r'[0-9a-f]{32}',story_id):raise ValueError('Invalid id')
    with closing(get_db()) as c:
        cur=c.execute("UPDATE stories SET status='dismissed' WHERE id=?",(story_id,))
        if cur.rowcount!=1:raise ValueError('Story not found')
        c.commit()

def add_manual(obj):
    title=str(obj.get('title','')).strip()
    url=str(obj.get('url','')).strip()
    note=str(obj.get('note','')).strip()
    if not (10<=len(title)<=TITLE_LIMIT):raise ValueError('Title must be 10-180 characters')
    if not allowed_manual(url) or len(url)>1000:raise ValueError('Use an approved HTTPS source link')
    if len(note)>1000:raise ValueError('Note too long')
    record={'id':hashlib.sha256(url.encode()).hexdigest()[:32], 'source':hostname(url), 'kind':'lead',
            'title':title,'url':url,'summary':note or 'Manually collected lead. Verify before writing.', 'published':'', 'first_seen':now()}
    with closing(get_db()) as c:
        c.execute('''INSERT OR IGNORE INTO stories (id,source,kind,title,url,summary,published,first_seen,manual)
                     VALUES (:id,:source,:kind,:title,:url,:summary,:published,:first_seen,1)''',record)
        c.commit()
    return record

def audit_site():
    """Independent public HTTP checks; no access to production filesystem."""
    pages=[
      'https://www.digibytewallet.org/news/',
      'https://www.digibytewallet.org/news/digicoinlib-0-0-3-release.html',
      'https://www.digibytewallet.org/news/wallet-0-1-5-preview.html',
      'https://www.digibytewallet.org/news/digibyte-wallet-256-bit-recovery-security-updates.html',
    ]
    output=[]
    for url in pages:
        result={'url':url,'ok':False}
        try:
            req=Request(url,headers={'User-Agent':'DigiByteNewsroomAudit/0.1'})
            with urlopen(req,timeout=9) as response:
                if urlparse(response.url).hostname not in ('www.digibytewallet.org','digibytewallet.org'):
                    raise ValueError('Unexpected redirect')
                raw=response.read(350_000).decode('utf-8','replace')
                result['http']=response.status
                result['canonical']='rel="canonical"' in raw or bool(re.search(r'<link\s+[^>]*rel=["\']canonical["\']',raw,re.I))
                result['structured']='application/ld+json' in raw and ('NewsArticle' in raw or 'ItemList' in raw)
                result['image']='og:image' in raw
                result['indexable']='noindex' not in raw.lower()
                result['ok']=all((result['http']==200,result['canonical'],result['structured'],result['image'],result['indexable']))
        except Exception as e:result['error']=type(e).__name__+': '+str(e)[:120]
        output.append(result)
    return output

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def respond(self,status,obj,typ='application/json; charset=utf-8'):
        body=obj.encode('utf-8') if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',typ)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store, max-age=0')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
        if status>=400 and self.command=='POST':
            self.send_header('Connection','close');self.close_connection=True
        self.end_headers();self.wfile.write(body)
    def guard(self,mutate=False):
        host=self.headers.get('Host','')
        if not re.fullmatch(r'(?:127\.0\.0\.1|localhost):\d{1,5}',host) or self.client_address[0] not in ('127.0.0.1','::1'):
            self.respond(403,{'error':'Local access only'});return False
        if mutate and (self.headers.get('Origin')!='http://'+host or self.headers.get('X-Newsroom-CSRF')!=CSRF):
            self.respond(403,{'error':'Invalid origin or CSRF'});return False
        return True
    def do_GET(self):
        if not self.guard():return
        path=urlparse(self.path).path
        if path=='/':
            page=(APP/'dashboard.html').read_text('utf-8').replace('__CSRF_TOKEN__',CSRF)
            return self.respond(200,page,'text/html; charset=utf-8')
        if path=='/api/stories':
            with LOCK:info=dict(SCAN_REPORT)
            return self.respond(200,{'stories':story_list(),'scan':info,'sources':[{'name':s['name'],'kind':s['kind']} for s in load_sources()]})
        if path=='/api/draft':
            query=self.path.split('?',1)[-1]
            from urllib.parse import parse_qs
            st=parse_qs(query).get('id',[''])[0]
            if not re.fullmatch(r'[0-9a-f]{32}',st):return self.respond(400,{'error':'Invalid id'})
            return self.respond(200,{'draft':get_draft(st)})
        if path=='/api/health':return self.respond(200,{'version':'0.1.0','mode':'review-only','publishing_enabled':False,'automated_social_scraping':False})
        if path=='/api/audit':return self.respond(200,{'results':audit_site(),'checked_at':now()})
        return self.respond(404,{'error':'Not found'})
    def do_POST(self):
        if not self.guard(mutate=True):return
        try:
            size=int(self.headers.get('Content-Length','-1'))
            if not (0<=size<=MAX_POST):return self.respond(413,{'error':'Request too large'})
            body=json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(body,dict):raise ValueError('Expected JSON object')
            p=urlparse(self.path).path
            if p=='/api/scan':return self.respond(202,{'started':start_scan()})
            if p=='/api/manual':return self.respond(201,{'story':add_manual(body)})
            if p=='/api/draft':return self.respond(200,{'draft':draft_for(str(body.get('id','')))})
            if p=='/api/dismiss':
                dismiss(str(body.get('id','')))
                return self.respond(200,{'ok':True})
            return self.respond(404,{'error':'Not found'})
        except (ValueError,TypeError,sqlite3.Error) as e:
            return self.respond(400,{'error':str(e)[:200]})

def background_loop():
    time.sleep(2)
    while True:
        scan_worker()
        time.sleep(1800)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['serve','scan','status'])
    a=parser.parse_args()
    if a.command=='scan':
        print(json.dumps(scan_once(),indent=2));return
    if a.command=='status':
        print(json.dumps({'stories':len(story_list()),'sources':load_sources(),'state':str(STATE)},indent=2));return
    if not (1024<=PORT<=65535):raise SystemExit('Invalid port')
    get_db().close()
    thread=threading.Thread(target=background_loop,daemon=True,name='monitor')
    thread.start()
    Server(('127.0.0.1',PORT),Handler).serve_forever()

if __name__=='__main__':main()
