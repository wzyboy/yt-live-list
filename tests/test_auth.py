import json
import stat
from pathlib import Path

from pytest import MonkeyPatch

from yt_live_list import auth


class FakeCredentials:
    def to_json(self) -> str:
        return json.dumps({'refresh_token': 'secret'})


class FakeFlow:
    def run_local_server(self, **kwargs: object) -> FakeCredentials:
        assert kwargs == {'port': 0, 'access_type': 'offline', 'prompt': 'consent'}
        return FakeCredentials()


def test_auth_command_writes_private_token(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    client_secrets = tmp_path / 'client.json'
    client_secrets.write_text('{}', encoding='utf-8')
    token = tmp_path / 'nested' / 'token.json'

    def fake_from_client_secrets_file(
        filename: str, scopes: list[str]
    ) -> FakeFlow:
        assert filename == str(client_secrets)
        assert scopes == ['https://www.googleapis.com/auth/youtube.readonly']
        return FakeFlow()

    monkeypatch.setattr(
        auth.InstalledAppFlow,
        'from_client_secrets_file',
        fake_from_client_secrets_file,
    )

    result = auth.main(
        ['--client-secrets', str(client_secrets), '--token', str(token)]
    )

    assert result == 0
    assert json.loads(token.read_text(encoding='utf-8')) == {
        'refresh_token': 'secret'
    }
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
