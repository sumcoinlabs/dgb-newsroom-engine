"""Locally rendered editorial artwork v0.6. Pillow optional; no external images or fonts bundled.

Uses installed system fonts only. When Pillow is unavailable, callers retain
stable v0.5 artwork. Never depicts an unverified real-world event.
"""
from io import BytesIO
import hashlib
import math
import os
import re
import textwrap

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, PngImagePlugin
except ImportError:
    Image=ImageDraw=ImageFont=ImageFilter=PngImagePlugin=None

SIZE=(1600,1200)
THEMES={
 'Bitcoin':((11,19,38),(246,167,78),(112,204,244)),
 'Ethereum':((17,18,45),(168,150,255),(102,225,232)),
 'DigiByte':((7,22,45),(53,162,244),(119,229,240)),
 'Sumcoin':((5,31,37),(74,209,182),(245,207,123)),
 'Crypto':((12,24,43),(73,174,227),(138,229,194))}
FONT_CANDIDATES=(
 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
 '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
 '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
 '/Library/Fonts/Arial Bold.ttf')
FONT_REGULAR=(
 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
 '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
 '/System/Library/Fonts/Supplemental/Arial.ttf')

def available():return Image is not None

def font(size,bold=True):
    for path in (FONT_CANDIDATES if bold else FONT_REGULAR):
        if os.path.isfile(path):
            try:return ImageFont.truetype(path,size)
            except OSError:pass
    return ImageFont.load_default()

def mix(a,b,t):return tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))

def wrap_headline(text,width=31):
    cleaned=' '.join(re.sub(r'[^\w\d\s.,:!&+\-/]',' ',text).split())
    return textwrap.wrap(cleaned,width=width,break_long_words=False,break_on_hyphens=False)[:4]

def generate(topic='Crypto',seed=''):
    if not available():raise ImportError('Pillow is not installed for the newsroom worker')
    W,H=SIZE
    base,accent,secondary=THEMES.get(topic,THEMES['Crypto'])
    key=hashlib.sha256(seed.encode('utf-8')).digest()
    # Smooth original illustration: no stock assets, screenshots, or company marks.
    background=Image.new('RGB',(W,H))
    pix=background.load()
    for y in range(H):
        yy=y/H
        for x in range(W):
            xx=x/W
            t=min(.34,.04+.21*yy+.13*max(0,1-math.hypot(xx-.78,yy-.28)))
            pix[x,y]=mix(base,accent,t)
    canvas=background.convert('RGBA')
    d=ImageDraw.Draw(canvas,'RGBA')
    for x in range(0,W,80):d.line((x,0,x,H),fill=(*secondary,6),width=1)
    for y in range(0,H,80):d.line((0,y,W,y),fill=(*secondary,6),width=1)
    # Specular bloom, positioned deliberately behind the icon rather than the text.
    bloom=Image.new('RGBA',(W,H),(0,0,0,0))
    b=ImageDraw.Draw(bloom,'RGBA')
    b.ellipse((950,145,1530,800),fill=(*accent,88))
    b.ellipse((1090,260,1500,680),fill=(*secondary,70))
    canvas=Image.alpha_composite(canvas,bloom.filter(ImageFilter.GaussianBlur(110)))
    d=ImageDraw.Draw(canvas,'RGBA')
    # Editorial layout is consistent, artwork motif adapts to the news event.
    d.rounded_rectangle((94,82,1505,1118),radius=42,outline=(*secondary,67),width=3)
    d.rounded_rectangle((134,118,428,176),radius=27,fill=(*accent,36),outline=(*accent,115),width=2)
    d.text((160,131),'CRYPTO NEWSROOM',font=font(23),fill=(238,251,255,250))
    d.text((138,228),str(topic).upper()+'  /  TECHNOLOGY REPORT',font=font(26),fill=(*secondary,245))
    d.line((138,295,770,295),fill=(*accent,190),width=5)
    original=seed[:-32] if len(seed)>32 and re.fullmatch(r'[a-fA-F0-9]{32}',seed[-32:]) else seed
    # Keep the headline entirely within the left text column.
    headline=[]
    size=68
    for try_size in (68,62,56,50):
        candidate=[];buf='';f=font(try_size)
        for word in (original or 'Crypto technology update').split():
            trial=(buf+' '+word).strip()
            if buf and d.textlength(trial,font=f)>682:
                candidate.append(buf);buf=word
            else:buf=trial
        if buf:candidate.append(buf)
        headline=candidate
        size=try_size
        if len(headline)<=5:break
    headline=headline[:5]
    tf=font(size)
    start_y=368 if len(headline)>3 else 404
    for i,line in enumerate(headline):
        if d.textlength(line,font=tf)>688:
            while len(line)>3 and d.textlength(line+'…',font=tf)>688:line=line[:-1]
            line+='…'
        d.text((137,start_y+i*(size+19)),line,font=tf,fill=(239,248,252,255),stroke_width=0)
    d.text((138,1013),'ORIGINAL EDITORIAL ILLUSTRATION  •  SOURCE-LINKED REPORT',font=font(19,False),fill=(183,208,227,225))
    # Restrict the subject graphic to right-hand artwork zone.
    cx,cy=1245,604
    head=(original or '').lower()
    if re.search(r'\bsecurity|exploit|vulnerab|breach|attack|patch|encrypt',head):kind='security'
    elif re.search(r'\bwallet|payment|transaction|address',head):kind='wallet'
    elif re.search(r'\brelease|upgrade|version|client|software|core',head):kind='release'
    elif re.search(r'\bnetwork|node|protocol|consensus|staking',head):kind='network'
    else:kind=['release','wallet','security','network'][key[3]%4]
    # Repeating orbit rings and event-specific glyph form a credible graphic, not a photo.
    for r in (290,230,174):
        d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(*secondary,90),width=3)
    for k in range(12):
        angle=(k/12)*math.tau+key[0]/255
        rr=280+(key[k]%55)
        x=int(cx+math.cos(angle)*rr);y=int(cy+math.sin(angle)*rr)
        d.ellipse((x-6,y-6,x+6,y+6),fill=(*accent,245))
    dark=(*base,255)
    d.rounded_rectangle((1070,432,1420,778),radius=61,fill=(*base,235),outline=(*accent,220),width=9)
    if kind=='security':
        poly=[(1245,493),(1350,530),(1338,648),(1245,716),(1152,648),(1140,530)]
        d.polygon(poly,fill=(*accent,105))
        d.line(poly+[poly[0]],fill=(*secondary,250),width=12,joint='curve')
        d.line([(1200,607),(1235,642),(1294,574)],fill=(239,253,255,255),width=15,joint='curve')
    elif kind=='wallet':
        d.rounded_rectangle((1142,537,1347,692),radius=21,fill=(*accent,125),outline=(*secondary,250),width=9)
        d.rounded_rectangle((1242,583,1370,640),radius=16,fill=dark,outline=(*secondary,255),width=6)
        d.ellipse((1270,601,1294,625),fill=(*accent,255))
    elif kind=='release':
        for i in range(3):
            y=519+i*65
            d.rounded_rectangle((1144,y,1346,y+47),radius=9,fill=(*accent,65+i*18),outline=(*secondary,180),width=3)
            d.ellipse((1160,y+17,1174,y+31),fill=(*accent,255))
            d.line((1190,y+24,1315,y+24),fill=(238,246,254,200),width=5)
    else:
        nodes=[(1156,542),(1334,543),(1244,623),(1160,699),(1336,700)]
        for a,b in [(0,2),(1,2),(2,3),(2,4),(0,1),(3,4)]:
            d.line(nodes[a]+nodes[b],fill=(*secondary,230),width=8)
        for x,y in nodes:d.ellipse((x-16,y-16,x+16,y+16),fill=(*accent,255),outline=(247,250,255,250),width=4)
    badge=kind.upper()
    d.rounded_rectangle((1139,839,1372,895),radius=17,fill=(*accent,32),outline=(*secondary,125),width=2)
    d.text((1160,850),badge,font=font(24),fill=(235,250,255,244))
    info=PngImagePlugin.PngInfo()
    info.add_text('Generator','DGBNewsroom-v0.6')
    info.add_text('Description','Original editorial illustration; not an event photograph')
    output=BytesIO()
    canvas.convert('RGB').save(output,'PNG',compress_level=6,pnginfo=info)
    return output.getvalue()
