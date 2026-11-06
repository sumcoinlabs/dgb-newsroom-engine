#!/usr/bin/env python3
"""Aggregate existing Nginx access logs into anonymous *request* counts.

Run as a privileged, scheduled server job; the unprivileged newsroom service
only reads aggregated JSON. No IP addresses, referrers, cookies, or user agents
are written to the result. Request counts are NOT unique visitors or GA4 views.
"""
import argparse
from collections import Counter
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import pwd
import re
import tempfile

AGENT_BLOCK = re.compile(r'bot|crawler|spider|slurp|bingpreview|facebookexternalhit|twitterbot|uptimerobot|curl/|wget/|python-requests|headlesschrome',re.I)
LOG = re.compile(r'\[[^\]]+\]\s+"GET\s+(\S+)\s+HTTP/[^\"]+"\s+(\d{3})\s+\S+\s+"[^\"]*"\s+"([^\"]*)"')
DATE = re.compile(r'\[(\d{2})/([A-Za-z]{3})/(\d{4}):')
MONTHS = {m:i for i,m in enumerate(('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'),1)}
ARTICLE = re.compile(r'^/news/(?:[a-z0-9][a-z0-9-]{0,90}\.html)?$')

def counts_for_lines(lines, today=None, days=30):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    out = Counter()
    for line in lines:
        match=LOG.search(line)
        if not match:continue
        target,code,ua=match.groups()
        if not code.startswith('2') or AGENT_BLOCK.search(ua):continue
        target=target.split('?',1)[0]
        if not ARTICLE.fullmatch(target):continue
        matchdate=DATE.search(line)
        if not matchdate:continue
        d,m,y=matchdate.groups()
        try:
            when=dt.date(int(y),MONTHS[m.title()],int(d))
        except (ValueError,KeyError):continue
        if not 0 <= (today-when).days < days:continue
        out[target]+=1
    return out

def report(log_paths, days=30):
    today=dt.datetime.now(dt.timezone.utc).date()
    agg=Counter(); processed=[]
    for p in log_paths[:20]:
        p=Path(p)
        try:
            if not p.is_file() or p.stat().st_size>250_000_000:continue
            if p.suffix=='.gz':
                with gzip.open(str(p),'rt',encoding='utf-8',errors='replace') as f:agg.update(counts_for_lines(f,today,days))
            else:
                with p.open('rt',encoding='utf-8',errors='replace') as f:agg.update(counts_for_lines(f,today,days))
            processed.append(p.name)
        except (OSError,EOFError):continue
    result={'schema':1,'range_days':days,'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'views':sum(agg.values()), 'articles':[{'path':p,'views':n} for p,n in agg.most_common(100)],
            'logs_processed':len(processed),'source':'existing Nginx access logs'}
    return result

def atomic_aggregate(destination,log_paths):
    dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True)
    data=report(log_paths)
    fd,temporary=tempfile.mkstemp(prefix='.newsroom-aggregate-',dir=str(dest.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            os.fchmod(f.fileno(),0o640)
            json.dump(data,f,sort_keys=True)
        user=pwd.getpwnam('dgbnews')
        os.chown(temporary,user.pw_uid,user.pw_gid)
        os.replace(temporary,str(dest))
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return data

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='/var/lib/dgb-newsroom-engine/traffic-aggregate.json')
    parser.add_argument('logs',nargs='+')
    args=parser.parse_args()
    print(json.dumps(atomic_aggregate(args.output,args.logs),indent=2))
