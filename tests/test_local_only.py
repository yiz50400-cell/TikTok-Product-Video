"""Customer intake never creates acquisition stages, including for legacy jobs."""
import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from workflow.api import create_app
from workflow.cli import parser
from workflow.mcp_server import workflow_create_job
from workflow.orchestration.pipeline import Pipeline, set_inputs
from workflow.store import Job, database


@pytest.fixture
def local_client(tmp_path):
    with TestClient(create_app(tmp_path / 'data')) as client:
        client.headers.update({'Authorization': 'Bearer ' + (client.app.state.data_dir / 'access.token').read_text().strip(),
                               'X-Workflow-Client': 'studio'})
        yield client


def test_url_input_rejected_and_empty_legacy_source_list_allowed(local_client):
    body = {'title': '本地商品', 'product': '商品'}
    for sources in [['https://example.test/video'], ['file:///tmp/video.mp4']]:
        assert local_client.post('/api/jobs', json={**body, 'sources': sources}).status_code == 422
    job = local_client.post('/api/jobs', json={**body, 'sources': []}).json()
    assert '本地' in job['next_action']
    caps = local_client.get('/api/capabilities').json()
    assert 'collection' not in caps['standalone_modules']
    assert caps['version'] == (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
    assert caps['mode'] == 'local_material_editing'
    assert caps['source_policy'] == 'local_files_only'
    assert caps['default_editor'] == 'ChatCut Desktop'
    assert {'video_discovery', 'video_download'} <= set(caps['out_of_scope'])
    assert caps['standalone_modules']['desktop_delivery']['integrated'] is True
    assert 'automatic_platform_search' not in caps['pending']


@pytest.mark.parametrize('legacy', [{'collection': {}}, {'collection': None},
                                  {'sources': ['https://example.test/video']},
                                  {'pipeline_inputs': {'items': [], 'collection': {}}}])
def test_saved_collection_and_urls_fail_before_filesystem_changes(local_client, legacy):
    data = local_client.app.state.data_dir
    engine, sessions = database(data)
    try:
        job_id = local_client.post('/api/jobs', json={'title': '商品', 'product': '商品'}).json()['id']
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            job.payload = {**job.payload, **legacy}
        with pytest.raises(ValueError, match='本地'):
            Pipeline(data, sessions, data).run(job_id)
        assert not (data / 'pipelines' / job_id).exists()
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            before = dict(job.payload)
            with pytest.raises(ValueError):
                set_inputs(session, job, {'items': []})
            assert job.payload == before
    finally:
        engine.dispose()


def test_direct_collection_input_rejected_without_querying():
    class Task:
        payload = {}
    with pytest.raises(ValueError):
        set_inputs(None, Task(), {'collection': {}})


def test_cli_and_mcp_do_not_offer_url_sources():
    assert 'sources' not in inspect.signature(workflow_create_job).parameters
    with pytest.raises(SystemExit):
        parser().parse_args(['create', '--title', '商品', '--product', '商品', '--source', 'https://example.test'])


@pytest.mark.parametrize('status,count', [('PARTIALLY_DELIVERED', 2), ('LOCAL_DELIVERED', 1)])
def test_desktop_progress_is_displayed_and_debug_pipeline_cannot_clear_it(local_client, status, count):
    data = local_client.app.state.data_dir
    job_id = local_client.post('/api/jobs', json={'title': '商品', 'product': '商品', 'count': count}).json()['id']
    engine, sessions = database(data)
    try:
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            job.payload = {**job.payload, 'desktop_delivery': {'1': {'status': 'LOCAL_DELIVERED'}}}
            job.status = status
        shown = local_client.get('/api/jobs/' + job_id).json()
        assert '交付' in shown['next_action']
        with pytest.raises(ValueError, match='桌面交付'):
            Pipeline(data, sessions, data).run(job_id)
        assert not (data / 'pipelines' / job_id).exists()
    finally:
        engine.dispose()


def test_delivered_language_concept_and_reference_mutations_are_atomic(local_client):
    from copy import deepcopy
    from workflow.store import invalidate_pipeline
    job_id = local_client.post('/api/jobs', json={'title': '商品', 'product': '商品', 'market': 'PH',
                                                 'voiceover_locale': 'fil-PH'}).json()['id']
    route = '/api/jobs/' + job_id
    concept = {'ordinal': 1, 'angle': '演示', 'hook': '看看', 'buyer_concern': '使用方式',
               'proof_requirement': '动作', 'cta_direction': '详情', 'source_asset_ids': []}
    reference = {'schema_version': 1, 'product': {'name': '商品'}, 'market': 'PH',
                 'references': [{'candidate_id': 'customer-description',
                                 'relationship': 'same_product_candidate',
                                 'use_scope': 'material_candidate_and_structure',
                                 'evidence_scope': 'visual_structure_only', 'transcription_status': 'provided',
                                 **{key: key for key in ['hook', 'buyer_concern', 'proof', 'objection_or_turn', 'cta']}}]}
    assert local_client.post(route + '/batch/concepts', json={'concepts': [concept]}).status_code == 200
    assert local_client.post(route + '/reference-package', json={'package': reference}).status_code == 200
    engine, sessions = database(local_client.app.state.data_dir)
    try:
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            payload = deepcopy(job.payload)
            payload['desktop_delivery'] = {'1': {'status': 'LOCAL_DELIVERED'}}
            payload['batch']['rendered_count'] = 1
            payload['batch']['status'] = 'LOCAL_DELIVERED'
            payload['batch']['items'][0]['production_status'] = 'LOCAL_DELIVERED'
            job.payload = payload
            job.status = 'LOCAL_DELIVERED'
        before = local_client.get(route).json()
        changed_reference = {**reference, 'product': {'name': '另一描述'}}
        for suffix, body in [('/language', {'voiceover_locale': 'en-PH'}),
                             ('/batch/concepts', {'concepts': [{**concept, 'hook': '新的开头'}]}),
                             ('/reference-package', {'package': changed_reference})]:
            response = local_client.post(route + suffix, json=body)
            assert response.status_code == 409, response.text
            assert local_client.get(route).json() == before
        for suffix, body in [('/language', {'voiceover_locale': 'fil-PH'}),
                             ('/batch/concepts', {'concepts': [concept]}),
                             ('/reference-package', {'package': reference})]:
            assert local_client.post(route + suffix, json=body).status_code == 200
            assert local_client.get(route).json() == before
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            saved = deepcopy(job.payload)
            with pytest.raises(ValueError, match='交付'):
                invalidate_pipeline(job, clear_drafts=True)
            assert job.payload == saved
    finally:
        engine.dispose()


def test_delivered_job_rejects_import_and_analysis_without_resetting_progress(local_client):
    job_id = local_client.post('/api/jobs', json={'title': '商品', 'product': '商品'}).json()['id']
    route = '/api/jobs/' + job_id
    engine, sessions = database(local_client.app.state.data_dir)
    try:
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            job.payload = {**job.payload, 'desktop_delivery': {'1': {'status': 'LOCAL_DELIVERED'}},
                           'batch': {**job.payload['batch'], 'rendered_count': 1}}
            job.status = 'LOCAL_DELIVERED'
        before = local_client.get(route).json()
        media = local_client.app.state.data_dir / 'media'
        original_files = sorted(media.iterdir())
        uploaded = local_client.post(route + '/assets', files={'file': ('customer.mp4', b'customer original', 'video/mp4')})
        assert uploaded.status_code == 409
        analysis = {'index_path': '/tmp/test-index.json', 'index_sha256': 'a'*64,
                    'index': {}, 'manifest': {}, 'observations': {}, 'contact_sheet_hashes': {}}
        assert local_client.post(route + '/analyses', json=analysis).status_code == 409
        assert sorted(media.iterdir()) == original_files
        assert local_client.get(route).json() == before
    finally:
        engine.dispose()


def test_partial_desktop_delivery_can_import_missing_local_footage(local_client, tmp_path):
    import hashlib
    import subprocess
    import imageio_ffmpeg
    from copy import deepcopy
    job_id = local_client.post('/api/jobs', json={'title': '商品', 'product': '商品', 'count': 2}).json()['id']
    route = '/api/jobs/' + job_id
    source = tmp_path / 'additional-customer-footage.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i',
                    'testsrc2=size=180x320:rate=30', '-t', '1', '-c:v', 'libx264', str(source)], check=True)
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    engine, sessions = database(local_client.app.state.data_dir)
    delivery = {'1': {'status': 'LOCAL_DELIVERED', 'fingerprint': 'first-video-evidence'}}
    try:
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            payload = deepcopy(job.payload)
            payload['desktop_delivery'] = delivery
            payload['batch']['rendered_count'] = 1
            payload['batch']['status'] = 'PARTIALLY_DELIVERED'
            payload['batch']['items'][0]['production_status'] = 'LOCAL_DELIVERED'
            job.payload = payload
            job.status = 'PARTIALLY_DELIVERED'
        before = local_client.get(route).json()
        response = local_client.post(route + '/assets', files={'file': (source.name, source.read_bytes(), 'video/mp4')})
        assert response.status_code == 201, response.text
        after = local_client.get(route).json()
        assert after['status'] == 'PARTIALLY_DELIVERED'
        assert after['batch'] == before['batch']
        assert after['desktop_delivery'] == delivery
        assert len(after['assets']) == 1
        assert after['assets'][0]['sha256'] == original_sha
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_sha
        duplicate = local_client.post(route + '/assets', files={'file': (source.name, source.read_bytes(), 'video/mp4')})
        assert duplicate.status_code == 200
        assert local_client.get(route).json()['batch']['rendered_count'] == 1
    finally:
        engine.dispose()
