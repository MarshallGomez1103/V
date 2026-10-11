"""Unit tests for deterministic CLI helpers."""

from __future__ import annotations

import json
from types import TracebackType
from typing import cast

import pytest
from typer.testing import CliRunner

from voz.interfaces.cli.main import (
    app as cli_app,
)
from voz.interfaces.cli.main import (
    browser_host,
    is_server_ready,
    open_browser_after_ready,
    server_url,
    wait_until_ready,
)


class FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("localhost", "localhost"),
        ("0.0.0.0", "127.0.0.1"),
        ("::", "::1"),
    ],
)
def test_browser_host_uses_connectable_address(host: str, expected: str) -> None:
    assert browser_host(host) == expected


def test_server_url_brackets_ipv6_address() -> None:
    assert server_url("::", 8765) == "http://[::1]:8765"


def test_is_server_ready_accepts_only_successful_health_payload() -> None:
    opened: list[tuple[str, float]] = []

    def http_open(url: str, *, timeout: float) -> FakeResponse:
        opened.append((url, timeout))
        return FakeResponse(200, {"status": "ok"})

    assert is_server_ready("http://127.0.0.1:8765", http_open=http_open)
    assert opened == [("http://127.0.0.1:8765/api/health", 0.5)]


def test_is_server_ready_rejects_unhealthy_payload() -> None:
    def http_open(url: str, *, timeout: float) -> FakeResponse:
        return FakeResponse(200, {"status": "starting"})

    assert not is_server_ready("http://127.0.0.1:8765", http_open=http_open)


def test_wait_until_ready_retries_until_success() -> None:
    checks = iter([False, False, True])
    clock = iter([0.0, 0.0, 0.1, 0.2])
    sleeps: list[float] = []

    assert wait_until_ready(
        "http://127.0.0.1:8765",
        timeout=1.0,
        interval=0.1,
        ready_check=lambda _url: next(checks),
        monotonic=lambda: next(clock),
        sleep=sleeps.append,
    )
    assert sleeps == [0.1, 0.1]


def test_open_browser_after_ready_does_not_open_on_timeout() -> None:
    opened: list[str] = []

    assert not open_browser_after_ready(
        "http://127.0.0.1:8765",
        ready_wait=lambda _url: False,
        browser_open=lambda url: opened.append(url) is None,
    )
    assert opened == []


def test_open_browser_after_ready_opens_confirmed_server() -> None:
    opened: list[str] = []

    assert open_browser_after_ready(
        "http://127.0.0.1:8765",
        ready_wait=lambda _url: True,
        browser_open=lambda url: not opened.append(url),
    )
    assert opened == ["http://127.0.0.1:8765"]


def test_cli_forwards_host_port_and_no_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, object] = {}

    def fake_run_server(
        *, host: str, port: int, open_browser: bool, allow_hosts: tuple[str, ...]
    ) -> None:
        received.update(
            host=host, port=port, open_browser=open_browser, allow_hosts=allow_hosts
        )

    monkeypatch.setattr("voz.interfaces.cli.main.run_server", fake_run_server)

    result = CliRunner().invoke(
        cli_app,
        [
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--no-browser",
            "--allow-host",
            "mi-pc.local",
            "--allow-host",
            "otra.local",
        ],
    )

    assert result.exit_code == 0
    assert received == {
        "host": "0.0.0.0",
        "port": 9000,
        "open_browser": False,
        "allow_hosts": ("mi-pc.local", "otra.local"),
    }


def test_cli_prepares_ffmpeg_before_serving_and_warns_in_spanish_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voz.infrastructure.audio.ffmpeg_tools import FfmpegSetup

    order: list[str] = []

    def fake_ensure(*, announce: object) -> FfmpegSetup:
        order.append("ffmpeg")
        return FfmpegSetup("failed", "No se pudo preparar FFmpeg (sin red).")

    monkeypatch.setattr("voz.interfaces.cli.main.ensure_ffmpeg", fake_ensure)

    def fake_run_server(**_kwargs: object) -> None:
        order.append("server")

    monkeypatch.setattr("voz.interfaces.cli.main.run_server", fake_run_server)

    result = CliRunner().invoke(cli_app, ["--no-browser"])

    assert result.exit_code == 0
    assert order == ["ffmpeg", "server"]
    assert "No se pudo preparar FFmpeg" in result.output


def test_run_server_reuses_a_running_voz_instead_of_binding_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from voz.interfaces.cli import main

    opened: list[str] = []

    def ready(_url: str) -> bool:
        return True

    monkeypatch.setattr(main, "is_server_ready", ready)
    monkeypatch.setattr(main.webbrowser, "open", opened.append)
    monkeypatch.setattr(main, "create_app", lambda: pytest.fail("must not start"))

    main.run_server(host="127.0.0.1", port=8765, open_browser=True)

    assert opened == ["http://127.0.0.1:8765"]
    assert "VOZ ya está abierto" in capsys.readouterr().out


def _not_ready(_url: str) -> bool:
    return False


def _stub_server(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace Uvicorn and the app factory; return the kwargs given to the app."""
    from voz.interfaces.cli import main

    seen: dict[str, object] = {}

    def fake_create_app(**kwargs: object) -> object:
        seen.update(kwargs)
        return object()

    class FakeServer:
        def __init__(self, config: object) -> None: ...

        def run(self) -> None: ...

    monkeypatch.setattr(main, "is_server_ready", _not_ready)
    monkeypatch.setattr(main, "create_app", fake_create_app)
    monkeypatch.setattr(main.uvicorn, "Server", FakeServer)
    return seen


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20"])
def test_run_server_warns_on_stderr_when_exposed_beyond_loopback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
) -> None:
    from voz.interfaces.cli import main

    _stub_server(monkeypatch)
    monkeypatch.setattr(main, "local_addresses", lambda: ())

    main.run_server(host=host, port=8765, open_browser=False)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "no authentication" in captured.err
    assert host in captured.err
    assert "WARNING" not in captured.out


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.1.1", "localhost", "::1"])
def test_run_server_does_not_warn_on_loopback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
) -> None:
    from voz.interfaces.cli import main

    _stub_server(monkeypatch)

    main.run_server(host=host, port=8765, open_browser=False)

    captured = capsys.readouterr()
    assert "WARNING" not in captured.err
    assert "WARNING" not in captured.out


@pytest.mark.parametrize("host", ["0.0.0.0", "::"])
def test_wildcard_bind_allows_this_machines_own_addresses(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    from voz.interfaces.cli import main

    seen = _stub_server(monkeypatch)
    monkeypatch.setattr(main, "local_addresses", lambda: ("192.168.1.20", "mi-pc"))

    main.run_server(
        host=host, port=8765, open_browser=False, allow_hosts=("mi-pc.local",)
    )

    allowed = cast(tuple[str, ...], seen["allowed_hosts"])
    assert {"127.0.0.1", "localhost", "::1"} <= set(allowed)
    assert {"192.168.1.20", "mi-pc", "mi-pc.local"} <= set(allowed)


def test_concrete_bind_does_not_add_machine_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voz.interfaces.cli import main

    seen = _stub_server(monkeypatch)
    monkeypatch.setattr(main, "local_addresses", lambda: ("10.0.0.5",))

    main.run_server(host="192.168.1.20", port=8765, open_browser=False)

    assert seen["allowed_hosts"] == ("192.168.1.20",)


def test_local_addresses_tolerates_resolver_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from voz.interfaces.cli import main

    def boom(*_args: object, **_kwargs: object) -> object:
        raise OSError("no resolver")

    monkeypatch.setattr(socket, "gethostname", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)

    assert main.local_addresses() == ()
