"""ProviderSecrets: precedence, 0600 enforcement, atomic writes and no leaks."""

import logging
import os
import stat
from pathlib import Path

import pytest

from voz.application.ports.provider_secrets import SecretsError, SecretsFailureCode
from voz.infrastructure.secrets import SECRETS_FILENAME, ProviderSecrets

KEY = "sk-test-0123456789abcdef"


def _secrets(tmp_path: Path, **environ: str) -> ProviderSecrets:
    return ProviderSecrets(tmp_path / "voz", environ=environ)


def test_unconfigured_by_default(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path)
    assert secrets.get("openai") is None
    assert secrets.configured("openai") is False


def test_environment_precedence(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path, OPENAI_API_KEY="generic", VOZ_OPENAI_API_KEY="voz")
    assert secrets.get("openai") == "voz"
    assert _secrets(tmp_path, OPENAI_API_KEY="generic").get("openai") == "generic"
    assert _secrets(tmp_path, ELEVENLABS_API_KEY=" eleven ").get("elevenlabs") == (
        "eleven"
    )
    assert _secrets(tmp_path, OPENAI_API_KEY="  ").configured("openai") is False


def test_environment_wins_over_file(tmp_path: Path) -> None:
    _secrets(tmp_path).set("openai", KEY)
    assert _secrets(tmp_path, OPENAI_API_KEY="env").get("openai") == "env"
    assert _secrets(tmp_path).get("openai") == KEY


def test_set_writes_a_private_file_and_round_trips(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path)
    secrets.set("openai", KEY)
    secrets.set("elevenlabs", "other-key")
    path = tmp_path / "voz" / SECRETS_FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert secrets.get("openai") == KEY
    assert secrets.get("elevenlabs") == "other-key"
    assert sorted(p.name for p in path.parent.iterdir()) == [SECRETS_FILENAME]


def test_set_overwrites_and_delete_removes(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path)
    secrets.set("openai", KEY)
    secrets.set("openai", "second-key")
    secrets.set("elevenlabs", "other")
    assert secrets.get("openai") == "second-key"
    secrets.delete("openai")
    assert secrets.configured("openai") is False
    assert secrets.configured("elevenlabs") is True
    secrets.delete("elevenlabs")
    assert not (tmp_path / "voz" / SECRETS_FILENAME).exists()
    secrets.delete("openai")  # idempotent


@pytest.mark.parametrize(
    "key", ["", " ", "a b", 'q"uote ', "line\nbreak", "é", "x" * 513]
)
def test_invalid_keys_are_rejected_without_echo(tmp_path: Path, key: str) -> None:
    with pytest.raises(SecretsError) as raised:
        _secrets(tmp_path).set("openai", key)
    assert raised.value.code is SecretsFailureCode.KEY_INVALID
    assert key.strip() == "" or key not in str(raised.value)


def test_key_with_quotes_and_backslash_survives_toml(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path)
    tricky = 'sk-"q"\\back=slash'
    secrets.set("openai", tricky)
    assert secrets.get("openai") == tricky


def test_group_readable_file_is_an_insecure_error(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path)
    secrets.set("openai", KEY)
    path = tmp_path / "voz" / SECRETS_FILENAME
    path.chmod(0o640)
    with pytest.raises(SecretsError) as raised:
        secrets.get("openai")
    assert raised.value.code is SecretsFailureCode.FILE_INSECURE
    assert KEY not in str(raised.value)
    assert secrets.configured("openai") is False
    with pytest.raises(SecretsError):
        secrets.set("openai", "new")


def test_symlinked_secrets_file_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "voz"
    directory.mkdir()
    target = tmp_path / "elsewhere.toml"
    target.write_text('"openai" = "x"\n')
    target.chmod(0o600)
    os.symlink(target, directory / SECRETS_FILENAME)
    with pytest.raises(SecretsError) as raised:
        _secrets(tmp_path).get("openai")
    assert raised.value.code is SecretsFailureCode.FILE_INSECURE


def test_corrupt_file_is_a_typed_error(tmp_path: Path) -> None:
    directory = tmp_path / "voz"
    directory.mkdir()
    path = directory / SECRETS_FILENAME
    path.write_text("not = = toml")
    path.chmod(0o600)
    with pytest.raises(SecretsError) as raised:
        _secrets(tmp_path).get("openai")
    assert raised.value.code is SecretsFailureCode.FILE_INVALID


def test_unsafe_provider_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="provider_id"):
        _secrets(tmp_path).get("../etc")


def test_repr_and_str_do_not_reveal_secrets_or_paths(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path, OPENAI_API_KEY=KEY)
    secrets.set("openai", "file-key-123")
    for text in (repr(secrets), str(secrets), f"{secrets!r}"):
        assert KEY not in text
        assert "file-key-123" not in text
        assert str(tmp_path) not in text


def test_operations_do_not_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    secrets = _secrets(tmp_path)
    secrets.set("openai", KEY)
    secrets.get("openai")
    secrets.delete("openai")
    assert KEY not in caplog.text
