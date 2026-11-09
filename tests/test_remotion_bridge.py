"""Exercise real local inputs, immutable preparation and exported lineage."""
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
import pytest

from workflow.batch import new_batch
from workflow.desktop_delivery import digest
from workflow.store import Asset, Job, JobAsset, database
from workflow.remotion_bridge import prepare, render, validate_render_record


@pytest.fixture
def package(tmp_path):
    data = tmp_path / 'data'
    (data / 'media').mkdir(parents=True)
    video = data / 'media' / 'asset_demo.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                    '-i', 'testsrc2=s=180x320:r=30:d=2', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(video)], check=True)
    engine, sessions = database(data)
    with sessions.begin() as session:
        session.add(Job(id='job_demo', status='NEW', payload={
            'count': 2, 'product': '测试', 'market': 'MX', 'batch': new_batch(2)}))
        session.add(Asset(id='asset_demo', filename='原片', media_path=video.name, thumbnail_path='',
                          sha256=digest(video), metadata_json={}))
        session.flush()
        session.add(JobAsset(job_id='job_demo', asset_id='asset_demo'))
    srt = tmp_path / '原片.srt'
    srt.write_text('1\n00:00:00,200 --> 00:00:01,600\nMira el producto\n', encoding='utf-8')
    request = {'schema_version': 1, 'job_id': 'job_demo', 'ordinal': 1,
               'chatcut_project_id': 'chatcut_actual', 'video_path': str(video),
               'srt_path': str(srt), 'audio_mode': 'silent',
               'base_subtitles_burned_in': False,
               'sources': [{'asset_id': 'asset_demo', 'sha256': digest(video)}],
               'title': 'Producto', 'cta': 'Descubre más',
               'cards': [{'text': 'Uso diario', 'start': .5, 'end': 1.5}],
               'delivery_explanation_zh': '本地镜头与统一包装', 'delivery_text_zh': '商品展示'}
    yield data, sessions, request, tmp_path / '包装'
    engine.dispose()


def test_preparation_binds_local_files_and_converts_subtitle_times(package):
    data, sessions, request, output = package
    prepared = prepare(request, output, data, sessions)
    props = json.loads((output / 'props.json').read_text(encoding='utf-8'))
    assert props['durationInFrames'] == 60
    assert props['captions'][0]['startMs'] == 200
    assert props['captions'][0]['endMs'] == 1600
    assert props['video'] == 'base.mp4'
    assert prepared['chatcut_project_id'] == 'chatcut_actual'
    assert 'review' not in prepared
    assert digest(output / 'media/base.mp4') == digest(Path(request['video_path']))
    assert prepare(request, output, data, sessions) == prepared
    (output / 'media/base.mp4').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='变化|损坏'):
        prepare(request, output, data, sessions)


@pytest.mark.parametrize('change', [
    {'video_path': 'https://example.invalid/source.mp4'},
    {'base_subtitles_burned_in': True}, {'audio_mode': 'narration'},
    {'ordinal': 3}, {'cards': [{'text': 'Bad', 'start': 0, 'end': 4}]},
    {'sources': [{'asset_id': 'asset_other', 'sha256': 'a' * 64}]},
    {'title': 'a' * 81}, {'unexpected': 'value'},
])
def test_rejects_invalid_requests_before_creating_package(package, change):
    data, sessions, request, output = package
    with pytest.raises(ValueError):
        prepare({**request, **change}, output, data, sessions)
    assert not output.exists()


def test_failed_renderer_cannot_count_or_publish_delivery(package, monkeypatch):
    data, sessions, request, output = package
    prepare(request, output, data, sessions)
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'node')
    monkeypatch.setattr('workflow.remotion_bridge.subprocess.run', fail)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        render(output, data, sessions)
    assert not (output / 'rendered').exists()
    with sessions() as session:
        assert session.get(Job, 'job_demo').payload['batch']['rendered_count'] == 0


def test_render_record_rejects_unrelated_video_or_sources(tmp_path):
    video = tmp_path / 'video.mp4'; video.write_bytes(b'video')
    record = tmp_path / 'record.json'
    record.write_text(json.dumps({'engine': 'remotion', 'video_sha256': 'a' * 64,
                                  'sources': []}), encoding='utf-8')
    with pytest.raises(ValueError):
        validate_render_record(record, video, [], 'job_demo', 1)


@pytest.mark.skipif(__import__('os').environ.get('REMOTION_SMOKE') != '1',
                    reason='explicit real Remotion/Chromium render smoke')
@pytest.mark.parametrize('mode', ['silent', 'narration'])
def test_real_render_decode_resume_and_delivery(package, mode, monkeypatch):
    from datetime import datetime, timezone
    from workflow.desktop_delivery import register_delivery
    data, sessions, request, output = package
    if mode == 'narration':
        voiced = output.parent / '合成音轨底片.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', request['video_path'],
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                        '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(voiced)], check=True)
        request['video_path'] = str(voiced)
        request['audio_mode'] = mode
    prepare(request, output, data, sessions)
    result = render(output, data, sessions)
    final = output / 'rendered'
    assert result['status'] == 'RENDERED_PENDING_REVIEW'
    assert load_json(final / 'qa.json')['has_audio'] == (mode == 'narration')
    manifest = load_json(final / 'delivery-manifest.template.json')
    with pytest.raises(ValueError):
        register_delivery(data, sessions, 'job_demo', 1, manifest)
    assert render(output, data, sessions) == result
    saved_record = (final / 'render-record.json').read_bytes()
    damaged = load_json(final / 'render-record.json')
    del damaged['files']['subtitles.srt']
    (final / 'render-record.json').write_text(json.dumps(damaged), encoding='utf-8')
    with pytest.raises(ValueError, match='指纹|清单'):
        render(output, data, sessions)
    (final / 'render-record.json').write_bytes(saved_record)
    manifest['review'] = {'reviewer': 'automated-test-fixture',
                          'reviewed_at': datetime.now(timezone.utc).isoformat(),
                          'visual': {'passed': True, 'evidence': '合成测试专用复核字段，不代表客户验收'}}
    if mode == 'narration':
        manifest['review']['listening'] = {'passed': True, 'evidence': '测试正弦波，不代表真人配音质量'}
    registered = register_delivery(data, sessions, 'job_demo', 1, manifest)
    assert registered['rendered_count'] == 1
    assert Path(registered['paths']['render-record.json']).is_file()
    # Changing final bytes invalidates both resume and new delivery.
    with (final / 'final.mp4').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='不匹配'):
        render(output, data, sessions)


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.skipif(__import__('os').environ.get('REMOTION_SMOKE') != '1',
                    reason='explicit Remotion layout failure smoke')
def test_overflowing_copy_fails_instead_of_clipping(package):
    data, sessions, request, output = package
    request['cta'] = '商品' * 30
    prepare(request, output, data, sessions)
    with pytest.raises(subprocess.CalledProcessError):
        render(output, data, sessions)
    assert not (output / 'rendered').exists()
    assert 'Text does not fit' in (output / 'render.log').read_text(encoding='utf-8')
