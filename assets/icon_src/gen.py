import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parts import DEFS, PLATE, MARK
import math
def squircle(cx, cy, size, n=3.0, pts=90):
    e = 0.30*size; h = size/2
    corners = [(cx+h-e, cy-h+e, 0), (cx+h-e, cy+h-e, 90), (cx-h+e, cy+h-e, 180), (cx-h+e, cy-h+e, 270)]
    out=[]
    for (ox, oy, start) in corners:
        for i in range(pts+1):
            t = math.radians(start - 90 + 90*i/pts)
            c, s_ = math.cos(t), math.sin(t)
            out.append(f"{ox+e*math.copysign(abs(c)**(2/n),c):.2f},{oy+e*math.copysign(abs(s_)**(2/n),s_):.2f}")
    return "M"+" L".join(out)+" Z"

def svg(mode="mac", detail="full"):
    T = 824 if mode=="mac" else 1024
    k = 1.0 if mode=="mac" else 1.08
    if mode!="mac" and detail=="simple": k = 1.0
    sc = (0.84 if detail=="full" else 0.86)*k
    # plate bbox in source units: x 96..889, y 66.5..892.5; centre it, nudged right for the triangle's optical centre
    bx, by = (96+889)/2, (66.5+892.5)/2
    tx = 512 - bx*sc + 18*k; ty = 512 - by*sc
    tile = squircle(512,512,T)
    out=[f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs>{DEFS}
 <linearGradient id="t-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#24212B"/><stop offset="1" stop-color="#0B0A0E"/></linearGradient>
 <radialGradient id="t-bloom" cx="0.48" cy="0.5" r="0.5"><stop offset="0" stop-color="#FF4F7A" stop-opacity="0.26"/><stop offset="0.25" stop-color="#C255D9" stop-opacity="0.15"/><stop offset="0.5" stop-color="#9A5CFF" stop-opacity="0.07"/><stop offset="0.75" stop-color="#9A5CFF" stop-opacity="0.02"/><stop offset="1" stop-color="#9A5CFF" stop-opacity="0"/></radialGradient>
 <linearGradient id="t-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.22"/><stop offset="0.3" stop-color="#fff" stop-opacity="0.04"/><stop offset="1" stop-color="#fff" stop-opacity="0.08"/></linearGradient>
 <linearGradient id="p-fill" gradientUnits="userSpaceOnUse" x1="0" y1="66" x2="0" y2="893"><stop offset="0" stop-color="#131118"/><stop offset="1" stop-color="#060509"/></linearGradient>
 <linearGradient id="p-rim" gradientUnits="userSpaceOnUse" x1="0" y1="66" x2="0" y2="893"><stop offset="0" stop-color="#fff" stop-opacity="0.38"/><stop offset="0.35" stop-color="#fff" stop-opacity="0.09"/><stop offset="1" stop-color="#fff" stop-opacity="0.16"/></linearGradient>
 <filter id="t-shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#000" flood-opacity="0.5"/></filter>
 <filter id="p-shadow" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="{22/sc*k:.1f}" stdDeviation="{26/sc*k:.1f}" flood-color="#000" flood-opacity="0.6"/></filter>
 <clipPath id="t-clip"><path d="{tile}"/></clipPath>
</defs>''']
    if mode=="mac": out.append(f'<path d="{tile}" fill="#000" filter="url(#t-shadow)"/>')
    out.append(f'<path d="{tile}" fill="url(#t-bg)"/>')
    out.append(f'<g clip-path="url(#t-clip)"><rect width="1024" height="1024" fill="url(#t-bloom)"/></g>')
    out.append(f'<g transform="translate({tx:.2f} {ty:.2f}) scale({sc:.4f})">')
    out.append(f'<path d="{PLATE}" fill="#000" filter="url(#p-shadow)"/>')
    out.append(f'<path d="{PLATE}" fill="url(#p-fill)"/>')
    out.append(f'<path d="{PLATE}" fill="none" stroke="url(#p-rim)" stroke-width="{3.5/sc:.1f}" clip-path="url(#dam-plate)"/>')
    out.append(MARK)
    out.append('</g>')
    out.append(f'<path d="{tile}" fill="none" stroke="url(#t-rim)" stroke-width="{3*(T/824):.1f}" clip-path="url(#t-clip)"/>')
    out.append('</svg>')
    return "\n".join(out)

if __name__=="__main__":
    open(sys.argv[3],"w").write(svg(sys.argv[1], sys.argv[2]))
