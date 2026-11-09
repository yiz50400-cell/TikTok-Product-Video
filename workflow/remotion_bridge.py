"""ChatCut clean exports -> local Remotion packaging -> reviewed delivery.

Rendering is never customer approval or a delivered-count update.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from workflow.analysis.core import probe
from workflow.desktop_delivery import digest, local_file, validate_sources, validate_subtitles, validate_video
from workflow.orchestration.pipeline import validate_local_job
from workflow.platforms.files import atomic_json
from workflow.platforms.locks import acquire
from workflow.store import Job

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / 'remotion'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check_job(request, data, sessions):
    with sessions() as session:
        job = session.get(Job, request['job_id'])
        if not job or job.status == 'CANCELLED':
            raise ValueError('任务不存在或已取消')
        validate_local_job(job.payload)
        if type(request['ordinal']) is not int or not 1 <= request['ordinal'] <= job.payload.get('count', 1):
            raise ValueError('视频序号超出任务数量')
        sources = request['sources']
        if (not isinstance(sources, list) or not sources
                or any(not isinstance(s, dict) or set(s) != {'asset_id', 'sha256'}
                       or not isinstance(s['asset_id'], str)
                       or not isinstance(s['sha256'], str)
                       or not re.fullmatch('[a-f0-9]{64}', s['sha256']) for s in sources)
                or len({s['asset_id'] for s in sources}) != len(sources)):
            raise ValueError('sources须为不重复的任务素材ID与SHA256')
        validate_sources(Path(data).resolve(), session, request['job_id'], sources)


def text_field(value, name, maximum, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum:
        raise ValueError(f'{name}须为文本且不超过{maximum}字符')
    return value.strip()


def captions_from_srt(path, duration):
    validate_subtitles(path, duration)
    rows = []
    for block in re.split(r'\r?\n\s*\r?\n', path.read_text(encoding='utf-8-sig').strip()):
        lines = block.splitlines()
        values = [int(n) for n in re.findall(r'\d+', lines[1])]
        start, end = [(v[0] * 3600 + v[1] * 60 + v[2]) * 1000 + v[3]
                      for v in (values[:4], values[4:])]
        text = text_field('\n'.join(lines[2:]), '单条字幕', 110)
        rows.append({'text': text, 'startMs': start, 'endMs': end,
                     'timestampMs': None, 'confidence': None})
    return rows


def prepare(request, output, data, sessions):
    """Validate first, then atomically publish a local, immutable rendering input."""
    allowed = {'schema_version', 'job_id', 'ordinal', 'chatcut_project_id', 'video_path',
               'srt_path', 'audio_mode', 'base_subtitles_burned_in', 'sources', 'title',
               'cta', 'cards', 'accent_color', 'delivery_explanation_zh', 'delivery_text_zh'}
    required = allowed - {'srt_path', 'title', 'cta', 'cards', 'accent_color'}
    if not isinstance(request, dict) or set(request) - allowed or required - set(request):
        raise ValueError('包装请求字段缺失或存在未知字段')
    if request['schema_version'] != 1 or request['base_subtitles_burned_in'] is not False:
        raise ValueError('需要schema_version=1和未烧字幕的ChatCut底片')
    if not isinstance(request['job_id'], str) or not re.fullmatch(r'job_[A-Za-z0-9_-]+', request['job_id']):
        raise ValueError('任务ID无效')
    text_field(request['chatcut_project_id'], 'ChatCut项目ID', 200)
    check_job(request, data, sessions)
    mode = request['audio_mode']
    if mode not in ('silent', 'narration'):
        raise ValueError('音频模式须为silent或narration')
    for name in ('delivery_explanation_zh', 'delivery_text_zh'):
        text = text_field(request[name], name, 5000)
        if not re.search(r'[\u4e00-\u9fff]', text):
            raise ValueError('交付说明和文案须包含中文')
    video = local_file(request['video_path'], '.mp4')
    metadata = probe(video)
    duration = metadata['duration_seconds']
    if duration > 180:
        raise ValueError('当前商品短视频包装支持最长180秒')
    validate_video(video, duration, mode)
    frames = round(duration * 30)
    if frames < 1:
        raise ValueError('底片时长不足一帧')
    duration = frames / 30
    srt = local_file(request['srt_path'], '.srt') if request.get('srt_path') else None
    if mode == 'narration' and srt is None:
        raise ValueError('口播底片必须提供同步SRT')
    captions = captions_from_srt(srt, duration) if srt else []
    cards = request.get('cards', [])
    if not isinstance(cards, list) or len(cards) > 20:
        raise ValueError('最多20张卖点卡')
    previous = 0
    for card in cards:
        if not isinstance(card, dict) or set(card) != {'text', 'start', 'end'}:
            raise ValueError('卖点卡须包含text/start/end')
        text_field(card['text'], '卖点卡', 80)
        start, end = card['start'], card['end']
        if (any(type(n) not in (int, float) or not math.isfinite(n) for n in (start, end))
                or not previous <= start < end <= duration or round(start * 30) >= round(end * 30)):
            raise ValueError('卖点卡时间重叠或超出视频')
        previous = end
    accent = request.get('accent_color', '#FFD54A')
    if not isinstance(accent, str) or not re.fullmatch('#[a-fA-F0-9]{6}', accent):
        raise ValueError('accent_color须为六位十六进制颜色')
    props = {'video': 'base.mp4', 'durationInFrames': frames, 'fps': 30,
             'audioMode': mode, 'captions': captions, 'cards': cards, 'accentColor': accent,
             'title': text_field(request.get('title', ''), '标题', 80, empty=True),
             'cta': text_field(request.get('cta', ''), 'CTA', 60, empty=True)}
    inputs = {'media/base.mp4': {'path': str(video), 'sha256': digest(video)}}
    if srt:
        inputs['subtitles.srt'] = {'path': str(srt), 'sha256': digest(srt)}
    record = {'schema_version': 1, 'engine': 'remotion', 'request': deepcopy(request),
              'chatcut_project_id': request['chatcut_project_id'], 'inputs': inputs,
              'props_sha256': fingerprint(props)}
    record['fingerprint'] = fingerprint(record)
    output = Path(output).resolve()
    if output.exists():
        if not (output / 'prepared.json').is_file() or load(output / 'prepared.json') != record:
            raise ValueError('输入已变化，请使用新的包装目录')
        verify_prepared(output, data, sessions)
        return record
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.remotion-prepare-', dir=output.parent))
    try:
        for name, item in inputs.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item['path'], target)
            if digest(target) != item['sha256'] or digest(Path(item['path'])) != item['sha256']:
                raise ValueError('素材在复制过程中变化')
        atomic_json(temporary / 'props.json', props)
        atomic_json(temporary / 'prepared.json', record)
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return record


def verify_prepared(output, data, sessions):
    record = load(output / 'prepared.json')
    if record.get('fingerprint') != fingerprint({k: v for k, v in record.items() if k != 'fingerprint'}):
        raise ValueError('包装输入记录已损坏')
    check_job(record['request'], data, sessions)
    if fingerprint(load(output / 'props.json')) != record['props_sha256']:
        raise ValueError('包装参数已变化，请使用新目录')
    names = set(record['inputs'])
    if names not in ({'media/base.mp4'}, {'media/base.mp4', 'subtitles.srt'}):
        raise ValueError('包装输入文件列表无效')
    for name, item in record['inputs'].items():
        original = local_file(item['path'])
        if digest(output / name) != item['sha256'] or digest(original) != item['sha256']:
            raise ValueError('底片或字幕已变化/损坏，请重新准备')
    return record


def renderer_identity():
    paths = [RENDERER / 'package-lock.json', RENDERER / 'render.mjs',
             *sorted((RENDERER / 'src').glob('*'))]
    if any(not p.is_file() for p in paths) or len(paths) < 3:
        raise ValueError('Remotion源码不完整')
    return {p.relative_to(RENDERER).as_posix(): digest(p) for p in paths}


def validate_render_record(path, video, sources, job_id, ordinal):
    record = load(path)
    if not isinstance(record, dict) or record.get('record_fingerprint') != fingerprint(
            {k: v for k, v in record.items() if k != 'record_fingerprint'}):
        raise ValueError('Remotion渲染记录指纹无效')
    names = {'final.mp4', 'qa.json'}
    if record.get('has_subtitles') is True:
        names.add('subtitles.srt')
    if (type(record.get('has_subtitles')) is not bool or set(record.get('files', {})) != names
            or any(not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha)
                   for sha in record['files'].values())
            or not re.fullmatch('[a-f0-9]{64}', record.get('input_fingerprint', ''))
            or record.get('project_id') != 'remotion:' + record['input_fingerprint'][:20]
            or record['files']['final.mp4'] != record.get('video_sha256')):
        raise ValueError('Remotion渲染记录文件清单无效')
    if (record.get('engine') != 'remotion' or record.get('schema_version') != 1
            or record.get('job_id') != job_id or record.get('ordinal') != ordinal
            or record.get('sources') != sources or record.get('video_sha256') != digest(video)
            or not record.get('chatcut_project_id') or not record.get('renderer_files')
            or not re.fullmatch('[a-f0-9]{64}', record.get('base_video_sha256', ''))):
        raise ValueError('Remotion渲染记录与成片或任务素材不匹配')
    return record


def render(output, data, sessions):
    """Render/QA atomically; reuse intact results. Does not register delivery."""
    output = Path(output).resolve()
    if not output.is_dir():
        raise ValueError('请先prepare包装输入')
    with (output / '.render.lock').open('a+b') as lock:
        acquire(lock, blocking=False)
        prepared = verify_prepared(output, data, sessions)
        identity = renderer_identity()
        target = output / 'rendered'
        request = prepared['request']
        if target.exists():
            record = validate_render_record(target / 'render-record.json', target / 'final.mp4',
                                             request['sources'], request['job_id'], request['ordinal'])
            if record['input_fingerprint'] != prepared['fingerprint'] or record['renderer_files'] != identity:
                raise ValueError('渲染输入或模板版本变化，请使用新包装目录')
            for name, sha in record['files'].items():
                if name not in ('final.mp4', 'subtitles.srt', 'qa.json') or digest(target / name) != sha:
                    raise ValueError('已渲染文件损坏')
            return record
        node = shutil.which('node')
        if not node or not (RENDERER / 'node_modules/@remotion/renderer').is_dir():
            raise ValueError('请安装Node.js 22+并运行 npm --prefix remotion ci')
        temporary = Path(tempfile.mkdtemp(prefix='.render-', dir=output))
        try:
            command = [node, str(RENDERER / 'render.mjs'), str(output), str(temporary / 'final.mp4')]
            with (output / 'render.log').open('w', encoding='utf-8') as log:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=3600)
            props = load(output / 'props.json')
            expected = props['durationInFrames'] / props['fps']
            qa = validate_video(temporary / 'final.mp4', expected, request['audio_mode'])
            if qa['width'] != 1080 or qa['height'] != 1920:
                raise ValueError('Remotion输出须为1080x1920')
            qa['scope'] = 'technical_only_pending_visual_and_listening_review'
            atomic_json(temporary / 'qa.json', qa)
            files = ['final.mp4', 'qa.json']
            if (output / 'subtitles.srt').exists():
                shutil.copyfile(output / 'subtitles.srt', temporary / 'subtitles.srt')
                files.append('subtitles.srt')
            project_id = 'remotion:' + prepared['fingerprint'][:20]
            record = {'schema_version': 1, 'engine': 'remotion', 'project_id': project_id,
                      'chatcut_project_id': request['chatcut_project_id'],
                      'job_id': request['job_id'], 'ordinal': request['ordinal'],
                      'sources': request['sources'], 'input_fingerprint': prepared['fingerprint'],
                      'base_video_sha256': prepared['inputs']['media/base.mp4']['sha256'],
                      'renderer_files': identity, 'expected_duration': expected,
                      'audio_mode': request['audio_mode'],
                      'video_sha256': digest(temporary / 'final.mp4'),
                      'files': {name: digest(temporary / name) for name in files},
                      'has_subtitles': 'subtitles.srt' in files,
                      'status': 'RENDERED_PENDING_REVIEW'}
            record['record_fingerprint'] = fingerprint(record)
            atomic_json(temporary / 'render-record.json', record)
            manifest = {k: request[k] for k in ('sources', 'audio_mode',
                        'delivery_explanation_zh', 'delivery_text_zh')}
            manifest.update({'project_id': project_id, 'video_path': str(target / 'final.mp4'),
                             'expected_duration': expected,
                             'render_record_path': str(target / 'render-record.json'),
                             'review': {'reviewer': '', 'reviewed_at': '',
                                        'visual': {'passed': False, 'evidence': ''}}})
            if 'subtitles.srt' in files:
                manifest['srt_path'] = str(target / 'subtitles.srt')
            if request['audio_mode'] == 'narration':
                manifest['review']['listening'] = {'passed': False, 'evidence': ''}
            atomic_json(temporary / 'delivery-manifest.template.json', manifest)
            verify_prepared(output, data, sessions)
            if renderer_identity() != identity:
                raise ValueError('渲染过程中模板发生变化')
            temporary.rename(target)
            return record
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
