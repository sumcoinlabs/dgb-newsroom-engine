"""Original 1600x1200 title-led editorial artwork using Python stdlib only.

No copied logos, web images or photographs. Each lead receives distinct topic
colors and the actual headline. Deterministic PNG, no font dependency.
"""
import hashlib
import struct
import textwrap
import zlib

W,H=1600,1200
PALETTES={
 'Bitcoin':((9,23,44),(238,143,46),(251,206,132)),
 'Ethereum':((21,19,48),(121,117,238),(210,188,255)),
 'DigiByte':((9,26,50),(32,135,230),(93,226,244)),
 'Sumcoin':((7,35,39),(34,165,155),(253,203,113)),
 'Crypto':((16,25,48),(49,133,190),(124,223,218)),
}
# Original compact 5x7 block characters: no bundled font files.
GLYPHS={
'A':['01110','10001','10001','11111','10001','10001','10001'],
'B':['11110','10001','10001','11110','10001','10001','11110'],
'C':['01111','10000','10000','10000','10000','10000','01111'],
'D':['11110','10001','10001','10001','10001','10001','11110'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'F':['11111','10000','10000','11110','10000','10000','10000'],
'G':['01111','10000','10000','10111','10001','10001','01110'],
'H':['10001','10001','10001','11111','10001','10001','10001'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
'J':['00111','00010','00010','00010','10010','10010','01100'],
'K':['10001','10010','10100','11000','10100','10010','10001'],
'L':['10000','10000','10000','10000','10000','10000','11111'],
'M':['10001','11011','10101','10101','10001','10001','10001'],
'N':['10001','11001','10101','10011','10001','10001','10001'],
'O':['01110','10001','10001','10001','10001','10001','01110'],
'P':['11110','10001','10001','11110','10000','10000','10000'],
'Q':['01110','10001','10001','10001','10101','10010','01101'],
'R':['11110','10001','10001','11110','10100','10010','10001'],
'S':['01111','10000','10000','01110','00001','00001','11110'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'U':['10001','10001','10001','10001','10001','10001','01110'],
'V':['10001','10001','10001','10001','10001','01010','00100'],
'W':['10001','10001','10001','10101','10101','10101','01010'],
'X':['10001','10001','01010','00100','01010','10001','10001'],
'Y':['10001','10001','01010','00100','00100','00100','00100'],
'Z':['11111','00001','00010','00100','01000','10000','11111'],
'0':['01110','10011','10101','10101','11001','10001','01110'],
'1':['00100','01100','00100','00100','00100','00100','01110'],
'2':['01110','10001','00001','00010','00100','01000','11111'],
'3':['11110','00001','00001','01110','00001','00001','11110'],
'4':['00010','00110','01010','10010','11111','00010','00010'],
'5':['11111','10000','11110','00001','00001','10001','01110'],
'6':['00110','01000','10000','11110','10001','10001','01110'],
'7':['11111','00001','00010','00100','01000','01000','01000'],
'8':['01110','10001','10001','01110','10001','10001','01110'],
'9':['01110','10001','10001','01111','00001','00010','11100'],
'.':['00000','00000','00000','00000','00000','01100','01100'],
'-':['00000','00000','00000','11111','00000','00000','00000'],
'/':['00001','00001','00010','00100','01000','10000','10000'],
':':['00000','01100','01100','00000','01100','01100','00000'],
'+':['00000','00100','00100','11111','00100','00100','00000'],
'&':['01100','10010','10100','01000','10101','10010','01101'],
' ':['00000']*7,
}

def generate(topic='Crypto',seed=''):
    base,accent,light=PALETTES.get(topic,PALETTES['Crypto'])
    digest=hashlib.sha256(seed.encode('utf-8')).digest()
    pixels=[]
    for y in range(H):
        line=bytearray(W*3)
        shade=(y/H)*.24
        for x in range(W):
            gx=x/W
            glow=max(0,1-(((gx-.83)**2)*3+((y/H-.39)**2)*3))*.17
            k=(shade+glow)
            off=x*3
            for ch in range(3):line[off+ch]=int(base[ch]*(1-k)+accent[ch]*k)
        pixels.append(line)
    def rect(x,y,w,h,c):
        x=max(0,int(x));y=max(0,int(y));w=int(w);h=int(h)
        if w<=0 or h<=0:return
        color=bytes(c)
        for yy in range(y,min(H,y+h)):
            row=pixels[yy]
            for xx in range(x,min(W,x+w)):row[xx*3:xx*3+3]=color
    def line(x0,y0,x1,y1,c,width=3):
        dx=abs(x1-x0);dy=abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1;err=dx-dy
        while True:
            rect(x0-width//2,y0-width//2,width,width,c)
            if x0==x1 and y0==y1:break
            e=2*err
            if e>-dy:err-=dy;x0+=sx
            if e<dx:err+=dx;y0+=sy
    def chars(text,x,y,scale,c):
        xx=x
        for ch in text.upper():
            pat=GLYPHS.get(ch,GLYPHS[' ']);
            for yy,row in enumerate(pat):
                for col,t in enumerate(row):
                    if t=='1':rect(xx+col*scale,y+yy*scale,scale-1,scale-1,c)
            xx+=6*scale
    # Editorial composition; no implication of a real event photo.
    rect(95,94,10,1020,accent)
    rect(138,112,175,9,light)
    chars('CRYPTO NEWSROOM  /  REPORT',140,147,5,(177,206,218))
    topic_word=(topic if topic in PALETTES else 'CRYPTO').upper()
    chars(topic_word,137,281,15,(237,250,252))
    rect(140,417,360,5,accent)
    # Distinct source title, never generic unlabeled circles.
    title=seed[:-32] if len(seed)>32 and all(c in '0123456789abcdef' for c in seed[-32:].lower()) else seed
    title=' '.join(title.upper().split())[:140]
    words=textwrap.wrap(title,width=33,break_long_words=True,break_on_hyphens=False)[:3]
    for i,t in enumerate(words):chars(t,142,625+i*100,9,(222,239,247))
    chars('ORIGINAL EDITORIAL ILLUSTRATION',142,1076,5,(157,186,208))
    # Plot geometric constellations; seeded shape gives story-specific details.
    cx,cy=1290,377
    points=[]
    for i in range(9):
        x=1110+(digest[i]*2)%385;y=185+(digest[9+i]*3)%360
        points.append((x,y))
    for i in range(len(points)):
        if i+1<len(points):line(*points[i],*points[i+1],accent,4)
    for x,y in points:
        rect(x-14,y-14,28,28,light)
        rect(x-6,y-6,12,12,(7,24,40))
    # Event pin / source badge in right-hand corner.
    rect(1050,983,390,9,accent)
    chars('SOURCE LINKED',1060,1010,5,(181,216,224))
    def chunk(name,data):
        return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
    raw=b''.join(b'\0'+bytes(row) for row in pixels)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',W,H,8,2,0,0,0))+chunk(b'tEXt',b'Generator\x00DGBNewsroom-v0.5')+chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b'')
