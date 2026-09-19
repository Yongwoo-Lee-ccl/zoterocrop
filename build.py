#!/usr/bin/env python3
"""Build deterministic XPI and the matching Zotero update manifest."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
REPOSITORY = 'https://github.com/Yongwoo-Lee-ccl/zoterocrop'
UPDATE_URL = 'https://raw.githubusercontent.com/Yongwoo-Lee-ccl/zoterocrop/main/updates.json'


def build():
    plugin = ROOT / 'plugin'
    manifest = json.loads((plugin / 'manifest.json').read_text())
    settings = manifest.get('applications', {}).get('zotero', {})
    for key in ('id', 'update_url', 'strict_min_version', 'strict_max_version'):
        if not settings.get(key):
            raise ValueError(f'Missing required Zotero metadata: {key}')
    if settings['update_url'] != UPDATE_URL:
        raise ValueError('Update URL must point to this repository')
    version = manifest['version']
    name = f'crop-margins-{version}.xpi'
    (ROOT / 'dist').mkdir(exist_ok=True)
    target = ROOT / 'dist' / name
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(plugin.rglob('*')):
            if source.is_file() and '__pycache__' not in source.parts:
                entry = zipfile.ZipInfo(source.relative_to(plugin).as_posix(), (2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, source.read_bytes())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    updates = {'addons': {settings['id']: {'updates': [{
        'version': version,
        'update_link': f'{REPOSITORY}/releases/download/v{version}/{name}',
        'update_hash': 'sha256:' + digest,
        'applications': {'zotero': {key: settings[key] for key in ('strict_min_version', 'strict_max_version')}}
    }]}}}
    (ROOT / 'updates.json').write_text(json.dumps(updates, indent=2) + '\n')
    print(target)
    print('sha256:' + digest)


if __name__ == '__main__':
    build()
