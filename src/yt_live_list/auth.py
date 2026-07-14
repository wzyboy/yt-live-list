import os
import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from yt_live_list.youtube import YOUTUBE_READONLY_SCOPE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Authorize read-only access to your YouTube broadcasts.'
    )
    parser.add_argument(
        '--client-secrets',
        type=Path,
        required=True,
        help='Downloaded Google desktop OAuth client JSON file',
    )
    parser.add_argument(
        '--token',
        type=Path,
        required=True,
        help='Destination for the generated authorized-user token JSON',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(arguments.client_secrets),
        scopes=[YOUTUBE_READONLY_SCOPE],
    )
    credentials = flow.run_local_server(
        port=0,
        access_type='offline',
        prompt='consent',
    )

    token_path: Path = arguments.token
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding='utf-8')
    os.chmod(token_path, 0o600)
    print(f'Wrote YouTube token to {token_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
