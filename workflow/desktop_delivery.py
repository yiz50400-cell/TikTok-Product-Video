"""Register actual ChatCut or Remotion exports; technical checks never imply customer acceptance."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import imageio_ffmpeg

from workflow.batch import new_batch
from workflow.orchestration.pipeline import pipeline_lock, validate_local_job
from workflow.store import Activity, Asset, Job, JobAsset


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def local_file(value, suffix=None):
    if not isinstance(value, str) or '://' in value or value.startswith(('//', '\\\\')):
        raise ValueError('必须提供本机绝对文件路径')
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or (suffix and path.suffix.lower() != suffix):
        raise ValueError('本地文件缺失、路径非绝对或格式错误')
    return path.resolve()


def validate_subtitles(path, duration):
    text = path.read_text(encoding='utf-8-sig').strip()
    blocks = re.split(r'\r?\n\s*\r?\n', text)
    previous = 0.0
    for number, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(number) or not any(s.strip() for s in lines[2:]):
            raise ValueError('SRT字幕为空或结构无效')
        match = re.fullmatch(r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3}) --> (\d{2}):([0-5]\d):([0-5]\d),(\d{3})', lines[1])
        if not match:
            raise ValueError('SRT时间格式无效')
        values = list(map(int, match.groups()))
        start, end = [v[0] * 3600 + v[1] * 60 + v[2] + v[3] / 1000 for v in (values[:4], values[4:])]
        if start < previous or end <= start or end > duration + .05:
            raise ValueError('SRT时间重叠、倒序或超出视频')
        previous = end
    return {'cue_count': len(blocks), 'last_end': previous}


def validate_video(path, expected, mode):
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-nostdin',
               '-protocol_whitelist', 'file,pipe', '-xerror', '-i', str(path),
               '-map', '0:v:0', '-map', '0:a?', '-progress', 'pipe:1', '-f', 'null', '-']
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=600)
    video = next((line for line in result.stderr.splitlines() if 'Video:' in line), '')
    pixel_format = re.search(r',\s*([a-z][a-z0-9]*)(?:\([^)]*\))?,\s*\d{2,5}x\d{2,5}\b', video)
    size = re.search(r'\b(\d{2,5})x(\d{2,5})\b', video)
    declared = re.search(r'Duration: (\d+):(\d+):([\d.]+)', result.stderr)
    times = re.findall(r'^out_time_us=(\d+)$', result.stdout, re.M)
    if (result.returncode or not size or not declared or not times
            or 'progress=end' not in result.stdout or not re.search(r'Input #0, .*mp4', result.stderr)):
        raise ValueError('MP4完整解码失败')
    duration = int(declared[1]) * 3600 + int(declared[2]) * 60 + float(declared[3])
    decoded = int(times[-1]) / 1e6
    audio = 'Audio:' in result.stderr.split('Output #', 1)[0]
    width, height = map(int, size.groups())
    rotation = re.search(r'rotation of (-?[\d.]+) degrees', result.stderr)
    if ((rotation and abs(float(rotation[1])) > .01) or 'Video: h264' not in video
            or not pixel_format or pixel_format[1] != 'yuv420p' or height <= width
            or abs(width / height - 9 / 16) > .02):
        raise ValueError('需要H264/yuv420p的9:16竖屏MP4')
    if abs(duration - expected) > .25 or abs(decoded - duration) > .25:
        raise ValueError('实际视频时长与预期不符')
    if audio != (mode == 'narration'):
        raise ValueError('音轨与声明的silent/narration模式不符')
    return {'duration': duration, 'decoded_duration': decoded, 'width': width,
            'height': height, 'codec': 'h264', 'pixel_format': 'yuv420p',
            'has_audio': audio, 'full_decode_passed': True}


def validate_manifest(manifest):
    allowed = {'project_id', 'sources', 'video_path', 'srt_path', 'expected_duration',
               'audio_mode', 'delivery_explanation_zh', 'delivery_text_zh', 'review', 'render_record_path'}
    if not isinstance(manifest, dict) or set(manifest) - allowed:
        raise ValueError('交付清单存在未知字段')
    for key in ('project_id', 'delivery_explanation_zh', 'delivery_text_zh'):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f'{key}不能为空')
    for key in ('delivery_explanation_zh', 'delivery_text_zh'):
        if not re.search(r'[\u4e00-\u9fff]', manifest[key]):
            raise ValueError(f'{key}须包含中文')
    if manifest['project_id'].startswith('remotion:') and not manifest.get('render_record_path'):
        raise ValueError('Remotion成片必须提供render_record_path')
    expected = manifest.get('expected_duration')
    if type(expected) not in (float, int) or not math.isfinite(expected) or expected <= 0:
        raise ValueError('expected_duration须为正有限秒数')
    mode = manifest.get('audio_mode')
    if mode not in ('silent', 'narration'):
        raise ValueError('audio_mode须为silent或narration')
    sources = manifest.get('sources')
    if (not isinstance(sources, list) or not sources or any(
            not isinstance(s, dict) or set(s) != {'asset_id', 'sha256'}
            or not isinstance(s['asset_id'], str) or not isinstance(s['sha256'], str)
            or not re.fullmatch('[a-f0-9]{64}', s['sha256']) for s in sources)
            or len({s['asset_id'] for s in sources}) != len(sources)):
        raise ValueError('sources须为不重复的素材ID及SHA256')
    review = manifest.get('review')
    if not isinstance(review, dict) or set(review) - {'reviewer', 'reviewed_at', 'visual', 'listening'}:
        raise ValueError('需要真实复核记录，不接受用户审批字段')
    if not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip():
        raise ValueError('复核人不能为空')
    try:
        timestamp = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError()
    except (KeyError, AttributeError, ValueError) as exc:
        raise ValueError('reviewed_at须为含时区的实际复核时间') from exc
    for key in ('visual', 'listening') if mode == 'narration' else ('visual',):
        item = review.get(key)
        if (not isinstance(item, dict) or set(item) != {'passed', 'evidence'}
                or item['passed'] is not True or not isinstance(item['evidence'], str)
                or not item['evidence'].strip()):
            raise ValueError(f'需要实际{key}复核通过及具体证据')


def validate_sources(data, session, job_id, sources):
    checked = []
    for source in sources:
        asset = session.get(Asset, source['asset_id'])
        if not asset or not session.get(JobAsset, (job_id, source['asset_id'])):
            raise ValueError('素材不属于当前任务')
        path = local_file(str(data / 'media' / asset.media_path))
        if not path.is_relative_to((data / 'media').resolve()):
            raise ValueError('任务素材必须存放于本机素材库')
        if asset.sha256 != source['sha256'] or digest(path) != asset.sha256:
            raise ValueError('任务素材SHA256已变化或不匹配')
        checked.append((path, asset.sha256))
    return checked


def register_delivery(data_dir, sessions, job_id, ordinal, manifest):
    """Expose validation failures consistently, including corrupt persisted records."""
    try:
        return _register_delivery(data_dir, sessions, job_id, ordinal, manifest)
    except (KeyError, TypeError, AttributeError, OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('交付记录或本地文件无效，请检查清单及已保存记录') from exc


def _register_delivery(data_dir, sessions, job_id, ordinal, manifest):
    """Copy a verified immutable package and persist exactly one delivered batch item."""
    if not isinstance(job_id, str) or not re.fullmatch(r'job_[A-Za-z0-9_-]+', job_id):
        raise ValueError('任务ID无效')
    validate_manifest(manifest)
    data = Path(data_dir).resolve()
    with pipeline_lock(data, job_id) as root, sessions.begin() as session:
        job = session.get(Job, job_id)
        if not job or job.status == 'CANCELLED':
            raise ValueError('任务不存在或已取消')
        validate_local_job(job.payload)
        existing_desktop = job.payload.get('desktop_delivery', {})
        if not isinstance(existing_desktop, dict):
            raise ValueError('已保存桌面交付记录格式无效')
        pipeline = job.payload.get('pipeline', {})
        batch_items = job.payload.get('batch', {}).get('items', [])
        if (pipeline.get('rendered_count', 0) or pipeline.get('delivered_count', 0)
                or any(row.get('status') == 'LOCAL_DELIVERED' for row in pipeline.get('items', []))
                or any((row.get('production_status') == 'LOCAL_DELIVERED' or row.get('package_path'))
                       and str(row['ordinal']) not in existing_desktop for row in batch_items)):
            raise ValueError('已有调试渲染链路交付，不能混入桌面交付登记')
        if type(ordinal) is not int or not 1 <= ordinal <= job.payload.get('count', 1):
            raise ValueError('视频序号超出任务数量')
        sources = validate_sources(data, session, job_id, manifest['sources'])
        video = local_file(manifest.get('video_path'), '.mp4')
        srt = local_file(manifest['srt_path'], '.srt') if manifest.get('srt_path') else None
        if manifest['audio_mode'] == 'narration' and srt is None:
            raise ValueError('配音视频必须提供SRT')
        files = {'video.mp4': (video, digest(video))}
        if manifest.get('render_record_path'):
            from workflow.remotion_bridge import validate_render_record
            render_path = local_file(manifest['render_record_path'], '.json')
            render_record = validate_render_record(render_path, video, manifest['sources'], job_id, ordinal)
            if (render_record['project_id'] != manifest['project_id']
                    or render_record['audio_mode'] != manifest['audio_mode']
                    or render_record['expected_duration'] != manifest['expected_duration']
                    or render_record['files'].get('subtitles.srt') != (digest(srt) if srt else None)):
                raise ValueError('Remotion渲染记录与交付参数或字幕不匹配')
            files['render-record.json'] = (render_path, digest(render_path))
        if srt:
            files['subtitles.srt'] = (srt, digest(srt))
        qa = validate_video(video, manifest['expected_duration'], manifest['audio_mode'])
        subtitle_qa = validate_subtitles(srt, qa['duration']) if srt else None
        text_files = {
            '交付说明.txt': (manifest['delivery_explanation_zh'].strip() + '\n').encode('utf-8'),
            '交付文案.txt': (manifest['delivery_text_zh'].strip() + '\n').encode('utf-8'),
        }
        signed = {'manifest': deepcopy(manifest), 'files': {name: sha for name, (_, sha) in files.items()}}
        signed['files'].update({name: hashlib.sha256(content).hexdigest()
                                for name, content in text_files.items()})
        fingerprint = hashlib.sha256(json.dumps(signed, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        target = root / 'delivery' / str(ordinal) / fingerprint
        saved = deepcopy(job.payload)
        deliveries = saved.setdefault('desktop_delivery', {})
        for previous_ordinal, previous in deliveries.items():
            if (not isinstance(previous_ordinal, str)
                    or not re.fullmatch(r'[1-9][0-9]*', previous_ordinal)
                    or not 1 <= int(previous_ordinal) <= job.payload.get('count', 1)
                    or not isinstance(previous, dict)
                    or not re.fullmatch(r'[a-f0-9]{64}', previous.get('fingerprint', ''))
                    or previous.get('ordinal') != int(previous_ordinal)):
                raise ValueError('已保存桌面交付记录格式无效')
            validate_manifest(previous['manifest'])
            previous_signed = {key: previous[key] for key in ('manifest', 'files')}
            expected_fingerprint = hashlib.sha256(json.dumps(
                previous_signed, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if expected_fingerprint != previous['fingerprint']:
                raise ValueError('已保存交付指纹无效')
            expected_names = {'video.mp4', '交付说明.txt', '交付文案.txt'}
            if previous['manifest'].get('srt_path'):
                expected_names.add('subtitles.srt')
            if previous['manifest'].get('render_record_path'):
                expected_names.add('render-record.json')
            if set(previous['files']) != expected_names:
                raise ValueError('已保存交付文件列表无效')
            sources.extend(validate_sources(data, session, job_id, previous['manifest']['sources']))
            previous_dir = root / 'delivery' / previous_ordinal / previous['fingerprint']
            saved_manifest = previous_dir / 'manifest.json'
            if not saved_manifest.is_file() or json.loads(saved_manifest.read_text(encoding='utf-8')) != previous:
                raise ValueError('已登记交付清单损坏，拒绝复用')
            if any(not (previous_dir / name).is_file() or digest(previous_dir / name) != sha
                   for name, sha in previous['files'].items()):
                raise ValueError('已登记交付文件损坏，须先恢复原文件')
        old = deliveries.get(str(ordinal))
        if old and old['fingerprint'] != fingerprint:
            raise ValueError('该视频序号已有不同交付，拒绝覆盖')
        record = {**signed, 'fingerprint': fingerprint, 'ordinal': ordinal,
                  'project_id': manifest['project_id'], 'media_qa': qa, 'subtitle_qa': subtitle_qa,
                  'review_scope': 'caller_attested_visual_and_listening; not_user_acceptance',
                  'paths': {name: str(target / name) for name in signed['files']}, 'status': 'LOCAL_DELIVERED'}
        if target.exists():
            stored = target / 'manifest.json'
            if (not stored.is_file() or json.loads(stored.read_text(encoding='utf-8')) != record
                    or any(not (target / name).is_file() or digest(target / name) != sha
                           for name, sha in signed['files'].items())):
                raise ValueError('已存在交付文件损坏，拒绝复用')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix='.delivery-', dir=target.parent))
            try:
                for name, (path, sha) in files.items():
                    shutil.copyfile(path, temporary / name)
                    if digest(temporary / name) != sha or digest(path) != sha:
                        raise ValueError('导出文件在交付过程中变化')
                for name, content in text_files.items():
                    (temporary / name).write_bytes(content)
                (temporary / 'manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.rename(target)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        if any(digest(path) != sha for path, sha in files.values()):
            raise ValueError('导出文件在交付过程中变化')
        if any(digest(path) != sha for path, sha in sources):
            raise ValueError('源素材在交付过程中变化')
        deliveries[str(ordinal)] = record
        batch = saved.setdefault('batch', new_batch(saved.get('count', 1)))
        for item in batch['items']:
            if str(item['ordinal']) in deliveries:
                item['production_status'] = 'LOCAL_DELIVERED'
                item['package_path'] = str(root / 'delivery' / str(item['ordinal']) / deliveries[str(item['ordinal'])]['fingerprint'])
        batch['rendered_count'] = len(deliveries)
        batch['status'] = 'LOCAL_DELIVERED' if len(deliveries) == saved.get('count', 1) else 'PARTIALLY_DELIVERED'
        job.payload = saved
        job.status = batch['status']
        if old is None:
            session.add(Activity(job_id=job_id, kind='desktop_delivery', message=f'本地成片第{ordinal}条已登记；技术QA及复核记录不代表用户验收。'))
        return {**record, 'rendered_count': len(deliveries), 'job_status': job.status}
