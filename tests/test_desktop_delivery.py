"""Real decode, persistence, ownership and immutable delivery regression coverage."""
from copy import deepcopy
import subprocess

import imageio_ffmpeg
import pytest

from workflow.batch import new_batch
from workflow.desktop_delivery import digest, register_delivery
from workflow.store import Asset, Job, JobAsset, database


@pytest.fixture
def delivery(tmp_path):
    data = tmp_path / 'runtime'
    (data / 'media').mkdir(parents=True)
    video = tmp_path / 'export.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                    '-i', 'color=c=blue:s=180x320:r=25:d=1', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-y', str(video)], check=True)
    source = data / 'media' / 'source.mp4'
    source.write_bytes(video.read_bytes())
    engine, sessions = database(data)
    with sessions.begin() as session:
        session.add(Job(id='job_test', payload={'count': 2, 'batch': new_batch(2)}))
        session.add(Asset(id='asset_test', sha256=digest(source), filename='source.mp4',
                          media_path='source.mp4', thumbnail_path='unused.jpg', metadata_json={}))
        session.flush()
        session.add(JobAsset(job_id='job_test', asset_id='asset_test'))
    manifest = {'project_id': 'actual-project-test', 'sources': [{'asset_id': 'asset_test',
                'sha256': digest(source)}], 'video_path': str(video), 'expected_duration': 1,
                'audio_mode': 'silent', 'delivery_explanation_zh': '合成回归交付说明',
                'delivery_text_zh': '合成视频回归', 'review': {'reviewer': 'test-fixture',
                'reviewed_at': '2026-11-09T12:00:00+08:00', 'visual': {'passed': True,
                'evidence': '测试夹具预期纯蓝一秒竖屏；此记录仅测试调用方证据持久化，不是商品验收。'}}}
    yield data, sessions, manifest
    engine.dispose()


def test_delivery_counts_reuse_and_no_user_approval(delivery):
    data, sessions, manifest = delivery
    first = register_delivery(data, sessions, 'job_test', 1, manifest)
    assert first['rendered_count'] == 1
    assert first['job_status'] == 'PARTIALLY_DELIVERED'
    assert register_delivery(data, sessions, 'job_test', 1, manifest) == first
    second = register_delivery(data, sessions, 'job_test', 2, manifest)
    assert second['rendered_count'] == 2
    with sessions() as session:
        job = session.get(Job, 'job_test')
        assert job.status == 'LOCAL_DELIVERED'
        assert job.payload['batch']['rendered_count'] == 2
        assert job.payload['batch']['items'][0]['human_approval_status'] == 'pending_user'


@pytest.mark.parametrize('change', ['foreign', 'hash', 'missing', 'url', 'review', 'duration', 'audio'])
def test_reject_invalid_manifest(delivery, change):
    data, sessions, manifest = delivery
    if change == 'foreign':
        manifest['sources'][0]['asset_id'] = 'foreign'
    elif change == 'hash':
        manifest['sources'][0]['sha256'] = '0' * 64
    elif change == 'missing':
        manifest['video_path'] = '/not-here.mp4'
    elif change == 'url':
        manifest['video_path'] = 'https://example.test/export.mp4'
    elif change == 'review':
        del manifest['review']['visual']
    elif change == 'duration':
        manifest['expected_duration'] = 9
    else:
        manifest['audio_mode'] = 'narration'
    with pytest.raises(ValueError):
        register_delivery(data, sessions, 'job_test', 1, manifest)


def test_tampered_reuse_and_overwrite(delivery):
    from pathlib import Path
    data, sessions, manifest = delivery
    result = register_delivery(data, sessions, 'job_test', 1, manifest)
    changed = deepcopy(manifest)
    changed['project_id'] = 'different-project'
    with pytest.raises(ValueError, match='覆盖'):
        register_delivery(data, sessions, 'job_test', 1, changed)
    Path(result['paths']['video.mp4']).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='损坏'):
        register_delivery(data, sessions, 'job_test', 1, manifest)


def test_stale_source_and_bad_subtitles(delivery, tmp_path):
    data, sessions, manifest = delivery
    srt = tmp_path / 'bad.srt'
    srt.write_text('1\n00:00:00,000 --> 00:00:02,000\n测试\n', encoding='utf-8', newline='\n')
    manifest['srt_path'] = str(srt)
    with pytest.raises(ValueError, match='超出'):
        register_delivery(data, sessions, 'job_test', 1, manifest)
    del manifest['srt_path']
    (data / 'media' / 'source.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError, match='SHA256'):
        register_delivery(data, sessions, 'job_test', 1, manifest)


def test_narration_requires_audio_listening_and_valid_srt(delivery, tmp_path):
    data, sessions, manifest = delivery
    audio_video = tmp_path / 'narrated.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', manifest['video_path'],
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'copy',
                    '-c:a', 'aac', '-shortest', '-y', str(audio_video)], check=True)
    srt = tmp_path / 'narrated.srt'
    srt.write_text('1\n00:00:00,000 --> 00:00:00,900\n测试\n', encoding='utf-8', newline='\n')
    manifest.update(audio_mode='narration', video_path=str(audio_video), srt_path=str(srt))
    with pytest.raises(ValueError, match='listening'):
        register_delivery(data, sessions, 'job_test', 1, manifest)
    manifest['review']['listening'] = {'passed': True, 'evidence': '合成单音测试夹具，非真实配音验收。'}
    result = register_delivery(data, sessions, 'job_test', 1, manifest)
    assert result['media_qa']['has_audio'] is True
    assert result['subtitle_qa']['cue_count'] == 1


@pytest.mark.parametrize('content', [
    '',
    '1\ninvalid --> invalid\n文字\n',
    '1\n00:00:00,100 --> 00:00:00,900\n文字\n\n2\n00:00:00,800 --> 00:00:00,950\n文字\n',
    '1\n00:00:00,000 --> 00:00:00,900\n\n',
])
def test_malformed_subtitle_times_and_empty_text(tmp_path, content):
    from workflow.desktop_delivery import validate_subtitles
    path = tmp_path / 'invalid.srt'
    path.write_text(content, encoding='utf-8', newline='\n')
    with pytest.raises(ValueError):
        validate_subtitles(path, 1)


def test_standalone_cli_persists_job(delivery, tmp_path):
    import json
    import os
    from pathlib import Path
    import sys
    data, sessions, manifest = delivery
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8', newline='\n')
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'deliver_chatcut.py'
    result = subprocess.run([sys.executable, str(script), '--job-id', 'job_test',
                             '--ordinal', '1', '--manifest', str(path)],
                            env={**os.environ, 'WORKFLOW_DATA_DIR': str(data)},
                            text=True, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['rendered_count'] == 1
    with sessions() as session:
        assert session.get(Job, 'job_test').payload['batch']['rendered_count'] == 1


def test_chinese_text_files_are_packaged_and_integrity_checked(delivery):
    from pathlib import Path
    data, sessions, manifest = delivery
    result = register_delivery(data, sessions, 'job_test', 1, manifest)
    explanation = Path(result['paths']['交付说明.txt'])
    assert explanation.read_text(encoding='utf-8').strip() == manifest['delivery_explanation_zh']
    assert Path(result['paths']['交付文案.txt']).read_text(encoding='utf-8').strip() == manifest['delivery_text_zh']
    explanation.write_text('篡改', encoding='utf-8', newline='\n')
    with pytest.raises(ValueError, match='损坏'):
        register_delivery(data, sessions, 'job_test', 2, manifest)


@pytest.mark.parametrize('change', ['hash', 'unlink'])
def test_previous_delivery_sources_revalidated_before_count(delivery, change):
    data, sessions, manifest = delivery
    register_delivery(data, sessions, 'job_test', 1, manifest)
    # Second ordinal uses a different imported source, so only prior-record validation
    # can catch damage/detachment of ordinal one's source.
    fresh = data / 'media' / 'fresh.mp4'
    fresh.write_bytes((data / 'media' / 'source.mp4').read_bytes() + b'new-source-marker')
    with sessions.begin() as session:
        session.add(Asset(id='asset_fresh', sha256=digest(fresh), filename='fresh.mp4',
                          media_path='fresh.mp4', thumbnail_path='unused.jpg', metadata_json={}))
        session.flush()
        session.add(JobAsset(job_id='job_test', asset_id='asset_fresh'))
        if change == 'unlink':
            session.delete(session.get(JobAsset, ('job_test', 'asset_test')))
    if change == 'hash':
        (data / 'media' / 'source.mp4').write_bytes(b'corrupted original')
    manifest['sources'] = [{'asset_id': 'asset_fresh', 'sha256': digest(fresh)}]
    with pytest.raises(ValueError):
        register_delivery(data, sessions, 'job_test', 2, manifest)
    with sessions() as session:
        assert session.get(Job, 'job_test').payload['batch']['rendered_count'] == 1


@pytest.mark.parametrize('payload_patch', [
    {'pipeline': {'rendered_count': 1, 'items': []}},
    {'pipeline': {'items': [{'ordinal': 1, 'status': 'LOCAL_DELIVERED'}]}},
    {'sources': ['https://example.test/source.mp4']},
    {'collection': {}},
    {'pipeline_inputs': {'collection': {}}},
    {'desktop_delivery': []},
    {'desktop_delivery': {'1': None}},
    {'desktop_delivery': {'../1': {'fingerprint': '0' * 64}}},
    {'desktop_delivery': {'1': {'fingerprint': '0' * 64, 'ordinal': 1}}},
])
def test_reject_legacy_mixing_obsolete_inputs_and_malformed_records(delivery, payload_patch):
    data, sessions, manifest = delivery
    with sessions.begin() as session:
        job = session.get(Job, 'job_test')
        job.payload = {**job.payload, **deepcopy(payload_patch)}
    with pytest.raises(ValueError):
        register_delivery(data, sessions, 'job_test', 1, manifest)


def test_reject_existing_batch_legacy_delivery(delivery):
    data, sessions, manifest = delivery
    with sessions.begin() as session:
        job = session.get(Job, 'job_test')
        payload = deepcopy(job.payload)
        payload['batch']['items'][0].update(production_status='LOCAL_DELIVERED', package_path='/legacy/package')
        job.payload = payload
    with pytest.raises(ValueError, match='不能混入'):
        register_delivery(data, sessions, 'job_test', 2, manifest)


def test_corrupt_stored_json_is_value_error(delivery):
    from pathlib import Path
    data, sessions, manifest = delivery
    result = register_delivery(data, sessions, 'job_test', 1, manifest)
    (Path(result['paths']['video.mp4']).parent / 'manifest.json').write_text('{invalid', encoding='utf-8', newline='\n')
    with pytest.raises(ValueError):
        register_delivery(data, sessions, 'job_test', 1, manifest)


def test_real_ten_bit_h264_rejected(delivery, tmp_path):
    data, sessions, manifest = delivery
    video = tmp_path / 'ten-bit.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
                    '-i', 'color=c=blue:s=180x320:r=25:d=1', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p10le', '-y', str(video)], check=True)
    # The stream is genuine H264 High 10 with yuv420p10le, not an altered filename.
    inspected = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner',
                                '-i', str(video), '-f', 'null', '-'],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert 'yuv420p10le' in inspected.stderr
    manifest['video_path'] = str(video)
    with pytest.raises(ValueError, match='H264/yuv420p'):
        register_delivery(data, sessions, 'job_test', 1, manifest)


def test_chinese_export_path_uses_explicit_safe_utf8_decode(delivery, tmp_path, monkeypatch):
    from workflow import desktop_delivery
    data, sessions, manifest = delivery
    video = tmp_path / '客户商品成片.mp4'
    from pathlib import Path
    video.write_bytes(Path(manifest['video_path']).read_bytes())
    manifest['video_path'] = str(video)
    original_run = subprocess.run
    calls = []

    def checked_run(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs['encoding'] == 'utf-8'
        assert kwargs['errors'] == 'replace'
        return original_run(*args, **kwargs)

    monkeypatch.setattr(desktop_delivery.subprocess, 'run', checked_run)
    assert register_delivery(data, sessions, 'job_test', 1, manifest)['media_qa']['pixel_format'] == 'yuv420p'
    assert calls


def test_remotion_project_requires_bound_render_record():
    from workflow.desktop_delivery import validate_manifest
    manifest = {'project_id': 'remotion:fixture', 'delivery_explanation_zh': '测试说明',
                'delivery_text_zh': '测试文案'}
    with pytest.raises(ValueError, match='render_record_path'):
        validate_manifest(manifest)
