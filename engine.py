#!/usr/bin/env python3
"""Crypto Newsroom Engine v0.5: source-checked private editorial desk, private AI review queue.

No automated public publishing, social scraping, image scraping, or credentials.
Python 3.8+ stdlib only. Runs as unprivileged user on loopback.
"""
import argparse
import ai_writer
import editorial
import artwork
import datetime as dt
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, as_completed
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
AI_DAY_LIMIT = 8
AI_STORY_LIMIT = 2
AUTO_DAILY_LIMIT = 2
AI_TOKEN_DAILY_LIMIT = 50000
AI_RESERVE_TOKENS = ai_writer.MAX_PER_REQUEST_TOKENS
AUTO_LOCK = threading.Lock()
CSRF = secrets.token_hex(24)
LOCK = threading.RLock()
IS_SCANNING = False
SCAN_REPORT = {'last_scan':None,'new':0,'errors':[],'running':False}
ALLOWED_HOSTS = frozenset(('github.com','api.github.com'))
ALLOWED_MANUAL_DOMAINS = frozenset(('github.com','reddit.com','x.com','twitter.com','facebook.com','digibyte.org','digibyte.io','digibytewallet.org','www.digibytewallet.org','medium.com','youtube.com','youtu.be','sumcoin.org','www.sumcoin.org','sumcoin.space','bitcoin.org','www.bitcoin.org','bitcoinmagazine.com','decrypt.co','coindesk.com','www.coindesk.com','ethereum.org','www.ethereum.org'))
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
    conn.execute('''CREATE TABLE IF NOT EXISTS ai_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT, story_id TEXT NOT NULL,
      started_at TEXT NOT NULL, date_utc TEXT NOT NULL,
      status TEXT NOT NULL, model TEXT NOT NULL)''')
    existing={row[1] for row in conn.execute('PRAGMA table_info(ai_requests)')}
    for col,kind in [('actor',"TEXT NOT NULL DEFAULT 'manual'"),('prompt_tokens','INTEGER NOT NULL DEFAULT 0'),('completion_tokens','INTEGER NOT NULL DEFAULT 0'),('reserved_tokens','INTEGER NOT NULL DEFAULT 0')]:
        if col not in existing:conn.execute('ALTER TABLE ai_requests ADD COLUMN '+col+' '+kind)
    conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS source_health (
       name TEXT PRIMARY KEY, url TEXT NOT NULL, last_checked TEXT,
       last_success TEXT, last_error TEXT, count INTEGER NOT NULL DEFAULT 0,
       new_count INTEGER NOT NULL DEFAULT 0, last_entry TEXT,
       status TEXT NOT NULL DEFAULT 'unchecked')''')
    conn.execute("INSERT OR IGNORE INTO settings VALUES ('auto_draft','true')")
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
    if not isinstance(result,list) or len(result)>50: raise ValueError('Invalid source configuration')
    if len(set(r.get('name') for r in result if isinstance(r,dict)))!=len(result):raise ValueError('Duplicate source name')
    for row in result:
        if not isinstance(row,dict) or set(row) != {'name','url','kind'} or row['kind'] not in ('release','development','news'):
            raise ValueError('Unsafe source configuration')
        if row['kind']=='news':
            if hostname(row['url']) not in editorial.RSS_HOSTS:raise ValueError('Unsafe RSS feed')
        elif not trusted_source(row['url']):raise ValueError('Unsafe source configuration')
    return result

class SafeFeedRedirect(__import__('urllib.request',fromlist=['HTTPRedirectHandler']).HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        old=hostname(req.full_url);new=hostname(newurl)
        # Same publisher only; never follow a feed URL to arbitrary domains or private IPs.
        if old.replace('www.','',1)!=new.replace('www.','',1):
            raise ValueError('Cross-publisher feed redirect denied')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch_feed(url):
    if not trusted_source(url) and hostname(url) not in editorial.RSS_HOSTS:raise ValueError('Source not allowlisted')
    req=Request(url,headers={'User-Agent':'DigiByteNewsroomResearch/0.4 (+https://www.digibytewallet.org/news/about.html)','Accept':'application/atom+xml,application/rss+xml,application/xml;q=0.8'})
    from urllib.request import build_opener
    with build_opener(SafeFeedRedirect()).open(req,timeout=9) as resp:
        # Must remain the same allowed publisher even after safe redirect handling.
        actual=hostname(resp.geturl())
        if actual.replace('www.','',1)!=hostname(url).replace('www.','',1):raise ValueError('Unexpected feed redirect')
        raw=resp.read(MAX_RSS+1)
    if len(raw)>MAX_RSS:raise ValueError('Feed exceeded size limit')
    return raw

def _source_scan(src,fetcher):
    # Network and XML work outside SQLite; independent feeds can run concurrently.
    started=now()
    try:
        raw=fetcher(src['url'])
        parsed=list(editorial.rss_entries(raw,src) if src['kind']=='news' else atom_entries(raw,src['name'],src['kind']))
        latest=max((e.get('published') or '' for e in parsed),default='')
        return {'source':src,'started':started,'entries':parsed,'latest':latest,'error':''}
    except Exception as e:
        return {'source':src,'started':started,'entries':[],'latest':'','error':type(e).__name__+': '+str(e)[:150]}

def _stale_feed_date(stamp):
    try:
        published=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
        return published.tzinfo is not None and (dt.datetime.now(dt.timezone.utc)-published).days>14
    except (TypeError,ValueError,AttributeError):return True

def scan_once(fetcher=fetch_feed):
    global IS_SCANNING,SCAN_REPORT
    with LOCK:
        if IS_SCANNING:return {'running':True}
        IS_SCANNING=True
        SCAN_REPORT['running']=True
    new=0;errors=[]
    try:
        sources=load_sources()
        # Bounded concurrency avoids 35 x 9-second scans on a small VM.
        with ThreadPoolExecutor(max_workers=5,thread_name_prefix='feed') as pool:
            futures=[pool.submit(_source_scan,src,fetcher) for src in sources]
            results=[future.result() for future in as_completed(futures)]
        with closing(get_db()) as conn:
            for result in results:
                src=result['source'];name=src['name'];count=0
                if result['error']:
                    errors.append(name+': '+result['error'])
                else:
                    for item in result['entries']:
                        cursor=conn.execute('''INSERT OR IGNORE INTO stories
                        (id,source,kind,title,url,summary,published,first_seen)
                        VALUES (:id,:source,:kind,:title,:url,:summary,:published,:first_seen)''',dict(item,first_seen=now()))
                        count+=cursor.rowcount
                    new+=count
                conn.execute('''INSERT INTO source_health (name,url,last_checked,last_success,last_error,count,new_count,last_entry,status)
                  VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                   url=excluded.url,last_checked=excluded.last_checked,
                   last_success=COALESCE(excluded.last_success,source_health.last_success),
                   last_error=excluded.last_error,count=excluded.count,new_count=excluded.new_count,
                   last_entry=CASE WHEN excluded.last_entry!='' THEN excluded.last_entry ELSE source_health.last_entry END,
                   status=excluded.status''',
                  (name,src['url'],result['started'],result['started'] if not result['error'] else None,
                   result['error'],len(result['entries']),count,result['latest'],
                   'error' if result['error'] else 'empty' if not result['entries'] else
                   'stale' if result['latest'] and _stale_feed_date(result['latest']) else 'ok'))
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

def story_list(limit=350):
    with closing(get_db()) as c:
        return [dict(row) for row in c.execute("SELECT * FROM stories ORDER BY CASE status WHEN 'drafted' THEN 0 WHEN 'new' THEN 1 ELSE 2 END, COALESCE(published,first_seen) DESC LIMIT ?",(limit,))]

def grouped_queue():
    rows=story_list(1400)
    # Preserve and expose archived leads instead of pretending old releases are breaking news.
    active=editorial.group_stories([row for row in rows if row['status']!='dismissed'])
    dismissed=editorial.group_stories([row for row in rows if row['status']=='dismissed'])
    queue=([r for r in active if not r['archived'] and not r.get('off_topic')][:160]
           +[r for r in active if r['archived'] or r.get('off_topic')][:80]
           +dismissed[:30])
    with closing(get_db()) as c:
        drafts={row['story_id']:json.loads(row['content']) for row in c.execute('SELECT story_id,content FROM drafts')}
    for item in queue:
        draft=drafts.get(item['id'])
        item['prepared_by_ai']=bool(draft and draft.get('ai_generated'))
        item['review_status']='AI draft ready' if item['prepared_by_ai'] else 'Research outline' if draft else ''
    return queue

def get_settings():
    with closing(get_db()) as c:
        row=c.execute("SELECT value FROM settings WHERE key='auto_draft'").fetchone()
    return {'auto_draft': bool(row and row['value']=='true'), 'auto_daily_limit':AUTO_DAILY_LIMIT,
            'public_auto_publish':False,'rss_headlines_only':True}

def set_settings(data):
    if set(data)!={'auto_draft'} or type(data['auto_draft']) is not bool:
        raise ValueError('Expected an auto_draft true/false setting')
    with closing(get_db()) as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES ('auto_draft',?)",('true' if data['auto_draft'] else 'false',))
        c.commit()
    return get_settings()


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
    topic=editorial.topic(story)
    tags={'DigiByte':'DigiByte, DGB, DigiByte Wallet','Bitcoin':'Bitcoin, BTC, Cryptocurrency',
          'Sumcoin':'Sumcoin, SUM, Cryptocurrency','Ethereum':'Ethereum, ETH, Cryptocurrency'}.get(topic,'Cryptocurrency, Blockchain')
    return {'title':title,'slug':make_slug(title), 'summary':summary,'category':'Release' if release else 'Development update',
            'tags':tags,'image_alt':'Original abstract blockchain network artwork for '+topic+' coverage',
            'focus_x':'50','focus_y':'50','body':text}

def normalized_draft(draft):
    """Render legacy AI drafts without embedded editorial notes; never alter stored SQLite."""
    if not isinstance(draft,dict) or not draft.get('ai_generated'):
        return draft
    body=draft.get('body','')
    banner='**EDITORIAL WORKING DRAFT — VERIFY BEFORE PUBLISHING.**'
    boundary='\n\n## Source and verification\n\n'
    if not body.startswith(banner) or boundary not in body:return draft
    article,foot=body[len(banner):].split(boundary,1)
    source=re.search(r'Original source: (\[[^\]]{1,160}\]\(https://github\.com/[^)]+\))',foot)
    if not source:return draft
    checks=[]
    for line in foot.splitlines():
        if line.startswith('- '):checks.append(line[2:][:240])
    result=dict(draft)
    result['body']=article.strip()+'\n\n## Original source\n\n'+source.group(1)
    result['verification']=checks[:10]
    result['review_required']=True
    result['review_confirmed']=False
    result['legacy_normalized']=True
    return result

def draft_for(story_id):
    if not re.fullmatch(r'[0-9a-f]{32}',story_id): raise ValueError('Invalid story id')
    with closing(get_db()) as c:
        story=c.execute('SELECT * FROM stories WHERE id=?',(story_id,)).fetchone()
        if not story:raise ValueError('Story not found')
        if story['status']=='dismissed':raise ValueError('Dismissed story')
        stored=c.execute('SELECT content FROM drafts WHERE story_id=?',(story_id,)).fetchone()
        if stored:
            draft=normalized_draft(json.loads(stored['content']))
        else:
            draft=make_draft(dict(story))
            c.execute('INSERT INTO drafts VALUES (?,?,?)',(story_id,json.dumps(draft,ensure_ascii=False),now()))
            c.execute("UPDATE stories SET status='drafted' WHERE id=?",(story_id,))
            c.commit()
    return draft

def get_draft(story_id):
    with closing(get_db()) as c:
        r=c.execute('SELECT content FROM drafts WHERE story_id=?',(story_id,)).fetchone()
        return normalized_draft(json.loads(r['content'])) if r else None

def ai_usage(story_id=None):
    day=dt.datetime.now(dt.timezone.utc).date().isoformat()
    with closing(get_db()) as c:
        used=c.execute('SELECT COUNT(*) FROM ai_requests WHERE date_utc=?',(day,)).fetchone()[0]
        by_story=(c.execute('SELECT COUNT(*) FROM ai_requests WHERE story_id=?',(story_id,)).fetchone()[0]
                  if story_id else 0)
        auto_used=c.execute("SELECT COUNT(*) FROM ai_requests WHERE date_utc=? AND actor='auto'",(day,)).fetchone()[0]
        prompt,completion,committed=c.execute('''SELECT COALESCE(SUM(prompt_tokens),0),COALESCE(SUM(completion_tokens),0),
             COALESCE(SUM(CASE WHEN status='complete' AND prompt_tokens+completion_tokens>0
                 THEN MAX(reserved_tokens, prompt_tokens+completion_tokens) ELSE reserved_tokens END),0)
             FROM ai_requests WHERE date_utc=?''',(day,)).fetchone()
        uncertain=c.execute("SELECT COUNT(*) FROM ai_requests WHERE date_utc=? AND status!='complete'",(day,)).fetchone()[0]
    return {'daily_used':used,'daily_limit':AI_DAY_LIMIT,'story_used':by_story,'story_limit':AI_STORY_LIMIT,
            'auto_used':auto_used,'auto_limit':AUTO_DAILY_LIMIT,'tokens_used':prompt+completion,
            'tokens_committed':committed, 'unverified_attempts':uncertain,
            'token_daily_budget':AI_TOKEN_DAILY_LIMIT,'prompt_tokens':prompt,'completion_tokens':completion,
            'billing_guarantee':False}


def research_story(story_id,fetcher=None,caller=None,actor='manual'):
    """Bounded Groq drafting. Every attempt reserves tokens before network I/O; never publishes."""
    if not re.fullmatch(r'[0-9a-f]{32}',story_id):raise ValueError('Invalid id')
    if actor not in ('manual','auto'):raise ValueError('Invalid actor')
    if actor=='auto' and not get_settings()['auto_draft']:raise ValueError('Automatic drafting disabled')
    if not ai_writer.available() and caller is None:
        raise ValueError('Groq key not configured on this server')
    with LOCK:
        with closing(get_db()) as c:
            c.execute('BEGIN IMMEDIATE')
            story=c.execute('SELECT * FROM stories WHERE id=?',(story_id,)).fetchone()
            if not story or story['status']=='dismissed':raise ValueError('Story not available')
            utc_day=dt.datetime.now(dt.timezone.utc).date().isoformat()
            daily_used=c.execute('SELECT COUNT(*) FROM ai_requests WHERE date_utc=?',(utc_day,)).fetchone()[0]
            story_used=c.execute('SELECT COUNT(*) FROM ai_requests WHERE story_id=?',(story_id,)).fetchone()[0]
            if daily_used>=AI_DAY_LIMIT:raise ValueError('Daily Groq request limit reached')
            if actor=='auto':
                auto_used=c.execute("SELECT COUNT(*) FROM ai_requests WHERE date_utc=? AND actor='auto'",(utc_day,)).fetchone()[0]
                if auto_used>=AUTO_DAILY_LIMIT:raise ValueError('Automatic draft limit reached')
                if story['kind'] not in ('development','release'):
                    raise ValueError('Auto research only accepts official development sources')
            token_used=c.execute('''SELECT COALESCE(SUM(CASE WHEN status='complete' AND prompt_tokens+completion_tokens>0
                  THEN MAX(reserved_tokens,prompt_tokens+completion_tokens) ELSE reserved_tokens END),0)
                  FROM ai_requests WHERE date_utc=?''',(utc_day,)).fetchone()[0]
            if token_used+AI_RESERVE_TOKENS>AI_TOKEN_DAILY_LIMIT:
                raise ValueError('Groq daily token budget nearly exhausted')
            if story_used>=AI_STORY_LIMIT:raise ValueError('This story has reached its AI rewrite limit')
            nowutc=now()
            cursor=c.execute('INSERT INTO ai_requests (story_id,started_at,date_utc,status,model,actor,reserved_tokens) VALUES (?,?,?,?,?,?,?)',
                    (story_id,nowutc,nowutc[:10],'started',ai_writer.MODEL,actor,AI_RESERVE_TOKENS))
            request_id=cursor.lastrowid
            c.commit()
            record=dict(story)
    try:
        evidence=ai_writer.fetch_official(record,load_sources(),fetcher=fetcher)
        # Related records are context clues only, never independently verified claims.
        siblings=[r for r in story_list(300) if r['id'] != story_id and editorial.similar(r,record)]
        evidence['related_feed_leads']=[{'title':r['title'],'url':r['url'],'source':r['source']}
                                         for r in siblings[:3]]
        evidence['newsroom_topic']=editorial.topic(record)
        article=ai_writer.groq_generate(evidence,caller=caller)
        draft={'title':article['title'][:145], 'slug':make_slug(article['title']),
               'summary':article['summary'],'body':article['body'],
               'category':'Release' if record['kind']=='release' and not record['manual'] else 'Development update',
               'tags': ', '.join({'DigiByte':['DigiByte','DGB','DigiByte Wallet'],
                                  'Bitcoin':['Bitcoin','BTC','Cryptocurrency'],
                                  'Sumcoin':['Sumcoin','SUM','Cryptocurrency'],
                                  'Ethereum':['Ethereum','ETH','Cryptocurrency']}.get(editorial.topic(record),['Cryptocurrency','Blockchain'])),
               'image_alt':'Original abstract blockchain network artwork for '+editorial.topic(record)+' coverage',
               'focus_x':'50','focus_y':'50',
               'ai_generated':True,'evidence_url':record['url'],'model':ai_writer.MODEL,
               'verification':article.get('verification',[]),'review_required':True,'review_confirmed':False}
        with LOCK:
            with closing(get_db()) as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?)',(story_id,json.dumps(draft,ensure_ascii=False),now()))
                c.execute("UPDATE stories SET status='drafted' WHERE id=?",(story_id,))
                usage=article.get('usage') or {}
                c.execute("UPDATE ai_requests SET status='complete',prompt_tokens=?,completion_tokens=? WHERE id=?",
                          (int(usage.get('prompt_tokens',0)),int(usage.get('completion_tokens',0)),request_id))
                c.commit()
        return draft
    except Exception:
        with LOCK:
            with closing(get_db()) as c:
                c.execute("UPDATE ai_requests SET status='error' WHERE id=?",(request_id,))
                c.commit()
        raise

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

def auto_prepare_once(caller=None,fetcher=None):
    """Make no more than one background AI draft per monitoring pass. No public writes."""
    if not AUTO_LOCK.acquire(blocking=False):return {'status':'busy'}
    try:
        if not get_settings()['auto_draft']:return {'status':'disabled'}
        if not ai_writer.available() and caller is None:return {'status':'unconfigured'}
        usage=ai_usage()
        if usage['auto_used']>=AUTO_DAILY_LIMIT or usage['daily_used']>=AI_DAY_LIMIT:
            return {'status':'budget_exhausted'}
        if usage['tokens_used']+AI_RESERVE_TOKENS>AI_TOKEN_DAILY_LIMIT:
            return {'status':'token_budget_exhausted'}
        with closing(get_db()) as c:
            rows=[dict(r) for r in c.execute("SELECT * FROM stories WHERE status='new' AND manual=0 ORDER BY COALESCE(published,first_seen) DESC LIMIT 180")]
        candidates=[r for r in editorial.group_stories(rows) if editorial.auto_eligible(r)]
        for story in candidates:
            # Never automatically write over existing human or AI working drafts.
            if get_draft(story['id']) is not None:continue
            try:
                draft=research_story(story['id'],caller=caller,fetcher=fetcher,actor='auto')
                return {'status':'prepared','story_id':story['id'],'title':draft['title']}
            except (ValueError,ai_writer.ResearchError) as err:
                return {'status':'error','message':type(err).__name__+': '+str(err)[:100]}
        return {'status':'no_eligible_story'}
    finally:AUTO_LOCK.release()

def artwork_bytes(story_id):
    if not re.fullmatch(r'[0-9a-f]{32}',story_id):raise ValueError('Invalid ID')
    with closing(get_db()) as c:
        story=c.execute('SELECT * FROM stories WHERE id=?',(story_id,)).fetchone()
        if story is None:raise ValueError('Story not found')
        item=dict(story)
    art_dir=STATE/'artwork'
    art_dir.mkdir(mode=0o700,exist_ok=True)
    path=art_dir/(story_id+'.png')
    with LOCK:
        # Regenerate only our own older cached abstract artwork when moving to v0.5.
        outdated=not path.is_file() or b'DGBNewsroom-v0.5' not in path.read_bytes()[:500]
        if outdated:
            content=artwork.generate(editorial.topic(item),item['title']+item['id'])
            temp=art_dir/(story_id+'.pending.png')
            temp.write_bytes(content)
            temp.replace(path)
        return path.read_bytes()

def preview_article(story_id):
    draft=get_draft(story_id)
    if not draft:raise ValueError('No working draft')
    with closing(get_db()) as c:
        story=c.execute('SELECT * FROM stories WHERE id=?',(story_id,)).fetchone()
        if not story:raise ValueError('Story not found')
        record=dict(story)
    canonical='https://www.digibytewallet.org/news/'+draft['slug']+'.html'
    body=draft.get('body','')
    warnings=[]
    if 'VERIFY BEFORE PUBLISHING' in body:warnings.append('Legacy editorial warning must be removed from article')
    if draft.get('review_required') and not draft.get('review_confirmed'):
        warnings.append('Private editorial verification has not been approved')
    if record['kind']=='news':warnings.append('Headline-only third-party report: obtain primary evidence')
    if len(re.findall(r'\w+',body))<220:warnings.append('Article needs deeper original reporting')
    warnings.extend(['Generated illustration must be reviewed for relevance',
                     'Verify each sourced claim and confirm publication/release status'])
    schema={'@context':'https://schema.org','@type':'NewsArticle','headline':draft['title'],
            'description':draft['summary'],'datePublished':'ASSIGNED AT PUBLICATION',
            'dateModified':'ASSIGNED AT PUBLICATION','author':{'@type':'Organization','name':'DigiByte Wallet'},
            'publisher':{'@type':'Organization','name':'DigiByte Wallet'},
            'mainEntityOfPage':canonical}
    return {'canonical':canonical,'author':'DigiByte Wallet',
            'publication_date':'Assigned at publication, not original source timestamp',
            'source_timestamp':record['published'],'topic':editorial.topic(record),
            'headline':draft['title'],'summary':draft['summary'],
            'words':len(re.findall(r'\w+',body)), 'warnings':warnings,
            'jsonld_preview':schema,'image_size':'1600x1200 PNG; publisher produces 16:9, 4:3 and square variants',
            'public_auto_publish':False}

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

def published_inventory():
    """Read-only currently public newsroom articles. No public write operations."""
    site='https://www.digibytewallet.org/news/feed.json'
    try:
        with urlopen(Request(site,headers={'User-Agent':'DGB-Newsroom-ControlCenter/0.5'}),timeout=7) as r:
            if hostname(r.geturl())!='www.digibytewallet.org':raise ValueError('Unexpected redirect')
            obj=json.loads(r.read(150000).decode('utf-8'))
        entries=[]
        for x in obj.get('items',[])[:60]:
            url=x.get('url','')
            if urlparse(url).hostname!='www.digibytewallet.org' or not url.startswith('https://www.digibytewallet.org/news/'):
                continue
            entries.append({'title':str(x.get('title') or '')[:150],'url':url,'published':str(x.get('date_published') or '')[:45]})
        return {'available':True,'entries':entries,'lifecycle':'read-only','public_auto_publish':False}
    except (OSError,ValueError,KeyError,TimeoutError,TypeError) as e:
        return {'available':False,'entries':[],'error':type(e).__name__,'lifecycle':'read-only'}

def analytics_report():
    """Read-only aggregates. No raw visitor IP, cookie or user agent reaches the dashboard."""
    path=STATE/'traffic-aggregate.json'
    if not path.is_file():
        return {'configured':False,'provider':'Nginx access logs','views':None,'articles':[],
                'detail':'No server log aggregate has been generated. Google Analytics and Search Console are not connected.'}
    try:
        data=json.loads(path.read_text('utf-8'))
        if data.get('schema')!=1 or not isinstance(data.get('articles'),list):raise ValueError('Bad analytics aggregate')
        if not data.get('logs_processed'):
            return {'configured':False,'provider':'Nginx access logs','views':None,'articles':[],
                    'detail':'No readable Nginx access logs found. Configure the site log path before measuring traffic.'}
        return {'configured':True,'provider':'Nginx access logs','measurement':'Estimated HTML page requests, not unique visitors',
                'google_analytics_connected':False,'search_console_connected':False,
                'checked_at':data.get('checked_at'),'range_days':data.get('range_days',30),
                'views':data.get('views',0),'articles':data.get('articles',[])[:100],
                'detail':'Counts exclude known bots and non-2xx requests; caching may reduce server-log counts.'}
    except (ValueError,OSError,TypeError):
        return {'configured':False,'provider':'Nginx access logs','views':None,'articles':[],
                'detail':'Analytics aggregate is unreadable; check the hourly aggregation job.'}

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def respond(self,status,obj,typ='application/json; charset=utf-8'):
        body=(obj.encode('utf-8') if isinstance(obj,str) else obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False).encode('utf-8'))
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
            with closing(get_db()) as c:
                counts={row['status']:row['total'] for row in c.execute('SELECT status,COUNT(*) AS total FROM stories GROUP BY status')}
            with closing(get_db()) as c:
                health={r['name']:dict(r) for r in c.execute('SELECT * FROM source_health')}
            sources=[dict(name=s['name'],kind=s['kind'],url=s['url'],health=health.get(s['name'])) for s in load_sources()]
            healthy=sum(1 for s in sources if s['health'] and s['health']['status']=='ok')
            return self.respond(200,{'stories':grouped_queue(),'scan':info,'counts':counts,
                'sources':sources,'healthy_sources':healthy,
                'settings':get_settings(),'usage':ai_usage()})
        if path=='/api/draft':
            query=self.path.split('?',1)[-1]
            from urllib.parse import parse_qs
            st=parse_qs(query).get('id',[''])[0]
            if not re.fullmatch(r'[0-9a-f]{32}',st):return self.respond(400,{'error':'Invalid id'})
            return self.respond(200,{'draft':get_draft(st)})
        if path=='/api/health':return self.respond(200,{'version':'0.5.0','mode':'automated-draft-review','publishing_enabled':False,
          'automated_social_scraping':False,'ai_configured':ai_writer.available(),'settings':get_settings()})
        if path=='/api/settings':return self.respond(200,{'settings':get_settings(),'usage':ai_usage()})
        if path=='/api/sources':
            with closing(get_db()) as c:
                health={r['name']:dict(r) for r in c.execute('SELECT * FROM source_health')}
            return self.respond(200,{'sources':[dict(s,health=health.get(s['name'])) for s in load_sources()],
                                    'last_scan':SCAN_REPORT.get('last_scan')})
        if path=='/api/preview':
            from urllib.parse import parse_qs
            story_id=parse_qs(urlparse(self.path).query).get('id',[''])[0]
            return self.respond(200,{'preview':preview_article(story_id)})
        if path=='/api/artwork':
            from urllib.parse import parse_qs
            story_id=parse_qs(urlparse(self.path).query).get('id',[''])[0]
            try:return self.respond(200,artwork_bytes(story_id),'image/png')
            except ValueError as e:return self.respond(404,{'error':str(e)})
        if path=='/api/ai-status':return self.respond(200,dict(ai_usage(),configured=ai_writer.available(),model=ai_writer.MODEL))
        if path=='/api/analytics':return self.respond(200,analytics_report())
        if path=='/api/publications':return self.respond(200,published_inventory())
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
            if p=='/api/settings':return self.respond(200,{'settings':set_settings(body)})
            if p=='/api/manual':return self.respond(201,{'story':add_manual(body)})
            if p=='/api/draft':return self.respond(200,{'draft':draft_for(str(body.get('id','')))})
            if p=='/api/research':return self.respond(200,{'draft':research_story(str(body.get('id','')))})
            if p=='/api/dismiss':
                dismiss(str(body.get('id','')))
                return self.respond(200,{'ok':True})
            return self.respond(404,{'error':'Not found'})
        except (ValueError,TypeError,sqlite3.Error,ai_writer.ResearchError) as e:
            return self.respond(400,{'error':str(e)[:200]})

def background_loop():
    time.sleep(2)
    while True:
        scan_worker()
        try:auto_prepare_once()
        except Exception as e:
            with LOCK:
                SCAN_REPORT['errors'].append('Auto drafting: '+type(e).__name__+': '+str(e)[:100])
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
