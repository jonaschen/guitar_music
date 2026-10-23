"""Explicit stem-supported harmony hypothesis; never treats mixed/stem disagreement as approval."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.evaluation.harmony_overlay import overlay_harmony
from app.exporters.midi import PlaybackManifest, export_manifest_midi


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new output directory')
    base=PlaybackManifest.model_validate_json(args.base.read_text())
    report=json.loads(args.audit.read_text())
    if base.revision!='e20ee58c35c73cd1' or report['revision']!='db8c657e-62a5-4fad-a33e-cde25a9e1c0d':
        raise ValueError('This explicit experiment requires its pinned source revision')
    selected={};decisions=[]
    methods=report['sources']['accompaniment-stem']['methods']
    for hypothesis in methods['cqt']:
        name=hypothesis['name'];times=[];support=[]
        for method in ['cqt','stft_2048','stft_4096']:
            row=next(r for r in methods[method] if r['name']==name)
            qualified=[r for r in row['sustained_support'] if min(r['old_pre_fraction'],r['new_post_fraction'])>=.75]
            support.append({'method':method,'qualified':qualified})
            if len(qualified)==1:times.append(qualified[0]['time'])
        accepted=len(times)==3 and max(times)-min(times)<=.10
        target=median(times) if accepted else None
        decisions.append({'name':name,'target':target,'accepted_for_experiment':accepted,'support':support})
        if accepted:selected[name]=target
    required=['D_to_G_without_Am','G_to_C_extended','G_to_Am']
    if not all(k in selected for k in required):raise ValueError('This explicit sequence hypothesis lacks sustained stem evidence')
    # This song-specific recipe is deliberately separate from the reusable overlay.
    # Select exactly the existing attacks that introduce the new spans, no inserted strokes.
    guitar=[e for e in base.events if e.track=='guitar']
    def at(time):
        matches=[e for e in guitar if abs(e.start-time)<1e-8]
        if len(matches)!=1:raise ValueError('Pinned attack missing or ambiguous')
        return matches[0]
    d=at(66.52480725623583); g=at(68.18539682539682)
    c=at(70.03138321995465); a=at(73.73496598639456)
    # All retained boundaries belong to the pinned previous candidate, not lyric taps.
    wind=at(72.07437641723356); last=at(75.53451247165533)
    moves={g.id:selected[required[0]],c.id:selected[required[1]],a.id:selected[required[2]]}
    bounds=[d.start,moves[g.id],moves[c.id],wind.start,moves[a.id],last.start]
    refs=['chord-94','chord-98','chord-99','chord-103','chord-107']
    spans=[dict(start=l,end=r,reference_source_id=ref) for l,r,ref in zip(bounds,bounds[1:],refs)]
    candidate=overlay_harmony(base,spans,moves,base.revision)
    assert [e for e in candidate.events if e.track!='guitar']==[e for e in base.events if e.track!='guitar']
    assert len(candidate.events)==len(base.events)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'manifest.json').write_text(candidate.model_dump_json(indent=2))
    (args.output/'performance.mid').write_bytes(export_manifest_midi(candidate))
    (args.output/'recipe.json').write_text(json.dumps({'expected_revision':base.revision,'spans':spans,'moves':moves},indent=2))
    (args.output/'report.json').write_text(json.dumps({'decisions':decisions,'candidate_revision':candidate.revision,
      'hypothesis':'Prefer sustained separated accompaniment evidence for this experiment, retaining mixed-source disagreement.',
      'parameters':{'min_pre_post_fraction':.75,'max_cross_method_spread':.10},
      'limits':'Not an automatic production policy. Shared source separation bias remains. Em entry unresolved, retained. Later beat slots stay fixed.',
      'human_marks_used_for_timing':False,'base_path':str(args.base),'audit_path':str(args.audit)},indent=2))
    print(json.dumps({'spans':spans,'moves':moves,'decisions':[(d['name'],d['accepted_for_experiment'])for d in decisions]},indent=2))


if __name__=='__main__':main()
