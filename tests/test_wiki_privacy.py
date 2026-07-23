"""Tests for wiki privacy redaction (emdx/services/wiki_privacy_service.py).

Regression tests for the private-IP redaction regex: the old pattern
gave the ``10`` alternative only two trailing octet groups, so
``10.1.2.3`` was redacted to ``[INTERNAL_IP].3`` (leaking the host
octet) and version strings like ``macOS 10.15.7`` were mangled.
"""

from __future__ import annotations

import pytest

from emdx.services.wiki_privacy_service import postprocess_validate, preprocess_content


class TestPrivateIpRedaction:
    @pytest.mark.parametrize(
        "ip",
        [
            "10.1.2.3",
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.100",
            "192.168.0.1",
        ],
    )
    def test_private_ips_fully_redacted(self, ip: str) -> None:
        content = f"The server lives at {ip} behind the VPN."
        result, warnings = preprocess_content(content)

        assert ip not in result
        assert "[INTERNAL_IP]" in result
        # No partial redaction leaving a trailing octet (e.g. "[INTERNAL_IP].3")
        assert "[INTERNAL_IP]." not in result
        assert any("internal IP" in w for w in warnings)

    def test_10_x_host_octet_does_not_leak(self) -> None:
        """Regression: 10.1.2.3 must not become '[INTERNAL_IP].3'."""
        result, _ = preprocess_content("connect to 10.1.2.3 now")
        assert result == "connect to [INTERNAL_IP] now"

    @pytest.mark.parametrize(
        "text",
        [
            "macOS 10.15.7 is old",  # version string, only 3 octets
            "Python 3.10.12 release",
            "see 8.8.8.8 for DNS",  # public IP
            "172.32.1.1 is not RFC 1918",  # outside 172.16-31
            "172.15.0.1 is not RFC 1918",
            "192.169.1.1 is not RFC 1918",
            "11.0.0.1 is public",
        ],
    )
    def test_non_private_addresses_untouched(self, text: str) -> None:
        result, warnings = preprocess_content(text)
        assert result == text
        assert not any("internal IP" in w for w in warnings)

    def test_multiple_ips_counted(self) -> None:
        content = "hosts: 10.0.0.1, 192.168.1.2, 172.16.5.5"
        result, warnings = preprocess_content(content)
        assert result.count("[INTERNAL_IP]") == 3
        assert any("3 internal IP" in w for w in warnings)

    def test_postprocess_validate_redacts_private_ips(self) -> None:
        """Layer 3 reuses the same patterns and must also fully redact."""
        result, warnings = postprocess_validate("leaked 10.1.2.3 in output")
        assert "10.1.2.3" not in result
        assert "[INTERNAL_IP]" in result
        assert "[INTERNAL_IP]." not in result
        assert any("internal IP" in w for w in warnings)

    def test_postprocess_validate_leaves_version_strings(self) -> None:
        content = "Tested on macOS 10.15.7"
        result, warnings = postprocess_validate(content)
        assert result == content
        assert not any("internal IP" in w for w in warnings)
