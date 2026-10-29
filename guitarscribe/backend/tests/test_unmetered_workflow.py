"""A rejected meter can yield an honest, editable chord-only score."""
import json
import pytest
from app.core.pipeline import AnalysisPipeline
from app.models.analysis import ChordAnalysis, ChordEvent, BeatInfo
from app.models.audio import AudioAsset, NormalizedAudio, SourceRequest, SourceType
from app.models.score import SongScore, SongInfo, AnalysisSummary
from app.analyzers.beats.timing_diagnostics import BeatProjectionError
from app.postprocess.chords import ChordPostProcessor
from app.exporters.midi import compile_playback_manifest, export_midi
from app.exporters.musicxml import export_musicxml
from app.exporters.chordpro import ChordProExporter
from app.services.chord_inspection import chord_inspection_events
from app.services.chord_entry_performance import build_entry_performance


def timeline():
    return SongScore(song=SongInfo(duration_seconds=8),
        analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature=''),
        chords=[ChordEvent(id='a',start=.137,end=2.412,symbol='C'),
                ChordEvent(id='b',start=3.517,end=8,symbol='G')])


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,supported,error_kind', [('off',True,'projection'),('vocal',True,'projection'),('off',False,'projection'),('off',True,'runtime')])
async def test_only_typed_timing_rejection_and_audio_only_chords_can_fall_back(tmp_path,mode,supported,error_kind):
    evidence={'beats':[0,.5,1,1.5,2], 'downbeats':[0,1.5], 'rejection_reason':'inconsistent meter'}
    class Source:
        async def fetch(self,request):return AudioAsset(path=tmp_path/'input.wav',source_type=SourceType.LOCAL)
    class Preprocessor:
        async def normalize(self,asset):return NormalizedAudio(path=asset.path,duration_seconds=8)
    class Beats:
        async def analyze(self,audio):
            if error_kind=='runtime':raise RuntimeError('engine crashed')
            raise BeatProjectionError('inconsistent meter',evidence)
    class Chords:
        supports_unmetered=supported
        async def analyze(self,audio,beats):
            assert beats is None and mode=='off' and supported
            return ChordAnalysis(chords=timeline().chords,engine='cached')
    class Forbidden:
        def __getattr__(self,name):pytest.fail(f'Unmetered path invoked {name}')
    frozen=Forbidden()
    pipeline=AnalysisPipeline(Preprocessor(),Beats(),Chords(),frozen,ChordPostProcessor(),frozen,frozen,frozen,Source())
    run=pipeline.run(SourceRequest(source_type=SourceType.LOCAL,path=tmp_path/'input.wav'),
                     {'melody_mode':mode,'chord_complexity':'full','_artifact_directory':str(tmp_path)})
    if mode!='off' or not supported or error_kind=='runtime':
        with pytest.raises(RuntimeError if error_kind=='runtime' else BeatProjectionError):await run
        assert not (tmp_path/'chord-analysis.json').exists()
        return
    score=await run
    assert score.analysis.timing_status=='unmetered'
    assert not score.beats and not score.melody and not score.rhythm.display
    assert score.analysis.bpm==0 and score.analysis.time_signature==''
    assert [(c.symbol,c.start,c.end) for c in score.chords]==[(c.symbol,c.start,c.end) for c in timeline().chords]
    assert json.loads((tmp_path/'timing-rejection.json').read_text())==evidence
    assert not (tmp_path/'timing-analysis.json').exists()
    assert compile_playback_manifest(score).events==tuple(chord_inspection_events(timeline().chords,8)[0])


@pytest.mark.parametrize('field,value',[('bpm',120),('time_signature','4/4')])
def test_unmetered_cannot_smuggle_tempo_or_meter(field,value):
    data=timeline().model_dump();data['analysis'][field]=value
    with pytest.raises(ValueError,match='Unmetered'):SongScore.model_validate(data)


def test_unmetered_cannot_smuggle_beats():
    data=timeline().model_dump();data['beats']=[BeatInfo(time=0,beat=1,measure=1)]
    with pytest.raises(ValueError,match='Unmetered'):SongScore.model_validate(data)


def test_manifest_preserves_seconds_and_selected_capo_voicing():
    score=timeline();before=score.model_dump()
    manifest=compile_playback_manifest(score)
    assert manifest.events==tuple(chord_inspection_events(score.chords,8)[0])
    assert score.model_dump()==before
    assert all(e.track=='guitar' for e in manifest.events)
    assert manifest.bpm==0 and manifest.time_signature==''
    from app.services.playable_chords import with_default_voicings
    score=with_default_voicings(score)
    selected=score.chords[0].available_voicings[-1]
    score.chords[0].voicing_id=selected.id
    score.analysis.capo=score.guitar.capo=2
    assert compile_playback_manifest(score).events[0].pitches==tuple(t+f+2 for t,f in zip(score.guitar.tuning,selected.frets) if f is not None)
    score.chords=score.chords[1:]
    assert len(compile_playback_manifest(score).events)==1


def test_unmetered_export_is_timed_text_without_invented_notation():
    score=timeline()
    text=ChordProExporter().export(score)
    assert '{tempo:' not in text and '{time:' not in text
    assert '0.137–2.412 s' in text and '[C]' in text
    for export in [export_midi,export_musicxml]:
        with pytest.raises(ValueError,match='拍格'):export(score)
    with pytest.raises(ValueError,match='拍格'):build_entry_performance(score, 'sparse')
