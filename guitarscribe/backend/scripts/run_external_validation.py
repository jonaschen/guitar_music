"""Execute bounded Klangio experiments on the approved three-clip packet.

Submission requires confirmed free quota or a user-confirmed unpaid new account.
No purchases, automatic POST retries, redirects, or changes to product data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import requests


TASKS = [("beats", "/beat-tracking", {}),
         ("chords", "/chord-recognition", {"vocabulary": "major-minor"})]
BASE = "https://api.klang.io"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_state(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2)+"\n")
    temporary.replace(path)


def packet_cases(packet):
    manifest = json.loads((packet / "manifest.json").read_text())
    cases = manifest["cases"]
    if len(cases) != 3 or manifest["maximum_job_creations"] != 6:
        raise ValueError("Only the approved three-clip, six-job packet is supported")
    if len({c["recording_id"] for c in cases}) != 3:
        raise ValueError("Duplicate recording IDs")
    for case in cases:
        for key in ("clip", "recording_id"):
            if Path(case[key]).name != case[key] or case[key] in {".", ".."}:
                raise ValueError("Unsafe packet path")
        clip = packet / case["clip"]
        if case["start"] != 0 or case["end"] != 15 or sha(clip) != case["clip_sha256"]:
            raise ValueError("Clip differs from approved packet")
    return cases, sha(packet / "manifest.json")


def submit(packet, output, session, *, confirmed_free_requests=0, confirmed_unpaid_account=False):
    cases, manifest_sha = packet_cases(packet)
    if confirmed_free_requests < len(cases)*len(TASKS) and not confirmed_unpaid_account:
        raise ValueError("Free quota or an unpaid new account must be confirmed before upload")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        for kind, endpoint, query in TASKS:
            state_path = output / (case["recording_id"]+"."+kind+".job.json")
            if state_path.exists():
                state = json.loads(state_path.read_text())
                if (state.get("manifest_sha256") != manifest_sha or state.get("clip_sha256") != case["clip_sha256"]
                        or state.get("endpoint") != endpoint or state.get("query") != query):
                    raise ValueError("Existing job belongs to another packet")
                if not state.get("job_id"):
                    raise RuntimeError("Prior submission outcome uncertain; inspect account, do not resubmit")
                rows.append({"recording_id": case["recording_id"], "kind": kind, "state": "already_submitted"})
                continue
            state = {"recording_id": case["recording_id"], "kind": kind,
                     "clip_sha256": case["clip_sha256"], "manifest_sha256": manifest_sha,
                     "endpoint": endpoint, "query": query, "state": "submission_started",
                     "spending_limit_usd": 0, "confirmed_free_requests_before_batch": confirmed_free_requests,
                     "user_confirmed_unpaid_new_account": confirmed_unpaid_account}
            # Persist before POST. A timeout or crash must not cause a second billable job.
            with state_path.open("x") as target:
                json.dump(state, target, indent=2)
            try:
                time.sleep(0.6)  # Stay below the lowest published 2-job/second tier.
                with (packet / case["clip"]).open("rb") as audio:
                    response = session.post(BASE+endpoint, params=query,
                                            files={"file": (case["clip"], audio, "audio/wav")},
                                            timeout=(10, 45), allow_redirects=False)
                state["http_status"] = response.status_code
                if response.status_code != 200:
                    state["state"] = "submission_rejected_or_unknown"
                    write_state(state_path, state)
                    raise RuntimeError(f"Submission stopped at HTTP {response.status_code}; no retry")
                job = response.json().get("job_id")
                if not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", job):
                    raise ValueError("Unexpected job identifier")
                state.update(job_id=job, state="submitted")
                write_state(state_path, state)
                rows.append({"recording_id": case["recording_id"], "kind": kind, "state": "submitted"})
            except (requests.RequestException, ValueError) as exc:
                state.update(state="submission_outcome_unknown", error_type=type(exc).__name__)
                write_state(state_path, state)
                raise RuntimeError("Submission interrupted; journal preserved, no automatic retry") from None
    return rows


def collect(packet, output, session):
    cases, manifest_sha = packet_cases(packet)
    rows = []
    for case in cases:
        for kind, _, _ in TASKS:
            prefix = case["recording_id"]+"."+kind
            state_path, result_path = output / (prefix+".job.json"), output / (prefix+".json")
            state = json.loads(state_path.read_text())
            if state.get("manifest_sha256") != manifest_sha or not state.get("job_id"):
                raise ValueError("Unbound or uncertain job; cannot collect")
            if result_path.exists():
                if sha(result_path) != state.get("result_sha256"):
                    raise ValueError("Existing result has changed or collection was interrupted")
                rows.append({"recording_id": case["recording_id"], "kind": kind, "state": "cached"})
                continue
            url = BASE+"/job/"+state["job_id"]
            response = session.get(url+"/status", timeout=(10, 30), allow_redirects=False)
            if response.status_code != 200:
                raise RuntimeError(f"Status HTTP {response.status_code}")
            status = response.json().get("status")
            if status not in {"IN_QUEUE", "IN_PROGRESS", "FAILED", "COMPLETED"}:
                raise ValueError("Unexpected remote status")
            state["remote_status"] = status
            write_state(state_path, state)
            if status == "COMPLETED":
                response = session.get(url+"/json", timeout=(10, 30), allow_redirects=False)
                if response.status_code != 200:
                    raise RuntimeError(f"Result HTTP {response.status_code}")
                result = response.json()
                if not isinstance(result, list):
                    raise ValueError("Expected a result array; unexpected body not logged")
                with result_path.open("x") as target:
                    json.dump(result, target, indent=2, allow_nan=False)
                    target.write("\n")
                state.update(state="collected", result_sha256=sha(result_path))
                write_state(state_path, state)
            rows.append({"recording_id": case["recording_id"], "kind": kind, "state": status})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["submit", "collect"])
    parser.add_argument("packet", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key-file", type=Path, default=Path.home()/".config/guitarscribe/klangio-api-key")
    parser.add_argument("--confirmed-free-requests", type=int, default=0)
    parser.add_argument("--confirmed-unpaid-account", action="store_true")
    parser.add_argument("--chords-only", action="store_true")
    parser.add_argument("--vocabulary", choices=["major-minor", "full"], default="major-minor")
    args = parser.parse_args()
    TASKS = [(kind, endpoint, {"vocabulary": args.vocabulary} if kind == "chords" else query)
             for kind, endpoint, query in TASKS if not args.chords_only or kind == "chords"]
    key = args.key_file.read_text().strip()
    if not key or any(c.isspace() for c in key):
        raise SystemExit("Key file must contain only the API key")
    with requests.Session() as session:
        session.headers["kl-api-key"] = key
        try:
            rows = (submit(args.packet, args.output, session, confirmed_free_requests=args.confirmed_free_requests,
                           confirmed_unpaid_account=args.confirmed_unpaid_account)
                    if args.action == "submit" else collect(args.packet, args.output, session))
            print(json.dumps(rows))
        except (ValueError, RuntimeError, requests.RequestException, OSError) as exc:
            # Do not print transport exceptions or server bodies that might contain credentials.
            print(json.dumps({"stopped": True, "error_type": type(exc).__name__}))
            sys.exit(1)
