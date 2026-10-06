"""Regression gates for the supplied 13-shot export and editor package states."""
import copy
import json
import shutil
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import pytest
from clipper import projects
from clipper.export_verify import package_path, validate_bundle
from clipper.storage import read_json, write_json
from clipper.timebase import (endpoint_range, frame_to_us, interval_issues,
                              seconds_to_us, video_track_ranges)

# Exact frame boundaries from the user's 97.366667 s / 30 fps export.
BOUNDARIES = [0, 109, 296, 460, 687, 905, 1057, 1166, 1251, 1491, 1744, 2054, 2514, 2921]


def shots(boundaries=BOUNDARIES, fps=30):
    return [dict(start=a/fps, end=b/fps, start_frame=a, duration_frames=b-a,
                 source_start=a/fps, source_end=b/fps, rect=[0, 0, 1080, 1920],
                 mode='fill', face_rect=None, zoom_at=None)
            for a, b in zip(boundaries, boundaries[1:])]


def test_supplied_thirteen_shots_have_no_microsecond_overlap_or_gap():
    plan = dict(shots=shots(), fps=30, duration=2921/30, duration_frames=2921)
    old = [(round(s['start']*1e6), round((s['end']-s['start'])*1e6)) for s in plan['shots']]
    assert sum(a+d > b for (a, d), (b, _) in zip(old, old[1:])) == 2
    assert sum(a+d < b for (a, d), (b, _) in zip(old, old[1:])) == 3
    ranges, duration = video_track_ranges(plan)
    assert all(a+d == b for (a, d), (b, _) in zip(ranges, ranges[1:]))
    assert ranges[-1][0] + ranges[-1][1] == duration == 97_366_667


@pytest.mark.parametrize('fps', [25, 30, 60, {'numerator': 30000, 'denominator': 1001}])
def test_frame_endpoints_preserve_rational_rate(fps):
    rate = Fraction(fps['numerator'], fps['denominator']) if isinstance(fps, dict) else Fraction(fps)
    plan = dict(shots=shots([0, 1, 109, 1001], rate), fps=fps,
                duration=float(1001/rate), duration_frames=1001)
    ranges, duration = video_track_ranges(plan)
    assert duration == round(1001 * 1_000_000 / rate)
    assert all(a+d == b for (a, d), (b, _) in zip(ranges, ranges[1:]))
    assert frame_to_us(1001, fps) == duration


def test_subtitle_and_audio_endpoints_keep_subframe_precision():
    a, d = endpoint_range(.010001, .042009)
    b, _ = endpoint_range(.042009, .075007)
    assert a == 10_001 and a+d == b == 42_009
    assert seconds_to_us(.010001) != frame_to_us(0, 30)


@pytest.mark.parametrize('ranges', [[(0, 5), (4, 10)], [(0, 5), (6, 10)], [(0, 0), (0, 10)], [(0, 11)]])
def test_invalid_video_intervals_are_rejected(ranges):
    assert interval_issues(ranges, duration=10, contiguous=True)


def test_adjacent_intervals_and_sparse_overlay_tracks_are_valid():
    assert not interval_issues([(0, 4), (4, 10)], duration=10, contiguous=True)
    assert not interval_issues([(1, 3), (7, 8)], duration=10)


@pytest.mark.parametrize('value', ['../outside.mp4', '/tmp/outside.mp4', 'C:/outside.mp4', 'file:///C:/outside.mp4'])
def test_portable_paths_reject_external_or_escaping_media(tmp_path, value):
    with pytest.raises(ValueError, match='luar paket'):
        package_path(tmp_path, value, 'C:/old/package')


def test_windows_file_uri_relocates_with_package(tmp_path):
    assert package_path(tmp_path, 'file:///C:/old/package/Media/clip%201.mp4', 'C:/old/package') == tmp_path/'Media/clip 1.mp4'


@pytest.fixture
def media_metadata(monkeypatch):
    """Control MediaInfo only; use the real pycapcut segment/track serializer.

    These unit files are synthetic. They do not test decoding or native import.
    """
    cc = pytest.importorskip('pycapcut')
    import pymediainfo
    monkeypatch.setattr(pymediainfo.MediaInfo, 'can_parse', staticmethod(lambda: True))
    def parse(path, **kwargs):
        width,height=(1920,1080) if Path(path).name.startswith('02-') else (1080,1920)
        video = [] if Path(path).suffix == '.wav' else [SimpleNamespace(duration=100_000, width=width, height=height)]
        return SimpleNamespace(video_tracks=video, audio_tracks=[] if video else [SimpleNamespace(duration=100_000)],
                               general_tracks=[], image_tracks=[])
    monkeypatch.setattr(pymediainfo.MediaInfo, 'parse', staticmethod(parse))
    return cc


@pytest.fixture
def package(tmp_path, media_metadata):
    root = tmp_path/'package';(root/'Media').mkdir(parents=True);(root/'Fonts').mkdir()
    shutil.copyfile(Path(projects.__file__).with_name('project_install.py'), root/'PASANG_PROYEK.py')
    for filename in ('BACA_DULU.txt', 'PASANG_CAPCUT.cmd', 'SIAPKAN_DAVINCI.cmd'):
        (root/filename).write_text('Unit package instructions\n')
    font = Path(__file__).resolve().parents[1]/'fonts/DMSans-SemiBold.ttf'
    shutil.copyfile(font, root/'Fonts'/font.name)
    for filename in ('01-video-clean.mp4', '01-speech.wav', '01-broll-01.mp4', '01-reference.mp4'):
        (root/'Media'/filename).write_bytes(b'unit-test-media')
    word = dict(text='Jangan', start=1., end=1.5, family='DM Sans', style='SemiBold',
                font_id='dm_sans', file=font.name, size=50, x=540, y=1500, emphasis=False, bold=False)
    plan = dict(shots=shots(), fps=30, duration=2921/30, duration_frames=2921,
                width=1080, height=1920, revision=3,
                source=dict(path=str(root/'Media/01-video-clean.mp4'), fps=30, width=1080, height=1920, duration=100),
                audio=dict(stems={'speech':str(root/'Media/01-speech.wav')}),
                captions=dict(phrases=[dict(start=1., end=2., words=[word, {**word, 'text':'terburu-buru', 'x':600}])]),
                style=dict(base='#FFFFFF', accent='#FFCC66', caption_style='editorial'),
                broll=[dict(path=str(root/'Media/01-broll-01.mp4'), start=4., end=5., duration=1.)])
    result = dict(title='Cerita', revision=3, plan=plan, plan_path=str(root/'original-edit-plan-01.json'),
                  absolute_file=str(root/'Media/01-reference.mp4'))
    write_json(root/'edit-plan-01.json', plan);write_json(result['plan_path'], plan)
    write_json(root/'manifest.json', dict(created_root=str(root), timelines=1,
        source_files=[plan['source']['path']],
        capcut_status='experimental-generated', resolve_status='generated-unverified-in-editor'))
    (root/'Media/01-captions.ass').write_text('[Script Info]\n')
    projects.write_srt(plan, root/'Media/01-captions.srt')
    write_json(root/'Media/01-credits.json', []);(root/'Media/01-credits.txt').write_text('')
    projects.resolve_export([result], root)
    projects.capcut_export([result], root)
    return root, result


def test_real_draft_serializer_accepts_thirteen_connected_shots(package):
    root, result = package
    data = read_json(root/'CapCut/CLIP_01/draft_content.json')
    segments = next(t for t in data['tracks'] if t['type']=='video')['segments']
    ranges = [s['target_timerange'] for s in segments]
    assert len(ranges) == 13
    assert all(a['start']+a['duration']==b['start'] for a,b in zip(ranges,ranges[1:]))
    report = validate_bundle(root, [result])
    assert report['issues'] == []
    assert report['structural_status'] == 'passed'
    assert all(e['construction_status']=='generated' and e['structural_status']=='passed'
               and e['native_status']=='not_tested' for e in report['editors'].values())
    assert all(e['status']=='requires_local_import' for e in report['native_tests'])


def test_missing_capcut_draft_cannot_pass_with_valid_resolve_xml(package):
    root, result = package
    (root/'CapCut/CLIP_01/draft_content.json').unlink()
    report = validate_bundle(root, [result])
    assert report['structural_status'] == 'needs_review'
    assert report['editors']['capcut']['import_status'] == 'blocked'
    assert report['editors']['resolve']['structural_status'] == 'passed'


def test_construction_error_blocks_capcut_even_when_draft_exists(package):
    root, result = package
    path = root/'manifest.json';manifest=read_json(path)
    manifest.update(capcut_status='failed', capcut_error='Simulated partial generation')
    write_json(path, manifest)
    report = validate_bundle(root, [result])
    assert report['editors']['capcut']['construction_status'] == 'failed'
    assert 'Simulated partial generation' in report['editors']['capcut']['issues']
    assert report['editors']['resolve']['structural_status'] == 'passed'


@pytest.mark.parametrize('filename', ['Media/01-video-clean.mp4', 'Media/01-speech.wav', 'Media/01-broll-01.mp4',
                                      'Media/01-captions.ass', 'Fonts/DMSans-SemiBold.ttf', 'DaVinci/clip-01/text-001.comp'])
def test_required_files_are_checked_by_editor(package, filename):
    root, result = package
    (root/filename).unlink()
    report = validate_bundle(root, [result])
    assert report['structural_status'] == 'needs_review'
    assert any(filename in issue for issue in report['issues'])
    if filename.startswith('DaVinci/'):
        assert report['editors']['capcut']['structural_status'] == 'passed'
    else:
        assert all(e['structural_status']=='failed' for e in report['editors'].values())


def test_capcut_overlap_is_detected_per_track(package):
    root, result = package
    path = root/'CapCut/CLIP_01/draft_content.json';data=read_json(path)
    data['tracks'][0]['segments'][1]['target_timerange']['start'] -= 1
    write_json(path, data)
    report = validate_bundle(root, [result])
    assert any('tumpang tindih 1' in issue for issue in report['editors']['capcut']['issues'])
    assert report['editors']['resolve']['structural_status'] == 'passed'


def test_bad_font_identity_is_reported(package):
    root, result = package
    path=root/'edit-plan-01.json';plan=read_json(path)
    plan['captions']['phrases'][0]['words'][0]['family']='Wrong font family'
    write_json(path, plan)
    report=validate_bundle(root,[result])
    assert any('Identitas font berbeda' in issue for issue in report['issues'])


def test_relocated_complete_package_keeps_valid_media_references(package, tmp_path):
    root, result = package
    assert validate_bundle(root, [result])['issues'] == []
    newroot = tmp_path/'moved';shutil.copytree(root, newroot)
    result = {**result, 'plan_path':str(newroot/'original-edit-plan-01.json'), 'absolute_file':str(newroot/'Reference/01-reference.mp4')}
    report = validate_bundle(newroot, [result])
    assert report['issues'] == []


def test_resolve_title_uses_separate_fourth_track_when_broll_present(package):
    root, result = package
    plan=copy.deepcopy(result['plan']);word=plan['captions']['phrases'][0]['words'][0]
    plan['captions']['title']={**word,'end':3.,'start':0.}
    other=root/'title-test';(other/'Media').mkdir(parents=True)
    projects.resolve_export([{**result,'plan':plan}],other)
    assert 'GetItemListInTrack("video", 4)' in (other/'DaVinci/IMPORT_RESOLVE.lua').read_text()


def test_installer_blocks_failed_structure_before_index_changes(package, tmp_path):
    from clipper.project_install import install_capcut
    root, result=package
    (root/'CapCut/CLIP_01/draft_content.json').unlink()
    write_json(root/'verification.json',validate_bundle(root,[result]))
    draft_root=tmp_path/'user-drafts';draft_root.mkdir();index=draft_root/'root_meta_info.json'
    write_json(index,{'all_draft_store':[]});before=index.read_bytes()
    with pytest.raises(ValueError,match='belum lengkap'):
        install_capcut(root,draft_root,check_running=False)
    assert index.read_bytes()==before
    assert list(draft_root.iterdir())==[index]


def test_installer_checks_asset_hash_and_allows_relocation(package, tmp_path):
    from clipper.project_install import install_capcut
    root, result=package
    write_json(root/'verification.json',validate_bundle(root,[result]))
    newroot=tmp_path/'relocated';shutil.copytree(root,newroot)
    draft_root=tmp_path/'user-drafts';draft_root.mkdir();index=draft_root/'root_meta_info.json'
    write_json(index,{'all_draft_store':[]})
    created,backup=install_capcut(newroot,draft_root,check_running=False)
    assert len(created)==1 and backup.is_file()
    assert newroot.as_posix() in (created[0]/'draft_content.json').read_text()
    before=index.read_bytes();(newroot/'Media/01-speech.wav').write_bytes(b'altered')
    with pytest.raises(ValueError,match='Isi aset paket berubah'):
        install_capcut(newroot,draft_root,check_running=False)
    assert index.read_bytes()==before


def test_windows_escaped_paths_and_nested_fonts_relink(tmp_path):
    from clipper.project_install import relink
    root=tmp_path/'project-one';(root/'Media').mkdir(parents=True);(root/'Fonts').mkdir()
    (root/'Media/01-video-clean.mp4').write_bytes(b'packaged-media')
    old='C:/AI/clipper/project-one';windows=old.replace('/', '\\')
    # Reproduce the supplied ZIP: created_root was already changed to Downloads,
    # while source_files retained doubly escaped paths under the original root.
    write_json(root/'manifest.json',dict(created_root='C:/Users/User/Downloads/project-one',
        source_files=[windows.replace('\\', '\\\\')+'\\\\Media\\\\01-video-clean.mp4']))
    body=dict(content=json.dumps(dict(styles=[dict(font=dict(path=windows+'\\Fonts\\DMSans-SemiBold.ttf'))])),
              source=windows+'\\Media\\01-video-clean.mp4',original_source='C:/Elsewhere/original.mp4')
    write_json(root/'draft.json',body)
    (root/'timeline.xml').write_text('<pathurl>file:///C:/AI/clipper/project-one/Media/01-video-clean.mp4</pathurl>')
    manifest=relink(root);data=read_json(root/'draft.json')
    assert manifest['source_files']==[str(root/'Media/01-video-clean.mp4')]
    assert data['source']==str(root/'Media/01-video-clean.mp4')
    assert json.loads(data['content'])['styles'][0]['font']['path']==str(root/'Fonts/DMSans-SemiBold.ttf')
    assert data['original_source']=='C:/Elsewhere/original.mp4'
    assert (root/'Media/01-video-clean.mp4').as_uri() in (root/'timeline.xml').read_text()


@pytest.mark.parametrize('failed_editor', ['capcut', 'resolve', None])
def test_bundle_returns_honest_independent_editor_status(package,tmp_path,monkeypatch,failed_editor):
    from clipper import render,qc
    from clipper.config import Config
    root,result=package;plan=read_json(result['plan_path'])
    plan['broll']=[];plan['audio']['mix']=plan['audio']['stems']['speech']
    plan['subtitle_path']=str(root/'Media/01-captions.ass');write_json(result['plan_path'],plan)
    monkeypatch.setattr(render,'video',lambda source,plan,cfg,ass,target,audio,progress:Path(target).write_bytes(b'unit-clean-render'))
    monkeypatch.setattr(qc,'inspect',lambda *a,**kw:dict(passed=True))
    if failed_editor:
        def fail(*args,**kwargs):raise ValueError('Simulated '+failed_editor+' failure')
        monkeypatch.setattr(projects,failed_editor+'_export',fail)
    cfg=Config(out_dir=str(tmp_path/'exports'),work_dir=str(tmp_path/'work'),use_nvenc=False)
    bundle=projects.export_bundle([result],cfg)
    assert Path(bundle['zip']).is_file()
    assert bundle['export_mode']=='hybrid' and bundle['native_editor_status']=='not_tested'
    report=read_json(Path(bundle['folder'])/'verification.json')
    manifest=read_json(Path(bundle['folder'])/'manifest.json')
    assert manifest['editors']==report['editors']==bundle['editors']
    if failed_editor:
        assert bundle['structural_status']=='needs_review'
        assert bundle['editors'][failed_editor]['construction_status']=='failed'
        other='resolve' if failed_editor=='capcut' else 'capcut'
        assert bundle['editors'][other]['structural_status']=='passed'
    else:
        assert report['issues']==[]


def test_inconsistent_frame_and_second_clocks_are_rejected():
    plan=dict(shots=shots(),fps=30,duration=2921/30,duration_frames=2921)
    plan['shots'][1]['end']+=1
    with pytest.raises(ValueError,match='Batas frame shot berbeda'):
        video_track_ranges(plan)


def test_reference_hash_must_match_validated_final(package):
    from clipper.dependency_cache import content_id
    root,result=package
    result['output_content_id']=content_id(result['absolute_file'])
    Path(result['absolute_file']).write_bytes(b'altered-final')
    report=validate_bundle(root,[result])
    assert any('Reference berbeda dari render final' in issue for issue in report['issues'])


def test_version_four_installer_requires_editor_verification(package,tmp_path):
    from clipper.project_install import install_capcut
    root,result=package
    manifest=read_json(root/'manifest.json');manifest['version']=4;write_json(root/'manifest.json',manifest)
    write_json(root/'verification.json',dict(schema_version=2,editors={}))
    with pytest.raises(ValueError,match='pemeriksaan paket tidak tersedia'):
        install_capcut(root,tmp_path/'unused-drafts',check_running=False)
    assert not (tmp_path/'unused-drafts').exists()


def test_two_distinct_clips_keep_independently_selected_ratios(package):
    root,first=package
    second=copy.deepcopy(first['plan']);second.update(width=1920,height=1080,duration=1574/30,duration_frames=1574)
    second['shots']=shots([0,109,296,460,700,1000,1574])
    for shot in second['shots']:shot['rect']=[0,0,1920,1080]
    second['source'].update(path=str(root/'Media/02-video-clean.mp4'),width=1920,height=1080)
    second['audio']['stems']['speech']=str(root/'Media/02-speech.wav');second['broll']=[]
    for word in second['captions']['phrases'][0]['words']:word.update(x=960,y=900)
    for filename in ('02-video-clean.mp4','02-speech.wav','02-reference.mp4'):
        (root/'Media'/filename).write_bytes(b'second-unit-media')
    second_result=dict(title='Cerita lain',plan=second,revision=3,plan_path=str(root/'original-edit-plan-02.json'),
                       absolute_file=str(root/'Media/02-reference.mp4'))
    write_json(root/'edit-plan-02.json',second);write_json(second_result['plan_path'],second)
    projects.write_srt(second,root/'Media/02-captions.srt');(root/'Media/02-captions.ass').write_text('[Script Info]\n')
    write_json(root/'Media/02-credits.json',[]);(root/'Media/02-credits.txt').write_text('')
    manifest=read_json(root/'manifest.json');manifest.update(timelines=2,source_files=[first['plan']['source']['path'],second['source']['path']])
    write_json(root/'manifest.json',manifest)
    for name in ('CapCut','DaVinci'):shutil.rmtree(root/name)
    projects.resolve_export([first,second_result],root);projects.capcut_export([first,second_result],root)
    report=validate_bundle(root,[first,second_result]);assert report['issues']==[]
    wrapper=read_json(root/'CapCut/CLIPPER_ALL_TIMELINES/Timelines/project.json')
    ids=[t['id'] for t in wrapper['timelines']]
    assert len(set(ids))==2
    assert [read_json(root/'CapCut/CLIPPER_ALL_TIMELINES/Timelines'/ident/'draft_content.json')['name'] for ident in ids]==['Cerita','Cerita lain']
    assert [(r['width'],r['height'],r['duration_us']) for r in report['timelines']]==[(1080,1920,97_366_667),(1920,1080,52_466_667)]
