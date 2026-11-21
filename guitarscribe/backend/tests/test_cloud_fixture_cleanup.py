import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

from app.services.jobs import JobStore
from app.services.root_practice import RootPracticeStore
from app.services.song_structure import SongStructureStore


def test_owned_cloud_fixture_removes_only_its_new_empty_tables_and_learning_file(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[2]/'infra/on_demand/verify_cloud_fixture.py'
    spec=importlib.util.spec_from_file_location('fixture_cleanup',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',tmp_path);monkeypatch.setattr(module,'WORK',tmp_path/'work');monkeypatch.setattr(module,'MARKER',tmp_path/'marker.json')
    monkeypatch.setitem(sys.modules,'host_activity',SimpleNamespace(active_analysis=lambda _:False))
    work=module.WORK;work.mkdir();JobStore(work/'jobs');RootPracticeStore(work/'root-practice.sqlite3');SongStructureStore(work/'song-structure.sqlite3')
    with sqlite3.connect(work/'chord-practice.sqlite3') as db:
        db.execute('CREATE TABLE chord_practice(job_id TEXT PRIMARY KEY,document TEXT)');db.execute('INSERT INTO chord_practice VALUES(?,?)',('user-song','untouched'))
    before=module.db_hashes();module.seed();identifier=json.loads(module.MARKER.read_text())['job_id']
    with sqlite3.connect(work/'chord-practice.sqlite3') as db:
        db.execute('CREATE TABLE chord_context(job_id TEXT,basis TEXT)');db.execute('INSERT INTO chord_context VALUES(?,?)',(identifier,'owned'))
        db.execute('CREATE TABLE chord_reuse_ledger(job_id TEXT,operation TEXT)');db.execute('INSERT INTO chord_reuse_ledger VALUES(?,?)',(identifier,'owned'))
    with sqlite3.connect(work/'learning-practice.sqlite3') as db:
        db.execute('CREATE TABLE learning_practice(job_id TEXT,document TEXT)');db.execute('INSERT INTO learning_practice VALUES(?,?)',(identifier,'owned'))
    module.clean();assert module.db_hashes()==before;assert not module.MARKER.exists();assert not (work/'learning-practice.sqlite3').exists()
