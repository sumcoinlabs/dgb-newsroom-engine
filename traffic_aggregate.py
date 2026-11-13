#!/usr/bin/env python3
"""Aggregate 30-day HTML request counts from local Nginx logs. No IPs stored."""
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

STATE=Path(os.environ.get('DGB_ENGINE_STATE','/var/lib/dgb-newsroom-engine'))
SITE=Path(os.environ.get('DGB_NEWS_LIVE','/var/www/digibytewallet-org'))
LOGS=Path(os.environ.get('DGB_NGINX_LOG_DIR','/var/log/nginx'))
NOW=dt.datetime.now(dt.timezone.utc)
SINCE=NOW-dt.timedelta(days=30)
LINE=re.compile(r'^\S+\s+\S+\s+\S+\s+\[([^]]+)\]\s+"(GET|HEAD)\s+(\S+)\s+HTTP/[^\"]+"\s+(\d{3})\s+\S+\s+"[^\"]*"\s+"([^\"]*)"')
ROBOTS=re.compile(r'bot|crawler|spider|slurp|ahrefs|semrush|bingpreview|facebookexternalhit|googleother|googlebot|bingbot|yandex|archive|uptimerobot|lighthouse|headless|curl/|python-requests|wget/',re.I)

def logs_in(dirpath):
    paths=sorted(set(dirpath.glob('*access*.log*')) | set(dirpath.glob('access.log*')))
    targeted=[p for p in paths if re.search('digibyte|dgb|wallet',p.name,re.I)]
    return targeted or paths

def aggregate():
    feed=SITE/'news/feed.json'
    if not feed.is_file():raise RuntimeError('Cannot read site news feed')
    data=json.loads(feed.read_text(encoding='utf-8'))
    allowed={urlsplit(x['url']).path for x in data.get('items',[]) if str(x.get('url','')).startswith('https://www.digibytewallet.org/news/')}
    allowed.add('/news/')
    counts={p:0 for p in allowed}
    processed=0
    for file in logs_in(LOGS)[:25]:
        if not file.is_file():continue
        try:
            if file.stat().st_size>150*1024*1024:continue
            opener=gzip.open if file.suffix=='.gz' else open
            with opener(str(file),'rt',encoding='utf-8',errors='replace') as stream:
                processed+=1
                for lineno,ln in enumerate(stream):
                    if lineno>=300000:break
                    m=LINE.match(ln)
                    if not m:continue
                    stamp,method,uri,status,ua=m.groups()
                    if method!='GET' or status!='200' or ROBOTS.search(ua):continue
                    path=urlsplit(uri).path
                    if path not in allowed:continue
                    try:time=dt.datetime.strptime(stamp,'%d/%b/%Y:%H:%M:%S %z')
                    except ValueError:continue
                    if SINCE <= time <= NOW+dt.timedelta(minutes=5):counts[path]+=1
        except (OSError,EOFError):continue
    out={'schema':1,'checked_at':NOW.isoformat(timespec='seconds'),
         'range_days':30,'logs_processed':processed,'views':sum(counts.values()),
         'articles':[{'path':p,'views':v} for p,v in sorted(counts.items(),key=lambda x:(-x[1],x[0]))]}
    if processed:
        STATE.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.traffic-',dir=str(STATE))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as o:json.dump(out,o,sort_keys=True)
            os.chmod(temp,0o644)
            os.replace(temp,STATE/'traffic-aggregate.json')
        finally:
            if os.path.exists(temp):os.unlink(temp)
    print('Analytics: log files',processed,'30-day requests',out['views'],'articles',len(counts),flush=True)
    if not processed:print('NOTICE: No readable Nginx access logs; will not invent traffic counts',flush=True)
    return out

if __name__=='__main__':aggregate()
