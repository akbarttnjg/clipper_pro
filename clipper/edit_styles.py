"""Whole-edit recipes; typography presets remain owned by looks.py."""
STYLES=[
 {'id':'balanced','name':'Cerita seimbang','description':'Pembicara dominan, gerak sedang, jeda alami dan ilustrasi seperlunya.',
  'settings':{'edit_style':'balanced','caption_style':'narrative','motion_intensity':'balanced','layout':'auto','punch_zoom':True,'zoom_amount':.06,'trim_silence':True,'silence_max':1.2,'broll_mode':'local','broll_max':2,'music_db':-28.,'cold_open':False}},
 {'id':'lesson','name':'Kelas dan papan tulis','description':'Materi lebar tetap terlihat, subtitel tenang, jeda menulis dipertahankan, tanpa sisipan stok.',
  'settings':{'edit_style':'lesson','caption_style':'clean','motion_intensity':'calm','layout':'stream','source_kind':'board','punch_zoom':False,'trim_silence':False,'preserve_material_pauses':True,'material_share':.68,'broll_mode':'off','music_db':-36.,'cold_open':False}},
 {'id':'energetic','name':'Cerita dinamis','description':'Pembicara memenuhi gambar, ritme lebih rapat, aksen kata kuat dan ilustrasi lokal kontekstual.',
  'settings':{'edit_style':'energetic','caption_style':'magazine','motion_intensity':'dynamic','layout':'fill','source_kind':'speaker','punch_zoom':True,'zoom_amount':.09,'zoom_gap':8.,'trim_silence':True,'silence_max':.8,'silence_keep':.18,'broll_mode':'local','broll_max':3,'music_db':-25.,'cold_open':False}},
 {'id':'podcast','name':'Percakapan santai','description':'Dua pembicara diberi ruang, pergantian kalimat utuh dan animasi lembut.',
  'settings':{'edit_style':'podcast','caption_style':'editorial','motion_intensity':'calm','layout':'auto','source_kind':'podcast','punch_zoom':False,'trim_silence':True,'silence_max':1.6,'silence_keep':.35,'broll_mode':'off','music_db':-32.,'cold_open':False}},
]


def recipe(name):
    item=next((s for s in STYLES if s['id']==name),None)
    if item is None:raise ValueError('Resep gaya tidak dikenal')
    return dict(item['settings'])
