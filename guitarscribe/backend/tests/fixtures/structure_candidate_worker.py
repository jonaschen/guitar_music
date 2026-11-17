"""Deterministic subprocess fixture. This does not perform music inference."""
import argparse
import json
from pathlib import Path
import time
p=argparse.ArgumentParser();p.add_argument('--protocol');p.add_argument('--job');p.add_argument('--out');args=p.parse_args()
protocol=json.loads(Path(args.protocol).read_text());source=protocol['sources'][0];out=Path(args.out);out.mkdir(parents=True)
time.sleep(1)
duration=source['root_source']['duration']
sections=[dict(id=f'section-{i+1}',start=start,end=end,label=label,display_label=display,
               review_status='unreviewed',model_end=end,generated_gap=False)
          for i,(start,end,label,display) in enumerate([(0.,3.,'intro','前奏'),(3.,duration,'chorus','副歌')])]
candidate=dict(title=source['title'],job=source['job'],fingerprint=source['root_source']['fingerprint'],
               source_start=source['root_source']['source_start'],duration=duration,sections=sections,
               ready_as_default=False,semantic_quality='not_evaluated',reference_status='not_annotated')
(out/'candidate.json').write_text(json.dumps(candidate))
(out/'manifest.json').write_text(json.dumps(dict(status='candidate_ready_unreviewed',source=source)))
