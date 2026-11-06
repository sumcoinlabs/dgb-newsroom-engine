"""Multi-crypto triage without third-party article scraping or model calls.

Classification/priority are editorial heuristics, not independent fact checks.
Kept separate from the core HTTP/SQLite service for testability.
"""
import datetime as dt
import re
from difflib import SequenceMatcher
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

RSS_HOSTS=frozenset(('www.coindesk.com','coindesk.com','bitcoinmagazine.com','decrypt.co'))
ALLOWED_ARTICLE_HOSTS=RSS_HOSTS | frozenset(('cointelegraph.com',))
ATOM='{http://www.w3.org/2005/Atom}'
STOP=frozenset(('the','and','for','with','from','this','that','into','after','before','core','wallet','update','updates','dgb','btc','eth','digibyte','bitcoin','sumcoin','ethereum','fix','fixes','release','released','merge','pull','request','docs','new','adds'))

class StripHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
    def handle_data(self,v): self.parts.append(v)

def clean(raw,n=700):
    parser=StripHTML()
    parser.feed(str(raw or ''))
    return re.sub(r'\s+',' ',unescape(' '.join(parser.parts))).strip()[:n]

def rss_entries(data,source,limit=18):
    """Consume RSS summaries only; never fetch or reuse article bodies/images."""
    if len(data)>1_500_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsafe RSS feed')
    root=ET.fromstring(data)
    if root.tag != 'rss' and not root.tag.endswith('}RDF'):raise ValueError('Expected RSS feed')
    from email.utils import parsedate_to_datetime
    from hashlib import sha256
    items=root.findall('channel/item') if root.tag=='rss' else root.findall('{http://purl.org/rss/1.0/}item')
    expected=urlparse(source['url']).hostname
    for item in items[:limit]:
        url=(item.findtext('link') or '').strip()
        p=urlparse(url)
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not p.hostname:
            continue
        host=p.hostname.lower()
        if host not in RSS_HOSTS or (expected and host.replace('www.','',1) != expected.replace('www.','',1)):
            continue
        title=clean(item.findtext('title'),180)
        if not title:continue
        preview=clean(item.findtext('description'),900)
        date=(item.findtext('pubDate') or '').strip()
        try:
            d=parsedate_to_datetime(date)
            if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
            date=d.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
        except (ValueError,TypeError,OverflowError):date=''
        yield {'id':sha256(url.encode()).hexdigest()[:32], 'title':title, 'url':url,
               'summary':preview, 'published':date, 'source':source['name'], 'kind':'news'}

def topic(story):
    name=(story.get('source') or '').lower()
    title=(story.get('title') or '').lower()
    if 'sumcoin' in name or re.search(r'\bsumcoin\b',title): return 'Sumcoin'
    if 'digibyte' in name or 'digicoinlib' in name or 'digidollar' in title or 'digibyte' in title: return 'DigiByte'
    if 'ethereum' in name or re.search(r'\b(?:ethereum|ether|eth)\b',title):return 'Ethereum'
    if 'bitcoin' in name or re.search(r'\b(?:bitcoin|btc)\b',title):return 'Bitcoin'
    return 'Crypto'

def age_hours(story,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    try:
        published=story.get('published') or story.get('first_seen')
        when=dt.datetime.fromisoformat(published.replace('Z','+00:00'))
        if when.tzinfo is None:return None
        return max(0,(now-when).total_seconds()/3600)
    except (ValueError,TypeError,AttributeError):return None

def priority(story,now=None):
    """Conservative editorial ranking, never a fact verification score."""
    kind=story.get('kind')
    title=(story.get('title') or '').lower()
    base={'release':70,'development':35,'news':43,'lead':40}.get(kind,30)
    if story.get('manual'):base+=4
    if re.search(r'\b(?:security|vulnerabilit|critical|exploit|consensus|upgrade|breaking|mainnet|activation)\w*\b',title):base+=16
    if re.search(r'\b(?:fix|launch|release|patch|stable|version|reliability)\w*\b',title):base+=8
    if re.search(r'\b(?:readme|changelog|lint|docs|typo|format|ci|test|workflow)\w*\b',title):base-=30
    if title.startswith(('merge pull request','update readme','bump version')):base-=18
    age=age_hours(story,now)
    if age is None:base-=18
    elif age<=24:base+=15
    elif age<=72:base+=8
    elif age>720:base-=45
    elif age>168:base-=25
    elif age>72:base-=10
    if topic(story)=='Sumcoin':base+=6  # first-party coverage, not truth/authority boost
    return max(0,min(100,base))

def tokens(title):
    s=set(re.findall(r'[a-z0-9]{3,}',(title or '').lower()))
    versions=set(re.findall(r'v?\d+\.\d+(?:\.\d+)?',title or ''))
    return (s-STOP),versions

def similar(a,b):
    if topic(a)!=topic(b):return False
    sa,va=tokens(a.get('title',''))
    sb,vb=tokens(b.get('title',''))
    if va and vb and va.intersection(vb):return True
    if len(sa)<2 or len(sb)<2:return False
    overlap=len(sa&sb)/max(1,len(sa|sb))
    return overlap>=0.55 or (overlap>=0.34 and SequenceMatcher(None,a.get('title','').lower(),b.get('title','').lower()).ratio()>0.72)

def group_stories(rows,now=None):
    """Rank and cluster candidates; original records always retained in SQLite."""
    ordered=sorted(rows,key=lambda r:(r.get('status')=='drafted',priority(r,now),r.get('published') or ''),reverse=True)
    groups=[]
    for item in ordered:
        entry=dict(item)
        entry['topic']=topic(entry)
        entry['priority']=priority(entry,now)
        entry['related_sources']=[]
        matched=None
        for target in groups:
            if similar(entry,target):matched=target;break
        if matched:
            matched['related_sources'].append({'id':entry['id'],'title':entry['title'],'url':entry['url'],'source':entry['source']})
        else:groups.append(entry)
    return groups


def auto_eligible(story,now=None):
    return (story.get('kind') in ('release','development')
            and not story.get('manual')
            and story.get('status')=='new'
            and priority(story,now)>=82
            and age_hours(story,now) is not None
            and age_hours(story,now)<=72)
