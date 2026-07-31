import json
from pathlib import Path

import pytest

from mydns_notifier import MydnsDomain


def test_import_and_export_json(tmp_path, monkeypatch):
    sample = {
        'acc1': {
            'url': 'example.test',
            'id': 'user1',
            'pw': 'pass1',
            'last': {
                'ip': '198.51.100.2',
                'time': '2023-01-01T00:00:00+09:00'
            }
        }
    }
    f = tmp_path / 'conf.json'
    f.write_text(json.dumps(sample))

    # patch network functions used during import
    monkeypatch.setattr('mydns_notifier.get_global_ip', lambda: '198.51.100.2')
    monkeypatch.setattr('mydns_notifier.get_ip_from_dns', lambda url: '198.51.100.3')

    domains = MydnsDomain.import_json(f)
    assert len(domains) == 1
    d = domains[0]
    assert d.name == 'acc1'
    assert d.url == 'example.test'
    assert d.id == 'user1'
    assert d.pw == 'pass1'
    assert d.ip == '198.51.100.3'
    assert d.last.ip == '198.51.100.2'

    out = tmp_path / 'out.json'
    MydnsDomain.export_json(domains, out)
    loaded = json.loads(out.read_text())
    assert 'acc1' in loaded
    assert loaded['acc1']['url'] == 'example.test'
