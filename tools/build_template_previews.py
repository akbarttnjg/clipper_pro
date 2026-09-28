"""Rebuild the bundled gallery videos from the real typography engine (no AI)."""
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clipper.config import Config
from clipper.captions_pro import write_ass
from clipper.ffmpeg_util import ass_filter, probe
from clipper.looks import LOOKS
from clipper.font_catalog import FONTS


def demo_words():
    phrases = [('Cerita yang bermakna', .3), ('layak untuk didengar', 2.6),
               ('Mulai dari Rp 2,5 juta', 4.9), ('berani mengambil langkah', 7.2)]
    return [{'word': word, 'start': start+i*.32, 'end': start+i*.32+.30, 'word_id': n*10+i}
            for n, (text, start) in enumerate(phrases) for i, word in enumerate(text.split())]


def main():
    target = ROOT / 'static/templates'
    target.mkdir(exist_ok=True)
    cfg = Config(target_w=960, target_h=540, caption_position='left', title_card=False,
                 editorial_words=7, caption_gap_s=.7, use_nvenc=False)
    with tempfile.TemporaryDirectory(prefix='typography-gallery-') as tmp:
        for template in LOOKS:
            c = replace(cfg, **template['settings'])
            ass = write_ass(demo_words(), Path(tmp)/'demo.ass', c,
                            keywords=['bermakna','didengar','juta','langkah'])
            regular = str(Path(c.fonts_dir)/FONTS[c.font_main]['file'])
            bold = str(Path(c.fonts_dir)/FONTS[c.font_accent]['file'])
            background = (f'drawbox=x=480:y=100:w=1:h=330:color=0x283340:t=fill,'
                f"drawtext=fontfile='{regular}':text='CLIPPER  /  TYPOGRAPHY':fontsize=16:fontcolor=0x95a7b9:x=52:y=42,"
                f"drawtext=fontfile='{bold}':text='Aa':fontsize=144:fontcolor=0x263242:x=580:y=178,"
                f"drawtext=fontfile='{regular}':text='{template['name'].replace('&','dan')}':fontsize=22:fontcolor=0xf6cf69:x=550:y=363,"
                + ass_filter(ass,c))
            pending = Path(tmp) / (template['id']+'.mp4')
            subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','lavfi','-i',
                'color=c=0x111923:s=960x540:r=30:d=9.8','-vf',background,'-an','-c:v','libx264',
                '-preset','fast','-crf','22','-threads','3','-pix_fmt','yuv420p','-movflags','+faststart',
                str(pending)],check=True, stdin=subprocess.DEVNULL)
            meta = probe(pending)
            if meta['duration'] < 9.7:
                raise RuntimeError('Preview tidak lengkap: '+template['id'])
            import shutil
            shutil.copy2(pending, target/(template['id']+'.mp4'))
            subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
                '-ss','1.15','-i',str(pending),'-frames:v','1','-q:v','2',
                str(target/(template['id']+'.jpg'))],check=True,stdin=subprocess.DEVNULL)
            print(template['id'], flush=True)


if __name__ == '__main__':
    main()
