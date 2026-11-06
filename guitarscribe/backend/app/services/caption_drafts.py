"""On-demand subtitle previews for an existing job; no audio, automatic translation or alignment."""
import asyncio
import html
import json
import math
import time
from urllib.parse import urlparse,parse_qs
import httpx
from ..sources.youtube import YouTubeAudioDownloader,validate_youtube_url


class CaptionUnavailable(ValueError):pass


def caption_tracks(metadata):
    tracks=[]
    for kind,key in [('manual','subtitles'),('automatic','automatic_captions')]:
        collection=metadata.get(key)
        if not isinstance(collection,dict):continue
        for language,formats in collection.items():
            if not isinstance(language,str) or not isinstance(formats,list):continue
            selected=None
            for f in formats:
                if not isinstance(f,dict) or f.get('ext')!='json3':continue
                url=f.get('url','')
                if not isinstance(url,str):continue
                try:parsed=urlparse(url);query=parse_qs(parsed.query)
                except ValueError:continue
                if parsed.scheme!='https' or parsed.hostname not in ('youtube.com','www.youtube.com') or parsed.path!='/api/timedtext' or query.get('tlang'):continue
                # Only original ASR tracks, never hundreds of generated translations.
                original=metadata.get('language')
                if kind=='automatic':
                    actual=query.get('lang',[''])[0]
                    if actual.split('-')[0]!=language.split('-')[0]:continue
                    if original and str(original).split('-')[0]!=language.split('-')[0]:continue
                selected=f;break
            if selected:
                tracks.append(dict(id=kind+':'+language,language=language,kind=kind,name=str(selected.get('name') or language),url=selected['url']))
    return tracks


def parse_json3(data,offset,duration):
    if not all(math.isfinite(v) for v in (offset,duration)) or offset<0 or duration<=0:raise CaptionUnavailable('歌曲時間範圍無效。')
    if not isinstance(data,dict) or not isinstance(data.get('events'),list):raise CaptionUnavailable('字幕格式無法讀取，可改貼上歌詞。')
    lines=[];characters=0
    for event in data['events']:
        if not isinstance(event,dict):continue
        segments=event.get('segs',[])
        if not isinstance(segments,list):raise CaptionUnavailable('字幕文字格式無法讀取，可改貼上歌詞。')
        raw=''.join(s.get('utf8','') for s in segments if isinstance(s,dict) and isinstance(s.get('utf8'),str))
        text=html.unescape(raw).strip()
        if not text:continue
        start=event.get('tStartMs');length=event.get('dDurationMs')
        if not isinstance(start,(int,float)) or isinstance(start,bool) or not isinstance(length,(int,float)) or isinstance(length,bool):
            start=end=None
        else:
            try:start=start/1000-offset;end=start+length/1000
            except OverflowError:raise CaptionUnavailable('字幕時間格式無法讀取，可改貼上歌詞。')
            if not math.isfinite(start+end) or end<=start:continue
            if end<=0 or start>=duration:continue
            start=max(0.,start);end=min(duration,end)
        # Keep repeated choruses; missing times stay unknown, never inferred.
        for part in text.splitlines():
            part=part.strip()
            if not part:continue
            characters+=len(part)
            if len(part)>2000 or len(lines)>=400 or characters>120000:raise CaptionUnavailable('字幕內容過長，請改貼上所需段落。')
            lines.append(dict(lyric=part,start=start,end=end))
    return lines


class CaptionDraftService:
    def __init__(self,binary='yt-dlp',js_runtime='node'):
        self.downloader=YouTubeAudioDownloader(binary=binary,js_runtime=js_runtime)
        self.cache={};self.lock=asyncio.Lock()

    async def _metadata(self,url):
        validate_youtube_url(url)
        command=[self.downloader.binary,'--no-config','--no-playlist','--skip-download','--dump-single-json','--no-warnings',
                 '--socket-timeout','10','--retries','0','--extractor-retries','0','--js-runtimes',self.downloader.js_runtime,'--',url]
        try:process=await asyncio.create_subprocess_exec(*command,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        except OSError as exc:raise CaptionUnavailable('目前無法取得影片字幕，可貼上歌詞或匯入LRC。') from exc
        async def bounded(stream,limit):
            chunks=[];size=0
            while chunk:=await stream.read(65536):
                size+=len(chunk)
                if size>limit:raise CaptionUnavailable('影片字幕資料過大，請改貼上歌詞。')
                chunks.append(chunk)
            return b''.join(chunks)
        tasks=[asyncio.create_task(bounded(process.stdout,4*1024*1024)),asyncio.create_task(bounded(process.stderr,128*1024))]
        try:
            output,_=await asyncio.wait_for(asyncio.gather(*tasks),45)
            await asyncio.wait_for(process.wait(),5)
            if process.returncode:raise CaptionUnavailable('目前無法取得影片字幕，可貼上歌詞或匯入LRC。')
            parsed=json.loads(output)
            if not isinstance(parsed,dict):raise CaptionUnavailable('影片字幕資料格式無效，可改貼上歌詞。')
            return parsed
        except (TimeoutError,ValueError) as exc:
            if isinstance(exc,CaptionUnavailable):raise
            raise CaptionUnavailable('影片字幕取得失敗，可稍後重試或貼上歌詞。') from exc
        finally:
            # Reap on API cancellation too, without unbounded communicate().
            for task in tasks:task.cancel()
            if process.returncode is None:
                try:process.kill()
                except ProcessLookupError:pass
            await asyncio.gather(*tasks,return_exceptions=True)
            async def drain(stream):
                while await stream.read(65536):pass
            # A killed child can still have buffered pipe data; drain it before wait.
            await asyncio.wait_for(asyncio.gather(drain(process.stdout),drain(process.stderr),process.wait()),5)

    async def tracks(self,job):
        if not job.source_url:raise CaptionUnavailable('這個來源沒有影片字幕，可貼上歌詞或匯入LRC。')
        key=(job.id,job.source_url)
        async with self.lock:
            cached=self.cache.get(key)
            if not cached or time.monotonic()-cached['time']>1800:
                metadata=await self._metadata(job.source_url)
                cached=dict(time=time.monotonic(),tracks=caption_tracks(metadata));self.cache[key]=cached
                # Bound per-process metadata; never keep signed URLs in client responses.
                if len(self.cache)>32:self.cache.pop(next(iter(self.cache)))
        return cached['tracks']

    async def preview(self,job,track_id):
        tracks=await self.tracks(job);track=next((t for t in tracks if t['id']==track_id),None)
        if track is None:raise CaptionUnavailable('這個字幕選項不存在，請重新取得字幕列表。')
        async def fetch_payload():
            async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
                async with client.stream('GET',track['url']) as response:
                    if response.status_code!=200:raise CaptionUnavailable('字幕暫時無法下載，可稍後重試或貼上歌詞。')
                    chunks=[];size=0
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>2*1024*1024:raise CaptionUnavailable('字幕內容過長，請改貼上所需段落。')
                        chunks.append(chunk)
            parsed=json.loads(b''.join(chunks))
            if not isinstance(parsed,dict):raise CaptionUnavailable('字幕格式無法讀取，可改貼上歌詞。')
            return parsed
        try:payload=await asyncio.wait_for(fetch_payload(),25)
        except (httpx.HTTPError,ValueError,TimeoutError) as exc:
            if isinstance(exc,CaptionUnavailable):raise
            raise CaptionUnavailable('字幕預覽取得失敗，可貼上歌詞或匯入LRC。') from exc
        lines=parse_json3(payload,job.score.song.source_start_seconds,job.score.song.duration_seconds)
        return dict(job_id=job.id,track={k:v for k,v in track.items() if k!='url'},lines=lines,
                    message='字幕不一定是歌詞，可能有辨識錯誤；請先預覽再加入，既有簡譜不會被覆寫。')
