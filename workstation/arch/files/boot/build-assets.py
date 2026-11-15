#!/usr/bin/env python3
"""Generate tiny deterministic boot-menu assets; no fonts or imaging dependencies."""
import pathlib
import struct
import zlib
ROOT = pathlib.Path(__file__).parent
GLYPHS = {
 'A':['01110','10001','10001','11111','10001','10001','10001'],
 'R':['11110','10001','10001','11110','10100','10010','10001'],
 'C':['01111','10000','10000','10000','10000','10000','01111'],
 'H':['10001','10001','10001','11111','10001','10001','10001'],
 'L':['10000','10000','10000','10000','10000','10000','11111'],
 'T':['11111','00100','00100','00100','00100','00100','00100'],
 'S':['01111','10000','10000','01110','00001','00001','11110'],
 'I':['11111','00100','00100','00100','00100','00100','11111'],
 'N':['10001','11001','11001','10101','10011','10011','10001'],
 'U':['10001','10001','10001','10001','10001','10001','01110'],
 'X':['10001','10001','01010','00100','01010','10001','10001'],
 'W':['10001','10001','10001','10101','10101','10101','01010'],
 'D':['11110','10001','10001','10001','10001','10001','11110'],
 'O':['01110','10001','10001','10001','10001','10001','01110'],
 ' ':['00000']*7,
}
def png(name, w, h, pixel):
 def chunk(kind, data):
  return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data)&0xffffffff)
 data=b''.join(b'\0'+bytes(v for x in range(w) for v in pixel(x,y)) for y in range(h))
 (ROOT/name).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b''))
def icon(text):
 def pixel(x,y):
  if 97 <= y < 159:
   if y in (97,158) or x in (0,255): return (60,60,60,255)
   tx=x-(256-(len(text)*18-3))//2; ty=y-118
   if tx>=0 and 0<=ty<21 and tx//18<len(text) and tx%18<15:
    if GLYPHS[text[tx//18]][ty//3][tx%18//3]=='1': return (212,212,212,255)
   return (37,37,38,255)
  return (30,30,30,255)
 return pixel
png('background.png',1,1,lambda x,y:(30,30,30,255))
for name,text in [('arch-lts.png','ARCH LTS'),('arch.png','ARCH'),('windows.png','WINDOWS')]: png(name,256,256,icon(text))
png('selection.png',272,272,lambda x,y:(0,122,204,255) if (104<=y<168 and (y in (104,105,166,167) or x in (6,7,264,265))) else (0,0,0,0))
png('field.png',360,48,lambda x,y:(0,122,204,255) if x in (0,359) or y in (0,47) else (37,37,38,255))
