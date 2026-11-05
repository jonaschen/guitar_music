"""Duration-weighted local versus HMM observations; no causal acoustic claims."""
import math
from .chord_dictionary import DictionaryAvailability


def summarize(trace, intervals, start, end):
    availability=DictionaryAvailability(trace['dictionary'])
    frames=trace['frames']; totals={k:0.0 for k in ('both_correct','local_wrong_hmm_correct','local_correct_hmm_wrong','both_wrong')}
    covered=eligible=unavailable=tied=positive_harm=margin_sum=0.0
    examples=[]
    for i,frame in enumerate(frames):
        emission=frame['emission']; n=len(trace['dictionary'])
        if len(emission)!=n or len(frame['salience'])!=n or any(not math.isfinite(v)or v<0 for v in emission):raise ValueError('Invalid emission')
        if abs(sum(emission)-1)>1e-9:raise ValueError('Emission not normalized')
        maximum=max(emission); ties=[k for k,v in enumerate(emission)if v==maximum]
        if ties!=frame['ties'] or frame['local']!=ties[0] or not 0<=frame['hmm']<n:raise ValueError('Invalid selected/tied index')
        t=frame['sec']+frame['nsec']*1e-9
        z=frames[i+1]['sec']+frames[i+1]['nsec']*1e-9 if i+1<len(frames)else t
        if z<t:raise ValueError('Nonmonotonic frame timestamps')
        for interval in intervals:
            a,b=max(start,t,interval['start']),min(end,z,interval['end'])
            if b<=a:continue
            seconds=b-a;covered+=seconds
            match=availability.classify(interval['reference_label'])
            correct={e['index']for e in match['matches'].get('strict',[])}
            if not correct:unavailable+=seconds;continue
            eligible+=seconds;local=frame['local']in correct;hmm=frame['hmm']in correct
            key='both_correct' if local and hmm else 'local_wrong_hmm_correct' if hmm else 'local_correct_hmm_wrong' if local else 'both_wrong'
            totals[key]+=seconds
            if len(ties)>1:tied+=seconds
            margin=max(emission[k]for k in correct)-max(v for k,v in enumerate(emission)if k not in correct)
            margin_sum+=seconds*margin
            if local and not hmm and margin>1e-12:positive_harm+=seconds
            if key=='local_correct_hmm_wrong' and len(examples)<3:
                examples.append({'start':a,'end':b,'reference':interval['reference_label'],'local_index':frame['local'],'hmm_index':frame['hmm'],'margin':margin,'ties':ties})
    return {'duration_seconds':end-start,'covered_seconds':covered,'uncovered_seconds':max(0,end-start-covered),
            'eligible_seconds':eligible,'no_strict_candidate_seconds':unavailable,'four_way_seconds':totals,
            'eligible_tied_max_seconds_nonadditive':tied,'positive_margin_hmm_harm_seconds':positive_harm,
            'weighted_mean_emission_margin':margin_sum/eligible if eligible else None,'examples':examples,
            'frame_count':len(frames),'dictionary_entries':len(trace['dictionary'])}
