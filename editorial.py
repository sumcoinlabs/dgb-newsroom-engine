"""Source-first crypto story triage and grouping for Newsroom v0.4.

Scores estimate *newsworthiness*, not factual correctness or investment quality.
No copying third-party article content or images.
"""
import datetime as dt
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

RSS_HOSTS=frozenset((
 'www.coindesk.com','coindesk.com','bitcoinmagazine.com','decrypt.co',
 'cointelegraph.com','www.theblock.co','theblock.co','bitcoinops.org',
 'blog.ethereum.org','www.chainalysis.com','chainalysis.com',
 'cryptoslate.com','unchainedcrypto.com','thedefiant.io','www.dlnews.com','dlnews.com'))
ALLOWED_ARTICLE_HOSTS=RSS_HOSTS
ATOM='{http://www.w3.org/2005/Atom}'
STOP=frozenset(('the','and','for','with','from','this','that','into','after','before','core','wallet','update','updates','dgb','btc','eth','release','released','merge','pull','request','docs','new','adds','notes','news','said','says','could','amid','about'))
OFFICIAL_RE=re.compile(r'\b(?:security|vulnerabilit\w*|critical|exploit|consensus|mainnet|activation|protocol|upgrade|patch|stable)\b',re.I)
ROUTINE_RE=re.compile(r'\b(?:readme|changelog|lint|typo|formatting|dependency|unit tests|workflow|build|ci|docs|refactor|test|fix warning)\b',re.I)
PROJECTS={'Sumcoin':r'\b(?:sumcoin|sumcoinlib)\b','DigiByte':r'\b(?:digibyte|digidollar|digicoinlib|\bdgb\b)\b',
 'Ethereum':r'\b(?:ethereum|ether|\beth\b|\bgeth\b|\bevm\b)\b','Bitcoin':r'\b(?:bitcoin|\bbtc\b|lightning network|\blnd\b|\boptech\b|\bbip[- ]?\d+)\b'}
OTHER_CRYPTO=re.compile(r'\b(?:crypto(?:currency)?|blockchain|stablecoin|tokeniz\w*|defi|nft|zcash|xrp|solana|polkadot|dogecoin|monero|crypto exchange|tether|usdc|coinbase|binance|kraken|onchain|web3|wallet|sec .*crypto)\b',re.I)

class StripHTML(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,v):self.parts.append(v)

def clean(raw,n=700):
    parser=StripHTML();parser.feed(str(raw or ''))
    return re.sub(r'\s+',' ',unescape(' '.join(parser.parts))).strip()[:n]

def parse_date(raw):
    try:
        if not raw:return ''
        d=dt.datetime.fromisoformat(raw.replace('Z','+00:00')) if 'T' in raw else parsedate_to_datetime(raw)
        if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
    except (ValueError,OverflowError,TypeError):return ''

def rss_entries(data,source,limit=18):
    """Only headline, excerpt, date, URL. Support RSS, RDF, Atom. Never read images."""
    if len(data)>1_500_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('Unsafe RSS feed')
    root=ET.fromstring(data)
    expected=urlparse(source['url']).hostname.lower()
    entries=[]
    if root.tag==ATOM+'feed':
        for item in root.findall(ATOM+'entry')[:limit]:
            url=''
            for link in item.findall(ATOM+'link'):
                if link.get('rel','alternate')=='alternate':url=link.get('href','');break
            entries.append((url,item.findtext(ATOM+'title'),item.findtext(ATOM+'summary') or item.findtext(ATOM+'content'),item.findtext(ATOM+'published') or item.findtext(ATOM+'updated')))
    elif root.tag=='rss':
        for item in root.findall('channel/item')[:limit]:
            entries.append((item.findtext('link'),item.findtext('title'),item.findtext('description'),item.findtext('pubDate')))
    elif root.tag.endswith('}RDF'):
        for item in root.findall('{http://purl.org/rss/1.0/}item')[:limit]:
            entries.append((item.findtext('{http://purl.org/rss/1.0/}link'),item.findtext('{http://purl.org/rss/1.0/}title'),item.findtext('{http://purl.org/rss/1.0/}description'),item.findtext('{http://purl.org/dc/elements/1.1/}date')))
    else:raise ValueError('Expected RSS or Atom feed')
    for url,title,preview,date in entries:
        url=(url or '').strip();p=urlparse(url)
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not p.hostname:continue
        host=p.hostname.lower()
        if host not in RSS_HOSTS:continue
        # External publisher feeds must link back to that publisher; no cross-domain redirects.
        if host.replace('www.','',1)!=expected.replace('www.','',1):continue
        title=clean(title,180)
        if not title:continue
        yield {'id':sha256(url.encode()).hexdigest()[:32],'title':title,'url':url,
          'summary':clean(preview,900),'published':parse_date(date),
          'source':source['name'],'kind':'news'}

def topic(story):
    title=(story.get('title') or '').lower()
    name=(story.get('source') or '').lower()
    kind=story.get('kind')
    # Publisher titles do not determine article topic (e.g. Bitcoin Magazine about Thailand).
    if kind in ('news','lead'):
        for project,pattern in PROJECTS.items():
            if re.search(pattern,title,re.I):return project
        return 'Crypto'
    for project,pattern in PROJECTS.items():
        if re.search(pattern,title+' '+name,re.I):return project
    return 'Crypto'

def relevant(story):
    if story.get('kind')!='news':return True
    title=story.get('title','')
    return any(re.search(p,title,re.I) for p in PROJECTS.values()) or bool(OTHER_CRYPTO.search(title))

def age_hours(story,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    try:
        st=story.get('published') or story.get('first_seen')
        when=dt.datetime.fromisoformat(st.replace('Z','+00:00'))
        if when.tzinfo is None:return None
        return max(0,(now-when).total_seconds()/3600)
    except (ValueError,TypeError,AttributeError):return None

def archive(story,now=None):
    age=age_hours(story,now)
    return age is not None and age>14*24

def priority(story,now=None):
    kind=story.get('kind')
    title=story.get('title','')
    base={'release':60,'development':31,'news':47,'lead':40}.get(kind,25)
    if story.get('manual'):base+=4
    if OFFICIAL_RE.search(title):base+=16
    if re.search(r'\b(?:launch|release|shipped|adoption|regulation|lawsuit|fraud|hack|breach)\b',title,re.I):base+=9
    if ROUTINE_RE.search(title):base-=35
    if title.lower().startswith(('merge pull request','update readme','bump version','docs:','test:','build:','ci:')):base-=19
    if kind=='news' and not relevant(story):base-=65
    age=age_hours(story,now)
    if age is None:base-=14
    elif age<=24:base+=16
    elif age<=72:base+=10
    elif age<=168:base+=2
    elif age<=336:base-=18
    else:base-=46
    if topic(story)=='Sumcoin':base+=6 # first-party beat priority, not a reliability claim
    return min(100,max(0,base))

def tokens(title):
    title=title or ''
    words=set(re.findall(r'[a-z0-9]{3,}',title.lower()))-STOP
    versions=set(re.findall(r'\bv?\d+\.\d+(?:\.\d+)?\b',title.lower()))
    return words,versions

def similar(a,b):
    if topic(a)!=topic(b):return False
    sa,va=tokens(a.get('title',''));sb,vb=tokens(b.get('title',''))
    if va and vb and va.intersection(vb):return True
    if len(sa)<2 or len(sb)<2:return False
    overlap=len(sa&sb)/max(1,len(sa|sb))
    if overlap>=.55:return True
    if overlap>=.33 and SequenceMatcher(None,a['title'].lower(),b['title'].lower()).ratio()>.69:return True
    # Cross-publisher coverage about the same named asset and event within 72 hours.
    if a.get('source')!=b.get('source') and overlap>=.22 and len(sa&sb)>=2:
        ha,hb=age_hours(a),age_hours(b)
        if ha is not None and hb is not None and abs(ha-hb)<=72:
            if any(w in sa&sb for w in ('zcash','nu7','hack','breach','upgrade','sec','coinbase','binance','solana')):return True
    return False

def group_stories(rows,now=None):
    ordered=sorted(rows,key=lambda r:(r.get('status')=='drafted',priority(r,now),r.get('published') or ''),reverse=True)
    groups=[]
    for item in ordered:
        entry=dict(item);entry['topic']=topic(entry);entry['priority']=priority(entry,now)
        entry['related_sources']=[];entry['archived']=archive(entry,now)
        if not relevant(entry):entry['off_topic']=True
        match=None
        for target in groups:
            if similar(entry,target):match=target;break
        if match:
            match['related_sources'].append({'id':entry['id'],'title':entry['title'],'url':entry['url'],'source':entry['source']})
        else:groups.append(entry)
    return groups

def auto_eligible(story,now=None):
    age=age_hours(story,now)
    if story.get('kind') not in ('release','development') or story.get('manual') or story.get('status')!='new':return False
    if age is None or age>72:return False
    title=(story.get('title') or '')
    if ROUTINE_RE.search(title):return False
    # A prerelease or beta is a research lead, not a reason to spend the daily AI quota.
    if re.search(r'(?i)(?:\bv?\d+(?:\.\d+)*[-.]?(?:alpha|beta|rc|pre)\d*\b|\btestnet[- ]only\b|\bpreview\b|\bprerelease\b)',title):return False
    if topic(story)=='Crypto':return False
    if story.get('kind')=='development' and not OFFICIAL_RE.search(title):return False
    return priority(story,now)>=76
