#!/usr/bin/env python3
"""Opt-in Google metrics collector, read-only. Never stores access/refresh tokens in output.

Connection requires owner-created OAuth credentials with read-only scopes. The
configuration is outside the git repo. No OAuth or advertising scripts are
installed in public pages by this component.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CONFIG=Path(os.environ.get('DGB_GOOGLE_CONFIG','/etc/dgb-newsroom-engine/google-integrations.json'))
STATE=Path(os.environ.get('DGB_ENGINE_STATE','/var/lib/dgb-newsroom-engine'))
OUTPUT=STATE/'google-summary-v06.json'
SCOPES={'ga4':'https://www.googleapis.com/auth/analytics.readonly',
        'gsc':'https://www.googleapis.com/auth/webmasters.readonly',
        'adsense':'https://www.googleapis.com/auth/adsense.readonly'}

def _json_request(url,token=None,payload=None,form=False):
    body=None if payload is None else urlencode(payload).encode() if form else json.dumps(payload).encode()
    headers={'User-Agent':'DigiByteNewsroomGoogleCollector/0.6','Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    if body:headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    req=Request(url,data=body,headers=headers,method='POST' if payload is not None else 'GET')
    with urlopen(req,timeout=15) as res:
        if res.url.split('/')[2] != url.split('/')[2]:raise ValueError('Unexpected Google redirect')
        return json.loads(res.read(450_000).decode())

def _token(config):
    required=('client_id','client_secret','refresh_token')
    if not all(isinstance(config.get(k),str) and config[k] for k in required):
        raise ValueError('Incomplete OAuth client credentials')
    t=_json_request('https://oauth2.googleapis.com/token',payload={
        'client_id':config['client_id'],'client_secret':config['client_secret'],
        'refresh_token':config['refresh_token'],'grant_type':'refresh_token'},form=True)
    if not isinstance(t.get('access_token'),str):raise ValueError('OAuth token response invalid')
    return t['access_token']

def ga4(token,prop):
    if not re.fullmatch(r'\d{5,20}',str(prop)):raise ValueError('Invalid GA4 property id')
    url='https://analyticsdata.googleapis.com/v1beta/properties/'+str(prop)+':runReport'
    report=_json_request(url,token,{'dateRanges':[{'startDate':'30daysAgo','endDate':'yesterday'}],
        'dimensions':[{'name':'pagePath'}],
        'metrics':[{'name':'screenPageViews'},{'name':'activeUsers'}],
        'limit':10000})
    rows=[]
    for r in report.get('rows',[]):
        path=(r.get('dimensionValues') or [{}])[0].get('value','')
        vals=r.get('metricValues') or []
        if not path.startswith('/news/') or len(vals)<2:continue
        rows.append({'path':path[:240],'page_views':int(vals[0].get('value',0)),
                     'active_users':int(vals[1].get('value',0))})
    # Summing per-page active users would double-count readers across articles.
    total=_json_request(url,token,{'dateRanges':[{'startDate':'30daysAgo','endDate':'yesterday'}],
        'metrics':[{'name':'screenPageViews'},{'name':'activeUsers'}]})
    counts=((total.get('rows') or [{}])[0].get('metricValues') or [])
    return {'provider':'Google Analytics 4','period':'last 30 complete days',
            'site_page_views':int(counts[0].get('value',0)) if len(counts)>0 else 0,
            'site_active_users':int(counts[1].get('value',0)) if len(counts)>1 else 0,
            'news_pages':sorted(rows,key=lambda x:x['page_views'],reverse=True)[:30]}

def gsc(token,site):
    if not (isinstance(site,str) and (site.startswith('sc-domain:') or
        re.fullmatch(r'https://[a-zA-Z0-9.-]+/',site))):raise ValueError('Invalid Search Console property')
    end=dt.date.today()-dt.timedelta(days=3)
    start=end-dt.timedelta(days=27)
    url='https://www.googleapis.com/webmasters/v3/sites/'+quote(site,safe='')+'/searchAnalytics/query'
    data=_json_request(url,token,{'startDate':start.isoformat(),'endDate':end.isoformat(),
        'dimensions':[],'type':'web','dimensionFilterGroups':[{'filters':[
          {'dimension':'page','operator':'contains','expression':'/news/'}]}]})
    row=(data.get('rows') or [{}])[0]
    return {'provider':'Google Search Console','period':str(start)+' to '+str(end),
            'news_clicks':int(row.get('clicks') or 0),
            'news_impressions':int(row.get('impressions') or 0),
            'news_ctr':round(float(row.get('ctr') or 0)*100,2),
            'news_avg_position':round(float(row.get('position') or 0),2),
            'notes':'Search Console data lags and is not real-time.',
            'sitemaps':gsc_sitemap_rows(token,site)}

def adsense(token,account):
    if not re.fullmatch(r'accounts/pub-\d{10,30}',str(account)):
        raise ValueError('AdSense account must be accounts/pub-...')
    url='https://adsense.googleapis.com/v2/'+account+'/reports:generate?'+urlencode([
      ('dateRange','LAST_30_DAYS'),('metrics','ESTIMATED_EARNINGS'),('metrics','PAGE_VIEWS')])
    data=_json_request(url,token)
    headers=(data.get('headers') or [])
    row=(data.get('rows') or [])
    cells=row[0].get('cells',[]) if row else []
    mapped={str(h.get('name')):cells[i].get('value') for i,h in enumerate(headers) if i<len(cells)}
    earnings=mapped.get('ESTIMATED_EARNINGS')
    return {'provider':'AdSense Management API','period':'last 30 days',
            'estimated_earnings':float(earnings) if earnings is not None else None,
            'page_views':int(float(mapped.get('PAGE_VIEWS'))) if mapped.get('PAGE_VIEWS') else None,
            'currency':data.get('metadata',{}).get('currencyCode',''),
            'scope':'Account-wide, not a per-article DigiByteWallet.org revenue attribution'}


# DGB_RADAR_LOCAL_DISCOVERY_V1: strictly read-only public-file audit.
def discovery_status():
    import xml.etree.ElementTree as ET
    from urllib.parse import urlsplit
    site=Path(os.environ.get('DGB_NEWS_LIVE','/var/www/digibytewallet-org'))
    base='https://www.digibytewallet.org'
    result={'valid':False,'last_checked':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'source':'Live website files (not Google crawl data)'}
    try:
        sm=ET.parse(site/'sitemap.xml').getroot()
        nm=ET.parse(site/'news-sitemap.xml').getroot()
        ns='http://www.sitemaps.org/schemas/sitemap/0.9'
        news='http://www.google.com/schemas/sitemap-news/0.9'
        if sm.tag!='{%s}urlset'%ns or nm.tag!='{%s}urlset'%ns:
            raise ValueError('Invalid sitemap root tag')
        urls=[]
        for row in sm.findall('{%s}url'%ns):
            url=row.findtext('{%s}loc'%ns)
            if not url or not url.startswith(base+'/') or urlsplit(url).netloc!='www.digibytewallet.org':
                raise ValueError('Invalid main sitemap URL')
            urls.append(url)
        if len(urls)!=len(set(urls)):
            raise ValueError('Duplicate URL in main sitemap')
        feed=json.loads((site/'news/feed.json').read_text('utf-8'))
        published=[x.get('url','') for x in feed.get('items',[])]
        missing=[x for x in published if x not in urls]
        news_urls=[]
        for row in nm.findall('{%s}url'%ns):
            loc=row.findtext('{%s}loc'%ns)
            required=[row.findtext('{%s}news/{%s}publication/{%s}name'%(news,news,news)),
                      row.findtext('{%s}news/{%s}publication/{%s}language'%(news,news,news)),
                      row.findtext('{%s}news/{%s}publication_date'%(news,news)),
                      row.findtext('{%s}news/{%s}title'%(news,news))]
            if not loc or loc not in urls or not all(required):
                raise ValueError('Google News sitemap entry missing URL or required tags')
            news_urls.append(loc)
        if len(news_urls)!=len(set(news_urls)):
            raise ValueError('Duplicate URL in Google News sitemap')
        robots=(site/'robots.txt').read_text('utf-8')
        robots_ok=all(('Sitemap: '+base+'/'+name) in robots
                      for name in ('sitemap.xml','news-sitemap.xml'))
        result.update({'valid':not missing and robots_ok,'main_urls':len(urls),
                       'news_urls':len(news_urls),'published_articles':len(published),
                       'missing_count':len(missing),'robots_ok':robots_ok})
    except (OSError,ValueError,TypeError,KeyError,ET.ParseError) as exc:
        result['error']=type(exc).__name__+': '+str(exc)[:160]
    return result

# Read Search Console's *submitted* sitemap report when account owner authorizes it.
def gsc_sitemap_rows(token,site):
    try:
        url='https://www.googleapis.com/webmasters/v3/sites/'+quote(site,safe='')+'/sitemaps'
        data=_json_request(url,token)
        rows=[]
        for record in data.get('sitemap',[]):
            path=record.get('path','')
            if path not in ('https://www.digibytewallet.org/sitemap.xml',
                            'https://www.digibytewallet.org/news-sitemap.xml'):
                continue
            rows.append({'path':path,'last_downloaded':record.get('lastDownloaded'),
                         'submitted':record.get('lastSubmitted'),
                         'pending':bool(record.get('isPending',False)),
                         'errors':int(record.get('errors',0)),
                         'warnings':int(record.get('warnings',0)),
                         'discovered':sum(int(x.get('submitted',0)) for x in record.get('contents',[]))})
        return rows
    except (HTTPError,URLError,OSError,ValueError,TypeError,KeyError):
        return []

def public_status():
    base={'ga4':{'connected':False},'gsc':{'connected':False},'adsense':{'connected':False},
          'last_checked':None,'mode':'read-only','credentials_exposed':False,'discovery':discovery_status()}
    try:
        obj=json.loads(OUTPUT.read_text())
        if not isinstance(obj,dict) or obj.get('schema')!=6:return base
        for key in ('ga4','gsc','adsense'):
            record=obj.get(key,{})
            if isinstance(record,dict):base[key]={k:v for k,v in record.items() if k not in ('access_token','refresh_token','client_secret','client_id')}
        base['last_checked']=obj.get('last_checked')
    except (OSError,ValueError,TypeError):pass
    return base

def collect():
    result={'schema':6,'last_checked':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    for name in SCOPES:result[name]={'connected':False,'detail':'Not configured'}
    if CONFIG.is_file():
        try:
            if CONFIG.stat().st_mode & 0o007:raise ValueError('Configuration permissions are too open')
            config=json.loads(CONFIG.read_text())
            token=_token(config)
            checks=(('ga4','ga4_property_id',ga4),('gsc','gsc_site',gsc),('adsense','adsense_account',adsense))
            for name,field,fn in checks:
                if not config.get(field):continue
                try:result[name]=dict(fn(token,config[field]),connected=True)
                except (HTTPError,URLError,ValueError,TypeError,KeyError,OSError) as e:
                    # Only class and status, never Google response bodies or OAuth secrets.
                    result[name]={'connected':False,'detail':type(e).__name__,
                                  'http_status':e.code if isinstance(e,HTTPError) else None}
        except (HTTPError,URLError,ValueError,TypeError,KeyError,OSError) as e:
            for name in SCOPES:result[name]={'connected':False,'detail':type(e).__name__}
    STATE.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.google-v06-',dir=str(STATE))
    try:
        with os.fdopen(fd,'w') as out:
            os.fchmod(out.fileno(),0o600)
            json.dump(result,out,sort_keys=True)
            out.flush();os.fsync(out.fileno())
        os.replace(name,OUTPUT)
    finally:
        if os.path.exists(name):os.unlink(name)
    print('Google metrics:', ', '.join(k+'='+str(result[k]['connected']) for k in SCOPES))
    return result

if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1]!='--collect':raise SystemExit('Usage: google_metrics_v06.py --collect')
    collect()
