"""LAN authentication fails closed before reuse and keeps credentials private."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer
from typer.testing import CliRunner

from voz.infrastructure.server_token import create_server_token, read_server_token
from voz.interfaces.cli import main


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20"])
def test_lan_requires_token_before_reuse(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = Mock(return_value=True)
    monkeypatch.setattr(main, "is_server_ready", ready)
    with pytest.raises(typer.BadParameter, match="auth-token-file"):
        main.run_server(host=host, port=8765, open_browser=False)
    ready.assert_not_called()


def test_create_token_command_never_prints_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "prepare_ffmpeg", lambda: None)
    target = tmp_path / "token"
    result = CliRunner().invoke(main.app, ["auth-token", "--output", str(target)])
    assert result.exit_code == 0, result.output
    assert read_server_token(target) not in result.output
    assert str(target) not in result.output
    repeated = CliRunner().invoke(main.app, ["auth-token", "--output", str(target)])
    assert repeated.exit_code == 2
    assert read_server_token(target) not in repeated.output


def test_authenticated_reuse_passes_token_only_in_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "token"
    create_server_token(target)
    secret = read_server_token(target)
    ready = Mock(return_value=True)
    browser = Mock()
    monkeypatch.setattr(main, "is_server_ready", ready)
    monkeypatch.setattr(main.webbrowser, "open", browser)
    main.run_server(
        host="0.0.0.0", port=8765, open_browser=True, auth_token_file=target
    )
    ready.assert_called_once_with("http://127.0.0.1:8765", auth_token=secret)
    browser.assert_called_once_with("http://127.0.0.1:8765")


def test_invalid_token_file_rejected_before_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = Mock(return_value=True)
    monkeypatch.setattr(main, "is_server_ready", ready)
    with pytest.raises(typer.BadParameter):
        main.run_server(
            host="127.0.0.1",
            port=8765,
            open_browser=False,
            auth_token_file=tmp_path / "missing",
        )
    ready.assert_not_called()


def test_readiness_sends_token_in_authorization_header_only() -> None:
    import urllib.request
    from collections.abc import Generator
    from contextlib import contextmanager

    seen: list[urllib.request.Request] = []

    class Response:
        status = 200

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    @contextmanager
    def http_open(
        request: urllib.request.Request, *, timeout: float
    ) -> Generator[Response]:
        assert timeout == 0.5
        seen.append(request)
        yield Response()

    token = "x" * 43
    assert main.is_server_ready(
        "http://localhost:8765", auth_token=token, http_open=http_open
    )
    assert seen[0].full_url == "http://localhost:8765/api/health"
    assert seen[0].get_header("Authorization") == "Bearer " + token
    assert token not in seen[0].full_url


def test_browser_polling_retains_auth_but_url_stays_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "x" * 43
    ready = Mock(return_value=True)
    opened = Mock(return_value=True)
    monkeypatch.setattr(main, "is_server_ready", ready)

    def open_after_ready(base_url: str, *, ready_wait: Callable[[str], bool]) -> bool:
        return bool(ready_wait(base_url) and opened(base_url))

    monkeypatch.setattr(main, "open_browser_after_ready", open_after_ready)
    thread = main.start_browser_opener("http://localhost:8765", auth_token=token)
    thread.join(timeout=2)
    assert not thread.is_alive()
    ready.assert_called_once_with("http://localhost:8765", auth_token=token)
    opened.assert_called_once_with("http://localhost:8765")


@pytest.mark.parametrize("prefix", [[], ["serve"]])
def test_cli_forwards_only_explicit_token_file(
    prefix: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "token"
    create_server_token(target)
    run = Mock()
    monkeypatch.setattr(main, "prepare_ffmpeg", lambda: None)
    monkeypatch.setattr(main, "run_server", run)
    result = CliRunner().invoke(
        main.app, [*prefix, "--auth-token-file", str(target), "--no-browser"]
    )
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["auth_token_file"] == target
    assert read_server_token(target) not in result.output
