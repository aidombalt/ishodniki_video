import json, subprocess, numpy as np, sys
from PIL import Image
W = '/tmp/claude-0/-home-user-ishodniki-video/7fdd3399-3b0b-583b-a74f-2847502fb422/scratchpad/'
tl = json.load(open(W + 'work/timeline.json')); st = json.load(open(W + 'work/framestats.json'))
cuts = [d['cut'] for d in tl['timeline']]
t = np.array([s[0] for s in st]); lum = np.array([s[1] for s in st]); dif = np.array([s[2] for s in st])
probs = []
for i in range(1, len(t)):
    near = min(abs(t[i] - c) for c in cuts) < 0.75
    if dif[i] > 6 and not near: probs.append('jump %.2f diff %.1f' % (t[i], dif[i]))
    if lum[i] > 254.9 and not near and t[i] > 0.6: probs.append('blank %.2f' % t[i])
    if not np.isfinite(lum[i]): probs.append('nan %.2f' % t[i])
print('frames', len(t), 'max diff outside cuts', max([dif[i] for i in range(1, len(t)) if min(abs(t[i] - c) for c in cuts) >= 0.75]))
print('\n'.join(probs[:40]) or 'no glitches')
# rest-moment stills from the delivered subtitled file
moments = []
names = [d['name'] for d in tl['timeline']]
for i, d in enumerate(tl['timeline']):
    nxt = tl['timeline'][i + 1]['cut'] if i + 1 < len(tl['timeline']) else tl['total']
    moments.append((d['name'], round(min(d.get('t1', d['cut'] + 2.5) - 0.3, nxt - 0.4), 2)))
moments.append(('final', round(tl['total'] - 0.2, 2)))
for name, w, cols in (('sheet640.jpg', 640, 4), ('sheet390.jpg', 390, 4)):
    h = int(w * 9 / 16); ims = []
    for n, tt in moments:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(tt), '-i', W + 'out/subs.mp4', '-frames:v', '1', '-vf', 'scale=%d:%d:flags=lanczos' % (w, h), '/tmp/claude-0/-home-user-ishodniki-video/7fdd3399-3b0b-583b-a74f-2847502fb422/scratchpad/work/_f.png'])
        ims.append(Image.open(W + 'work/_f.png').convert('RGB'))
    rows = (len(ims) + cols - 1) // cols; S = Image.new('RGB', (cols * (w + 6), rows * (h + 6)), (110, 110, 110))
    for i, im in enumerate(ims): S.paste(im, ((i % cols) * (w + 6), (i // cols) * (h + 6)))
    S.save(W + 'out/' + name, quality=90)
print(moments)
