import socket

import pytest
import requests

from mydns_notifier import get_global_ip, get_ip_from_dns


class DummyResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.RequestException(f'status {self.status_code}')


def test_get_global_ip_success(monkeypatch):
    monkeypatch.setattr(
        'mydns_notifier.requests.get',
        lambda *a, **k: DummyResponse('1.2.3.4\n'),
    )
    assert get_global_ip() == '1.2.3.4'


def test_get_global_ip_failure(monkeypatch):
    def _raise(*a, **k):
        raise requests.RequestException('network error')

    monkeypatch.setattr('mydns_notifier.requests.get', _raise)
    with pytest.raises(requests.RequestException):
        get_global_ip()


def test_get_ip_from_dns_success(monkeypatch):
    # socket.getaddrinfo returns list of 5-tuples; index 4 is sockaddr tuple
    def fake_getaddrinfo(host, _port, family=socket.AF_UNSPEC):
        assert family == socket.AF_UNSPEC
        return [(None, None, None, None, ('203.0.113.5', 0))]

    monkeypatch.setattr('mydns_notifier.socket.getaddrinfo', fake_getaddrinfo)
    assert get_ip_from_dns('example.test') == '203.0.113.5'


def test_get_ip_from_dns_failure(monkeypatch):
    def _raise(host, _port, family=socket.AF_UNSPEC):
        raise socket.gaierror('not found')

    monkeypatch.setattr('mydns_notifier.socket.getaddrinfo', _raise)
    with pytest.raises(socket.gaierror):
        get_ip_from_dns('nonexistent')


def test_get_ip_from_dns_success_ipv6(monkeypatch):
    def fake_getaddrinfo(host, _port, family):
        assert family == socket.AF_INET6
        return [(None, None, None, None, ('2001:db8::5', 0, 0, 0))]

    monkeypatch.setattr('mydns_notifier.socket.getaddrinfo', fake_getaddrinfo)
    assert get_ip_from_dns('example.test', socket.AF_INET6) == '2001:db8::5'


def test_get_global_ip_success_ipv6(monkeypatch):
    monkeypatch.setattr(
        'mydns_notifier.requests.get',
        lambda *a, **k: DummyResponse('2001:db8::1\n'),
    )
    assert get_global_ip('ipv6') == '2001:db8::1'
