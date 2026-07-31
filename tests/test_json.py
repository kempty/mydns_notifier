import json
import socket

from mydns_notifier import IPV4, MydnsDomain


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
    monkeypatch.setattr('mydns_notifier.get_global_ip', lambda version=IPV4: '198.51.100.2')
    monkeypatch.setattr('mydns_notifier.get_ip_from_dns', lambda url, family=socket.AF_UNSPEC: '198.51.100.3')

    domains = MydnsDomain.import_json(f)
    assert len(domains) == 1
    d = domains[0]
    assert d.name == 'acc1'
    assert d.url == 'example.test'
    assert d.id == 'user1'
    assert d.pw == 'pass1'
    assert d.ipv4 == '198.51.100.3'
    assert d.last.ipv4 == '198.51.100.2'

    out = tmp_path / 'out.json'
    MydnsDomain.export_json(domains, out)
    loaded = json.loads(out.read_text())
    assert 'acc1' in loaded
    assert loaded['acc1']['url'] == 'example.test'


def test_import_export_json_dual_stack(tmp_path, monkeypatch):
    sample = {
        'acc1': {
            'url': 'example.test',
            'id': 'user1',
            'pw': 'pass1',
            'last': {
                'ipv4': '198.51.100.2',
                'ipv4_time': '2023-01-01T00:00:00+09:00',
                'ipv6': '2001:db8::2',
                'ipv6_time': '2023-01-01T00:00:00+09:00',
            }
        }
    }
    f = tmp_path / 'conf.json'
    f.write_text(json.dumps(sample))

    monkeypatch.setattr('mydns_notifier.get_global_ip', lambda version='ipv4': '198.51.100.2')
    monkeypatch.setattr('mydns_notifier.get_ip_from_dns', lambda url, family=None: '198.51.100.3')

    domains = MydnsDomain.import_json(f)
    assert len(domains) == 1
    d = domains[0]
    assert d.last.ipv4 == '198.51.100.2'
    assert d.last.ipv6 == '2001:db8::2'
    assert d.last.ipv4_time.isoformat() == '2023-01-01T00:00:00+09:00'
    assert d.last.ipv6_time.isoformat() == '2023-01-01T00:00:00+09:00'

    out = tmp_path / 'out.json'
    MydnsDomain.export_json(domains, out)
    loaded = json.loads(out.read_text())
    assert loaded['acc1']['last']['ipv4'] == '198.51.100.2'
    assert loaded['acc1']['last']['ipv6'] == '2001:db8::2'
