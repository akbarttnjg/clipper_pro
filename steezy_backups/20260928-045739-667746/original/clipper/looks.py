"""Complete, versioned looks. Motion can be changed independently after selection."""
VISUAL_FIELDS = {'caption_style','motion_intensity','caption_scale','accent_hex','accent_font',
                 'font_main','font_accent','caption_backdrop','safe_placement'}


def look(ident, name, description, motion, main, accent, color, intensity='calm'):
    return {'id':ident, 'name':name, 'description':description,
            'settings':{'caption_style':motion,'font_main':main,'font_accent':accent,
                        'accent_hex':color,'accent_font':True,'caption_scale':1.,
                        'motion_intensity':intensity,'caption_backdrop':True,'safe_placement':True}}


LOOKS = (
    look('elegan','Editorial elegan','Sans yang rapi + serif miring untuk penekanan.','narrative','dm_sans','dm_serif_italic','#F6D582'),
    look('tegas','Angka tegas','Huruf padat untuk angka dan istilah penting.','impact','dm_sans','bebas','#FFC857','balanced'),
    look('kelas','Ruang belajar','Susunan tenang, jelas untuk edukasi dan materi.','slide','dm_sans','montserrat','#8BDBC2'),
    look('fokus','Fokus lembut','Serif dengan masuk blur yang singkat.','blur','dm_sans','dm_serif','#E9D7BA'),
    look('energi','Pop editorial','Montserrat + aksen serif dengan pop terukur.','pop','montserrat','dm_serif_italic','#DCC8FF','balanced'),
)
