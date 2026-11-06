"""Original deterministic 1600x1200 abstract crypto-themed PNG, stdlib only.

No copied photographs, logos, copyrighted artwork, external downloads, or text.
All assets are private until an editor explicitly publishes an article.
"""
import hashlib
import math
import struct
import zlib

W,H=1600,1200
PALETTES={
    'Bitcoin': ((21,30,50),(246,144,36),(255,205,103)),
    'Ethereum':((25,29,60),(125,113,232),(207,182,255)),
    'DigiByte':((11,30,60),(25,134,226),(84,233,239)),
    'Sumcoin':((10,32,43),(36,159,147),(233,199,94)),
    'Crypto':((19,27,53),(66,163,218),(240,151,136)),
}

def generate(topic='Crypto',seed=''):
    """Return a fully original, large PNG with geometric rings/nodes/network lines."""
    base,accent,bright=PALETTES.get(topic,PALETTES['Crypto'])
    digest=hashlib.sha256(str(seed).encode('utf-8')).digest()
    shift=(digest[0]-128)/2500
    center_x=int(W*(.58+shift))
    center_y=int(H*(.48+shift))
    raw=[]
    for y in range(H):
        row=bytearray(W*3+1)
        for x in range(W):
            dx=(x-center_x)/W
            dy=(y-center_y)/H
            radius=(dx*dx+dy*dy)**.5
            halo=max(0,1-radius*1.7)
            ring=max(0,1-abs(radius-.225)*270)
            ring2=max(0,1-abs(radius-.31)*240)
            grid=max(0,1-min(abs(((x+int(y*.28))%200)-100),abs(((y+int(x*.11))%205)-102))*1.15) * .17
            streak=(math.sin((x*.007)+(y*.0025)+(digest[1]*.1))+.75)*.055
            blend=min(.75,halo*.28+ring*.38+ring2*.15+grid+streak)
            for c in range(3):
                v=base[c]*(1-blend)+accent[c]*blend+bright[c]*ring*.27
                row[x*3+c+1]=min(255,max(0,int(v)))
        raw.append(bytes(row))
    data=zlib.compress(b''.join(raw),level=6)
    def chunk(name,body):
        return struct.pack('!I',len(body))+name+body+struct.pack('!I',zlib.crc32(name+body)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',W,H,8,2,0,0,0))
            +chunk(b'IDAT',data)+chunk(b'IEND',b''))
