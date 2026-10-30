"""Create an invitation for a shared web trial. Never print or commit passwords."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess


def prepare(folder: Path):
    folder.mkdir(parents=True,exist_ok=True)
    folder.chmod(0o700)
    path=folder/'access.json'
    if path.exists():
        credentials=json.loads(path.read_text())
    else:
        credentials={'username':'friend','password':secrets.token_urlsafe(18)}
        # Exclusive creation avoids replacing a previously issued invitation.
        with path.open('x') as handle:json.dump(credentials,handle)
    path.chmod(0o600)
    hashed=subprocess.check_output(['openssl','passwd','-apr1','-stdin'],input=credentials['password'].encode()).decode().strip()
    auth=folder/'friends.htpasswd'
    auth.write_text(credentials['username']+':'+hashed+'\n')
    auth.chmod(0o644)  # nginx worker reads the mounted password hash, not access.json.
    print('Invitation file:',path.resolve())
    print('GUITARSCRIBE_WEB_AUTH_FILE:',auth.resolve())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    prepare(parser.parse_args().directory)
