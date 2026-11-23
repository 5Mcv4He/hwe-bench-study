"""Render repository composition and unresolved tasks using separate linear axes."""
import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font', required=True, help='Path to a CJK TrueType or OpenType font')
args = parser.parse_args()
rows = list(csv.DictReader((root / 'evidence/projects.csv').open()))
image = Image.new('RGB', (1360,660), '#ffffff')
draw = ImageDraw.Draw(image)
def label(x,y,string,size=25,fill='#203341',anchor='lm'):
    draw.text((x,y),str(string),font=ImageFont.truetype(args.font,size),fill=fill,anchor=anchor)

def axis(start, end, ticks):
    for value in ticks:
        x = round(start + (end-start)*value/ticks[-1])
        draw.line((x,174,x,528),fill='#e2e8eb',width=2)
        label(x,557,value,20,'#4d6470','mm')

def bar(x,y,width,color):
    if width:
        draw.rectangle((x,y-7,x+width,y+7),fill=color)

label(48,53,'417 道题来自哪里？两个系统分别留下多少未解？',41)
label(48,108,'HWE-bench v1.1   /   两栏独立刻度，单位均为题',23,'#526976')
label(204,155,'任务数',25)
label(835,155,'未解题数',25)
axis(205,705,[0,50,100,150,200,250])
axis(835,1255,[0,5,10,15])
for i,r in enumerate(rows):
    y=204+59*i
    label(48,y,r['project'],24)
    n=int(r['tasks'])
    bar(205,y,n*2,'#39627a');label(215+n*2,y,n,20)
    for col,dy,color in [('claude_unsolved',-10,'#9c492b'),('deepseek_unsolved',11,'#087e77')]:
        n=int(r[col]);bar(835,y+dy,n*28,color);label(843+n*28,y+dy,n,18,color)
for x,col,name in [(205,'#39627a','任务总数'),(605,'#9c492b','Opus 5.5 + Claude Code'),(940,'#087e77','V4.1 Flash 1017 + DSH')]:
    draw.rectangle((x,604,x+20,620),fill=col);label(x+30,613,name,21)
image.save(root/'figures/project-results.png',optimize=True)
