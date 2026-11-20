#!/usr/bin/env python3
"""Read GuitarScribe cloud state without waking/stopping/deploying anything.

Uses explicit project/resource arguments; never changes gcloud configuration.
Credentials are read only for the authenticated status request, never emitted.
Run from any directory with --repo, or from the checked-out skill in its repo.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if result.returncode:
            # Do not echo arbitrary CLI diagnostics or environment into reports.
            return {'ok': False, 'exit_code': result.returncode,
                    'error': 'Command failed; inspect local gcloud authentication/permissions separately.'}
        return {'ok': True, 'data': json.loads(result.stdout)}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {'ok': False, 'error': type(error).__name__}


def http_status(origin, access=None):
    headers = {}
    path = '/'
    if access:
        path = '/cloud/status'
        headers['Authorization'] = 'Basic ' + base64.b64encode(
            (access['username'] + ':' + access['password']).encode()).decode()
    request = urllib.request.Request(origin + path, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as response:
            if not access: return {'http_status': response.status}
            payload = json.loads(response.read(65536))
            # The public status endpoint is the only API read: no songs/audio.
            return {'http_status': response.status, **{key: payload.get(key) for key in (
                'state', 'used_seconds', 'limit_seconds', 'remaining_seconds', 'window_days', 'can_wake', 'stop_at')}}
    except urllib.error.HTTPError as error:
        return {'http_status': error.code}
    except (OSError, ValueError) as error:
        return {'error': type(error).__name__}


def inspect(repo, runner=command, fetch=http_status):
    repo = Path(repo).resolve()
    app = repo / 'guitarscribe'
    config = json.loads((app / 'infra/on_demand/deployment.json').read_text())
    # An edited manifest cannot redirect an Authorization header to another site.
    expected_origin = f"https://{config['service']}-{config['project_number']}.{config['region']}.run.app"
    if config['url'] != expected_origin or config['project_number'] != '324350766154':
        raise ValueError('Deployment target changed; review cloud operations reference before using credentials')
    project = '--project=' + config['project_id']
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'project': config['project_id'],
              'url': config['url'], 'declared_release': config.get('app_release'),
              'declared_commit': config.get('app_commit'), 'automatic_wake': False}
    report['vm'] = runner(['gcloud', 'compute', 'instances', 'describe', config['instance'], project,
        '--zone=' + config['zone'], '--quiet', '--verbosity=error',
        '--format=json(name,id,status,lastStartTimestamp,lastStopTimestamp,scheduling,disks[].deviceName,disks[].autoDelete,networkInterfaces[].networkIP)'])
    report['gateway'] = runner(['gcloud', 'run', 'services', 'describe', config['service'], project,
        '--region=' + config['region'], '--quiet', '--verbosity=error',
        '--format=json(status.latestReadyRevisionName,status.conditions,spec.template.spec.containers[].image,spec.template.metadata.annotations)'])
    report['anonymous'] = fetch(config['url'])
    access_path = app / 'output/cloud-control/access.json'
    if access_path.is_file():
        try:
            report['authenticated'] = fetch(config['url'], json.loads(access_path.read_text()))
        except (OSError, ValueError, KeyError) as error:
            report['authenticated'] = {'error': type(error).__name__}
    else:
        report['authenticated'] = {'error': 'Local access file unavailable; do not rotate or replace credentials to inspect status.'}
    objects = runner(['gcloud', 'storage', 'ls', '--json',
        f"gs://{config['bucket']}/backups/manifests/*.json", project, '--quiet', '--verbosity=error'])
    if objects.get('ok'):
        rows = [item['metadata'] for item in objects['data'] if item.get('type') == 'cloud_object']
        latest = sorted(rows, key=lambda item: item['timeCreated'], reverse=True)[:5]
        report['backup_manifests'] = {'ok': True, 'count': len(rows), 'latest': [
            {key: item.get(key) for key in ('name', 'generation', 'timeCreated', 'size')} for item in latest]}
    else:
        report['backup_manifests'] = objects
    report['billing'] = {'actual_cost': 'not_checked', 'monthly_target_twd': config['monthly_target_twd'],
                         'usage_ledger_is_not_a_bill': True}
    report['notes'] = [
        'TERMINATED/stopped with can_wake=true is normal idle operation, not an outage.',
        'Status reads may settle existing usage reservations; they never start the VM.',
        'A backup object listing proves presence only. Use a verified manifest for restore; do not overwrite work.',
        'Read-only inspection does not establish that all music judgments or all repository CI pass.'
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output', type=Path, help='Optional local JSON report; contains no credentials or song contents')
    args = parser.parse_args()
    report = inspect(args.repo)
    result = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result); args.output.chmod(0o600)
    print(result, end='')


if __name__ == '__main__':
    main()
