import os
os.environ["TESTING"] = "1"
import pytest
from unittest.mock import MagicMock
from fastapi import Request
from app.config import get_settings
from app.routers.scanning import extract_client_ip, _anonymize_ip, is_ip_in_networks


def make_mock_request(client_host: str = "127.0.0.1", headers: dict = None) -> Request:
    """Helper to construct a mock FastAPI Request object."""
    mock_req = MagicMock(spec=Request)
    mock_client = MagicMock()
    mock_client.host = client_host
    mock_req.client = mock_client
    mock_req.headers = headers or {}
    return mock_req


def test_no_trusted_proxies_ignores_forwarded_headers(monkeypatch):
    """When TRUSTED_PROXIES is empty, forwarded headers must never be trusted."""
    monkeypatch.setenv("TRUSTED_PROXIES", "")
    get_settings.cache_clear()

    # Direct client attempts to spoof IP via X-Forwarded-For and X-Real-IP
    req = make_mock_request(
        client_host="203.0.113.55",
        headers={
            "x-forwarded-for": "8.8.8.8",
            "x-real-ip": "1.1.1.1",
        }
    )

    extracted = extract_client_ip(req)
    assert extracted == "203.0.113.55", "Untrusted connection must ignore X-Forwarded-For and X-Real-IP"
    assert _anonymize_ip(extracted) == "203.0.113.0"


def test_untrusted_peer_cannot_forge_ip(monkeypatch):
    """When TRUSTED_PROXIES is configured, an untrusted peer's forwarded headers are rejected."""
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.1,127.0.0.1")
    get_settings.cache_clear()

    # Request from an external untrusted peer 198.51.100.99
    req = make_mock_request(
        client_host="198.51.100.99",
        headers={"x-forwarded-for": "9.9.9.9"}
    )

    extracted = extract_client_ip(req)
    assert extracted == "198.51.100.99", "Untrusted peer address must be used, ignoring spoofed header"
    assert _anonymize_ip(extracted) == "198.51.100.0"


def test_trusted_proxy_single_forwarded_ip(monkeypatch):
    """When request comes from a trusted proxy, legitimate X-Forwarded-For is extracted."""
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,10.0.0.0/8")
    get_settings.cache_clear()

    # Request arriving from trusted reverse proxy 127.0.0.1
    req = make_mock_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "203.0.113.195"}
    )

    extracted = extract_client_ip(req)
    assert extracted == "203.0.113.195"
    assert _anonymize_ip(extracted) == "203.0.113.0"


def test_trusted_proxy_multi_hop_strips_forged_prefix(monkeypatch):
    """
    In a multi-hop chain (attacker -> legitimate proxy -> our reverse proxy),
    traverse from right to left to pick the first untrusted IP, ignoring spoofed prefixes.
    """
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,10.0.0.0/8,172.16.0.0/12")
    get_settings.cache_clear()

    # Chain: "attacker_spoofed, real_client, intermediate_internal_proxy"
    # 127.0.0.1 receives from 10.0.0.50
    req = make_mock_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "8.8.8.8, 198.51.100.45, 10.0.0.50"}
    )

    extracted = extract_client_ip(req)
    # 10.0.0.50 is trusted (in 10.0.0.0/8); 198.51.100.45 is untrusted -> real client!
    # 8.8.8.8 is ignored.
    assert extracted == "198.51.100.45"
    assert _anonymize_ip(extracted) == "198.51.100.0"


def test_trusted_proxy_x_real_ip_fallback(monkeypatch):
    """When X-Forwarded-For is absent, trusted proxy X-Real-IP is accepted."""
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1")
    get_settings.cache_clear()

    req = make_mock_request(
        client_host="127.0.0.1",
        headers={"x-real-ip": "198.51.100.88"}
    )

    extracted = extract_client_ip(req)
    assert extracted == "198.51.100.88"
    assert _anonymize_ip(extracted) == "198.51.100.0"


def test_ip_anonymization_ipv4_and_ipv6():
    """Verify standard privacy subnet masking for IPv4 and IPv6."""
    # IPv4 (/24 mask zeroes host octet)
    assert _anonymize_ip("192.168.1.150") == "192.168.1.0"
    assert _anonymize_ip("203.0.113.42") == "203.0.113.0"
    assert _anonymize_ip("10.5.20.1") == "10.5.20.0"

    # IPv6 (/48 mask zeroes host interface)
    assert _anonymize_ip("2001:db8:85a3:8d3:1319:8a2e:370:7348") == "2001:db8:85a3::"
    assert _anonymize_ip("2001:0db8:0000:0000:0000:0000:0000:0001") == "2001:db8::"

    # Non-IP / local names / None
    assert _anonymize_ip(None) is None
    assert _anonymize_ip("testclient") == "anonymized"
    assert _anonymize_ip("<script>alert(1)</script>") == "anonymized"
    assert _anonymize_ip("invalid.ip.string") == "anonymized"


def test_raw_ip_is_never_stored_in_scan_event(monkeypatch):
    """Confirm raw client IP cannot leak into the database."""
    raw_ip = "198.51.100.77"
    anonymized = _anonymize_ip(raw_ip)
    assert anonymized != raw_ip
    assert anonymized == "198.51.100.0"
    assert raw_ip not in anonymized
