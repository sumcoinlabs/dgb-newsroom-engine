"""v0.6 read-only editorial diagnostics. No public writes or publishing controls."""
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlparse
import re

BLOCKERS = ('legacy working-draft boilerplate', 'missing source link', 'no article text')
_RELEASE = re.compile(r'\b(?:alpha|beta|release candidate|rc\d+|preview|prerelease|testnet|unreleased)\b|\bv?\d+\.\d+(?:\.\d+)?[-.](?:a|b|alpha|beta|rc)\d*\b', re.I)
_HYPE = re.compile(r'\b(?:guaranteed returns|100% safe|unhackable|moonshot|risk[- ]free|will definitely surge|massive profits)\b',re.I)
_LEGACY = re.compile(r'EDITORIAL WORKING DRAFT|VERIFY BEFORE PUBLISHING|human checks still required',re.I)

def _date(value):
    if not value:return None
    try:
        val=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return val.astimezone(timezone.utc) if val.tzinfo else None
    except (ValueError,TypeError):return None

def health_summary(sources, health, current=None):
    """Interpret existing source-health DB; never alter a source URL automatically."""
    current=current or datetime.now(timezone.utc)
    rows=[]
    for src in sources:
        h=health.get(src['name']) or {}
        status=h.get('status') or 'unchecked'
        recent=_date(h.get('last_entry'))
        days=round((current-recent).total_seconds()/86400,1) if recent else None
        error=(h.get('last_error') or '')[:150]
        reason={
            'ok':'Receiving feed entries',
            'empty':'Feed reachable but has no valid entries',
            'stale':'Feed has not published a recent item',
            'error':'Feed failed: '+(error or 'unknown error'),
            'unchecked':'Not scanned yet'
        }.get(status,'Unexpected source state')
        # Stale is not always broken: official release feeds can go months without releases.
        action={
            'ok':'No action needed',
            'empty':'Inspect feed format and source publishing activity',
            'stale':'Check official source manually; inactivity may be normal',
            'error':'Verify canonical RSS URL, redirect, and upstream response',
            'unchecked':'Run a scan'
        }.get(status,'Inspect source configuration')
        rows.append({'name':src['name'],'url':src['url'],'kind':src['kind'],
                     'status':status,'last_checked':h.get('last_checked'),
                     'days_since_entry':days,'last_error':error,'reason':reason,
                     'suggestion':action,'entry_count':h.get('count',0)})
    return {'total':len(rows),'healthy':sum(x['status']=='ok' for x in rows),
            'attention':[x for x in rows if x['status']!='ok'], 'sources':rows}

def draft_quality(draft, story=None, published=None):
    """Editorial review aids; flag possible issues, never claim to verify facts."""
    story=story or {};published=published or []
    title=str(draft.get('title') or '').strip()
    body=str(draft.get('body') or '')
    summary=str(draft.get('summary') or '').strip()
    text=re.sub(r'\[[^\]]+\]\([^)]*\)|[#*_`]', ' ',body)
    words=len(re.findall(r"\b[\w'-]+\b",text))
    warnings=[];blockers=[]
    if not body.strip():blockers.append('No article text')
    if _LEGACY.search(body):blockers.append('Legacy working-draft boilerplate')
    if not re.search(r'\]\(https://[^)]+\)',body):blockers.append('Missing source link')
    if story.get('url') and story['url'] not in body:
        warnings.append('Original evidence URL is not cited in the article')
    if words<220:warnings.append('Short report: check whether reporting is substantial enough')
    if words>1000:warnings.append('Long report: review for unnecessary filler')
    if not (10<=len(title)<=155):warnings.append('Headline length outside publisher guidance')
    if not (45<=len(summary)<=360):warnings.append('Summary length outside publisher guidance')
    if _HYPE.search(title+' '+body):warnings.append('Potentially promotional or absolute claim needs evidence')
    if story.get('kind')=='news':warnings.append('Secondary headline source: seek primary evidence')
    if _RELEASE.search(story.get('title','')) and re.search(r'\b(?:released|launched|available now|shipped|stable release)\b',title+' '+body,re.I):
        warnings.append('Possible pre-release characterized as a final release; verify status')
    if draft.get('review_required') and not draft.get('review_confirmed'):
        warnings.append('Private AI fact-check acknowledgement still pending')
    slug=draft.get('slug','')
    for item in published:
        url=str(item.get('url') or '')
        if slug and url.endswith('/'+slug+'.html'):
            blockers.append('Article slug is already published')
            break
        if title and len(title)>22 and SequenceMatcher(None,title.lower(),str(item.get('title','')).lower()).ratio()>.87:
            warnings.append('Potential overlap with a published article: '+url)
            break
    return {'title':title[:155],'slug':slug,'story_id':story.get('id'),
            'words':words,'warnings':warnings,'blockers':blockers,
            'review_ready':not blockers and not warnings,
            'status':'BLOCKED' if blockers else 'REVIEW' if warnings else 'CHECKED',
            'note':'A checklist is not independent verification of facts.'}

def publication_checks(items):
    """Inspect feed metadata only. No edits, deletions, or automatic restores."""
    issues=[];seen=set()
    for p in items:
        url=p.get('url') or ''
        slug=urlparse(url).path
        if not (url.startswith('https://www.digibytewallet.org/news/') and slug.endswith('.html')):
            issues.append({'url':url,'problem':'Unexpected canonical URL'})
        if url in seen:issues.append({'url':url,'problem':'Duplicate URL in feed'})
        seen.add(url)
        if not _date(p.get('published')):
            issues.append({'url':url,'problem':'Missing or invalid publication timestamp'})
    return {'count':len(items),'issues':issues,'mode':'read-only',
            'corrections_enabled':False,'automatic_public_publishing':False}
