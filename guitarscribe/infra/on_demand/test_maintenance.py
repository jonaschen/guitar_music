"""Backup observability never mistakes an attempt for a completed backup."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
import pytest
import backup_work as backup
from host_activity import maintenance_status


def test_completed_backup_survives_later_failure_and_skip(tmp_path):
    status = tmp_path / 'maintenance/status.json'
    work = tmp_path / 'work'; work.mkdir()
    def complete(*args, **kwargs):
        return dict(status='complete', manifest='backups/manifests/good.json', manifest_sha256='a'*64, files=4)
    backup.observed_backup(work, None, status_file=status, clock=lambda: 100, runner=complete)
    first = json.loads(status.read_text())
    assert first['last_success']['snapshot_at'] == 100
    assert status.stat().st_mode & 0o777 == 0o600
    def fail(*args, **kwargs): raise OSError('secret token/private/song')
    with pytest.raises(OSError):
        backup.observed_backup(work, None, status_file=status, clock=lambda: 200, runner=fail)
    assert json.loads(status.read_text())['last_success'] == first['last_success']
    assert 'secret' not in status.read_text()
    view = maintenance_status(work, status, now=210)
    assert view['backup']['state'] == 'failed'
    assert view['backup']['last_success_at'] == 100
    def skip(*args, **kwargs): raise backup.BackupSkipped('analysis')
    with pytest.raises(backup.BackupSkipped):
        backup.observed_backup(work, None, status_file=status, clock=lambda: 300, runner=skip)
    view = maintenance_status(work, status, now=310)
    assert view['backup']['state'] == 'deferred'
    assert view['backup']['last_success_at'] == 100
    assert not list(work.iterdir())


def test_pending_edits_missing_corrupt_and_interrupted_are_not_healthy(tmp_path):
    work = tmp_path / 'work'; work.mkdir()
    status = tmp_path / 'status.json'
    assert maintenance_status(work, status, now=100)['backup']['state'] == 'unknown'
    status.write_text('not json')
    assert maintenance_status(work, status, now=100)['backup']['state'] == 'unknown'
    status.write_text(json.dumps(dict(state='running', started_at=100, last_success=None)))
    assert maintenance_status(work, status, now=200)['backup']['state'] == 'running'
    assert maintenance_status(work, status, now=2000)['backup']['state'] == 'interrupted'
    status.write_text(json.dumps(dict(state='complete', finished_at=110, last_success=dict(snapshot_at=100, completed_at=110))))
    database = work / 'chord-practice.sqlite3'; database.touch(); os.utime(database,(120,120))
    assert maintenance_status(work, status, now=130)['backup']['state'] == 'pending'
    os.utime(database,(90,90))
    assert maintenance_status(work, status, now=50000)['backup']['state'] == 'complete'
    wal = work / 'chord-practice.sqlite3-wal'; wal.touch(); os.utime(wal,(140,140))
    assert maintenance_status(work, status, now=150)['backup']['state'] == 'pending'
    assert 'disk_available_bytes' in maintenance_status(work,status)


def test_status_cannot_be_inside_work_or_overwrite_inflight_attempt(tmp_path):
    work = tmp_path / 'work'; work.mkdir()
    with pytest.raises(ValueError): backup.observed_backup(work,None,status_file=work/'state.json')
    status = tmp_path / 'status.json'
    def nested(*args, **kwargs):
        before = status.read_text()
        with pytest.raises(backup.BackupSkipped): backup.observed_backup(work,None,status_file=status)
        assert status.read_text() == before
        return dict(status='complete',manifest='backups/manifests/good.json',manifest_sha256='a'*64,files=0)
    backup.observed_backup(work,None,status_file=status,runner=nested)
