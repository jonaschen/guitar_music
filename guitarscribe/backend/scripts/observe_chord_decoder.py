"""One bounded, isolated trace run per source; no decoder modifications."""
import datetime as dt
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import historical_events, projected_events, parity, sha, write
from app.models.analysis import ChordEvent

TRACE = r'''
    const char* tracePath = std::getenv("GUITARSCRIBE_TRACE_PATH");
    if (tracePath) {
        std::ofstream trace(tracePath);
        trace << std::setprecision(17);
        trace << "{\"dictionary\":[";
        for (int c=0;c<nChord;++c) {
            if(c) trace << ",";
            trace << "{\"index\":" << c << ",\"label\":" << std::quoted(m_chordnames[c]) << ",\"weights\":[";
            for(int k=0;k<24;++k) {if(k)trace<<",";trace<<m_chorddict[c*24+k];}
            trace << "]}";
        }
        trace << "],\"frames\":[";
        for (int f=0;f<nFrame;++f) {
            if(f)trace<<",";
            const auto& emission=chordogram[f];
            int best=std::max_element(emission.begin(),emission.end())-emission.begin();
            trace<<"{\"sec\":"<<timestamps[f].sec<<",\"nsec\":"<<timestamps[f].nsec<<",\"local\":"<<best<<",\"hmm\":"<<chordpath[f]<<",\"ties\":[";
            bool first=true;
            for(int c=0;c<nChord;++c)if(emission[c]==emission[best]){if(!first)trace<<",";trace<<c;first=false;}
            trace<<"],\"salience\":[";
            for(int c=0;c<nChord;++c){if(c)trace<<",";trace<<traceSaliences[f][c];}
            trace<<"],\"emission\":[";
            for(int c=0;c<nChord;++c){if(c)trace<<",";trace<<emission[c];}
            trace<<"]}";
        }
        trace<<"]}\n";
        trace.close();
        if(!trace) throw std::runtime_error("Trace write failed");
    }
'''


def patch(source):
    replacements = [
        ('#include <algorithm>', '#include <algorithm>\n#include <iomanip>\n#include <stdexcept>'),
        ('vector<vector<double> > chordogram;', 'vector<vector<double> > chordogram;\n    vector<vector<double> > traceSaliences;'),
        ('vector<double> currentChordSalience;', 'vector<double> currentChordSalience;\n        vector<double> traceCurrent;'),
        ('tempchordvalue = pow(1.3, tempchordvalue);', 'traceCurrent.push_back(tempchordvalue);\n            tempchordvalue = pow(1.3, tempchordvalue);'),
        ('chordogram.push_back(currentChordSalience);', 'chordogram.push_back(currentChordSalience);\n        traceSaliences.push_back(traceCurrent);'),
        ('vector<int> chordpath = ViterbiPath(init, trans, chordogram, delta, &scale);',
         'vector<int> chordpath = ViterbiPath(init, trans, chordogram, delta, &scale);\n'+TRACE),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("Observation patch not unique")
        source = source.replace(before, after)
    return source


def run(root):
    root=root.resolve(); out=root/'output/evaluation/chord-decoder-trace-2026-11-05'
    plan_path=root/'docs/evaluation/chord-decoder-trace-plan-2026-11-05.json'
    plan=json.loads(plan_path.read_text()); plan_hash=sha(plan_path)
    def checked(entry):
        p=root/entry['path']
        if sha(p)!=entry['sha256']:raise ValueError('Frozen input changed')
        return p
    inputs=json.loads(checked(plan['input_plan']).read_text())
    prep=json.loads(checked(plan['preparation']).read_text())
    deadline=dt.datetime.fromisoformat(plan['deadline_utc'].replace('Z','+00:00'))
    def budget():
        remaining=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()
        if remaining<=0:raise TimeoutError('Original 90 minute deadline reached')
        return min(300,remaining)
    build=out/'plugin'; build.mkdir(exist_ok=False)
    original=Path(prep['builds']['baseline']['library']).parent
    for name,digest in prep['builds']['baseline']['source_sha256'].items():
        if sha(original/name)!=digest:raise ValueError('Source changed')
        dest=build/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original/name,dest)
    before=(build/'Chordino.cpp').read_text();after=patch(before);(build/'Chordino.cpp').write_text(after)
    (out/'observation.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/Chordino.cpp',tofile='b/Chordino.cpp')))
    cmd=inputs['build']['command']
    with (out/'build.log').open('x')as log:subprocess.run(cmd,cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=budget())
    library=build/'nnls-chroma.so'
    write(out/'before-inference.json',{'plan_sha256':plan_hash,'runner_sha256':sha(__file__),'library_sha256':sha(library),'patch_sha256':sha(out/'observation.patch'),'preparation_sha256':sha(checked(plan['preparation']))})
    env=dict(os.environ);env['VAMP_PATH']=str(build);env['PYTHONPATH']='/home/jonas/.cache/guitarscribe-chordino-diagnostic/python'
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='2'
    results=[]
    for case in inputs['inputs']:
        rid=case['recording_id'];audio=prep['audio'][rid]
        for key in ('audio','annotation','estimate','raw_cache'):checked(case[key])
        if sha(audio['path'])!=audio['sha256']:raise ValueError('Normalized audio changed')
        trace=out/(rid+'-trace.json');env['GUITARSCRIBE_TRACE_PATH']=str(trace)
        config={'audio':audio['path'],'audio_sha256':audio['sha256'],'duration_seconds':audio['duration_seconds'],'library':str(library),'library_sha256':sha(library),'output':str(out/(rid+'-events.json'))}
        cp=out/(rid+'-config.json');write(cp,config)
        with (out/(rid+'-run.log')).open('x')as log:
            subprocess.run([sys.executable,str(Path(__file__).with_name('run_chord_bass_ablation.py')),'worker',str(cp)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=budget())
        result=json.loads(Path(config['output']).read_text());raw=historical_events(result['raw_events'],audio['duration_seconds'],case['historical_decoder'])
        baseline=root/'output/evaluation/chord-bass-ablation-2026-11-05/run-v2'
        cached=[ChordEvent.model_validate(e)for e in json.loads((baseline/(rid+'-baseline-historical-raw.json')).read_text())]
        gates={'historical_raw':parity(cached,raw,1e-9),'projected':parity(projected_events(cached,case),projected_events(raw,case),1e-9)}
        write(out/(rid+'-parity.json'),gates)
        if not all(g['passed']for g in gates.values()):raise ValueError('Observation changed events: '+rid)
        if not trace.is_file():raise ValueError('Missing trace')
        results.append({'recording_id':rid,'gates':gates,'trace_sha256':sha(trace),'events_sha256':sha(Path(config['output']))})
        print(rid,'unchanged',flush=True)
    if sha(plan_path)!=plan_hash:raise ValueError('Plan changed')
    write(out/'run-result.json',{'sources':results,'inferences':len(results),'product_changed':False,'plan_sha256':plan_hash})


if __name__=='__main__':
    try:run(Path(sys.argv[1]))
    except Exception as exc:
        print('STOP:',type(exc).__name__,str(exc),file=sys.stderr)
        raise
