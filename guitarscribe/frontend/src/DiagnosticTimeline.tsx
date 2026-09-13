import { useEffect, useRef, useState } from "react";
import type { SongScore } from "./types";

type Props = {
  audioUrl: string;
  score: SongScore;
  playbackTime: number;
  onSeek: (time: number) => void;
};

const WAVEFORM_BUCKETS = 900;

export function DiagnosticTimeline({ audioUrl, score, playbackTime, onSeek }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [waveform, setWaveform] = useState<number[]>([]);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const response = await fetch(audioUrl);
        if (!response.ok) return;
        const context = new AudioContext();
        try {
          const decoded = await context.decodeAudioData(await response.arrayBuffer());
          const channel = decoded.getChannelData(0);
          const bucketSize = Math.max(1, Math.floor(channel.length / WAVEFORM_BUCKETS));
          const peaks = Array.from({ length: WAVEFORM_BUCKETS }, (_, bucket) => {
            const start = bucket * bucketSize;
            const end = Math.min(channel.length, start + bucketSize);
            let peak = 0;
            for (let index = start; index < end; index += 1) peak = Math.max(peak, Math.abs(channel[index]));
            return peak;
          });
          if (!disposed) setWaveform(peaks);
        } finally {
          await context.close();
        }
      } catch {
        if (!disposed) setWaveform([]);
      }
    };
    void load();
    return () => { disposed = true; };
  }, [audioUrl]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(bounds.width * ratio));
      canvas.height = Math.max(1, Math.round(bounds.height * ratio));
      const context = canvas.getContext("2d");
      if (!context) return;
      context.scale(ratio, ratio);
      const width = bounds.width;
      const height = bounds.height;
      const duration = Math.max(score.song.duration_seconds, 0.01);
      context.clearRect(0, 0, width, height);
      context.fillStyle = "rgba(255,255,255,0.025)";
      context.fillRect(0, 0, width, height);

      context.strokeStyle = "rgba(230,235,245,0.32)";
      context.lineWidth = 1;
      waveform.forEach((peak, index) => {
        const x = index / Math.max(1, waveform.length - 1) * width;
        const amplitude = peak * height * 0.42;
        context.beginPath();
        context.moveTo(x, height / 2 - amplitude);
        context.lineTo(x, height / 2 + amplitude);
        context.stroke();
      });

      score.beats.forEach((beat) => {
        const x = beat.time / duration * width;
        context.strokeStyle = beat.beat === 1 ? "rgba(255,190,105,0.8)" : "rgba(139,211,181,0.28)";
        context.lineWidth = beat.beat === 1 ? 1.8 : 1;
        context.beginPath();
        context.moveTo(x, 0);
        context.lineTo(x, height);
        context.stroke();
        if (beat.beat === 1) {
          context.fillStyle = "rgba(255,205,135,0.95)";
          context.font = "10px system-ui";
          context.fillText(`B${beat.measure}`, Math.min(width - 24, x + 3), 12);
        }
      });

      score.chords.forEach((chord) => {
        const x = chord.start / duration * width;
        context.fillStyle = "rgba(126,170,255,0.95)";
        context.fillRect(x, height - 22, 2, 22);
      });
      score.melody.forEach((note) => {
        const start = note.start / duration * width;
        const end = note.end / duration * width;
        const pitchY = height - 27 - Math.max(0, Math.min(30, (note.midi - 48) * 0.7));
        context.strokeStyle = "rgba(245,139,172,0.9)";
        context.lineWidth = 2;
        context.beginPath();
        context.moveTo(start, pitchY);
        context.lineTo(Math.max(start + 1, end), pitchY);
        context.stroke();
      });

      const playheadX = playbackTime / duration * width;
      context.fillStyle = "rgba(255,255,255,0.95)";
      context.fillRect(playheadX, 0, 2, height);
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [playbackTime, score, waveform]);

  const seekFromPointer = (clientX: number) => {
    const bounds = canvasRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const fraction = Math.max(0, Math.min(1, (clientX - bounds.left) / Math.max(1, bounds.width)));
    onSeek(fraction * score.song.duration_seconds);
  };

  return <div className="diagnostic-timeline-panel">
    <div className="diagnostic-timeline-heading"><strong>Diagnostic timeline</strong><span>Click to seek and compare the same instant across audio tracks.</span></div>
    <canvas
      ref={canvasRef}
      className="diagnostic-timeline"
      role="slider"
      tabIndex={0}
      aria-label="Diagnostic waveform and analysis overlay"
      aria-valuemin={0}
      aria-valuemax={score.song.duration_seconds}
      aria-valuenow={playbackTime}
      onClick={(event) => seekFromPointer(event.clientX)}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") onSeek(Math.max(0, playbackTime - 1));
        if (event.key === "ArrowRight") onSeek(Math.min(score.song.duration_seconds, playbackTime + 1));
      }}
    />
    <div className="diagnostic-legend"><span className="legend-downbeat">Downbeat / bar</span><span className="legend-beat">Beat</span><span className="legend-chord">Chord boundary</span><span className="legend-melody">Final melody</span><span className="legend-playhead">Playhead</span></div>
  </div>;
}
