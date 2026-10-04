import type { SongScore } from "./types";

export type BarAnchor = { measure: number; time: number };

export function retimeBars(score: SongScore, anchors: BarAnchor[], even = false): SongScore {
  if (anchors.length < 3 || anchors.length > 9) throw Error("請選取 2–8 個完整小節。");
  const count = Number(score.analysis.time_signature.split("/")[0]);
  if (!Number.isInteger(count) || count < 1) throw Error("無效拍號。");
  const original = anchors.map(a => score.beats.find(b => b.measure === a.measure && b.beat === 1)?.time);
  if (original.some(t => t === undefined)) throw Error("需要完整的小節起點與下一小節邊界；不支援裁切邊界或尾端缺拍。");
  const old = original as number[];
  if (anchors[0].time !== old[0] || anchors.at(-1)!.time !== old.at(-1)) throw Error("段落首尾固定，避免改到其他段落。");
  for (let i = 0; i < anchors.length; i++) {
    if (!Number.isFinite(anchors[i].time) || anchors[i].time < 0 || anchors[i].time > score.song.duration_seconds ||
        (i && (anchors[i].measure !== anchors[i - 1].measure + 1 || old[i] <= old[i - 1] || anchors[i].time <= anchors[i - 1].time))) {
      throw Error("小節必須連續、時間有限且依序遞增。");
    }
    if (i === anchors.length - 1) continue;
    const pulses = score.beats.filter(b => b.measure === anchors[i].measure);
    if (pulses.length !== count || pulses.some((b, j) => b.beat !== j + 1 || b.time < old[i] || b.time >= old[i + 1])) {
      throw Error("所選段落有缺拍／不完整小節，請勿直接重排。");
    }
  }
  const beats = score.beats.map(beat => {
    const i = anchors.findIndex(a => a.measure === beat.measure);
    if (i < 0 || i === anchors.length - 1) return beat;
    const fraction = even ? (beat.beat - 1) / count : (beat.time - old[i]) / (old[i + 1] - old[i]);
    return { ...beat, time: anchors[i].time + fraction * (anchors[i + 1].time - anchors[i].time) };
  });
  if (beats.some((b, i) => !Number.isFinite(b.time) || (i > 0 && b.time - beats[i - 1].time < .02 - 1e-9))) {
    throw Error("校正後拍點過近或順序異常，未套用。");
  }
  return { ...score, beats, provenance: { ...score.provenance, tempo_map_version: "manual-bar-anchors-v1",
    parameters: { ...score.provenance.parameters, timing_origin: "user",
      last_bar_timing_edit: JSON.stringify({ before: anchors.map((a, i) => ({ ...a, time: old[i] })), after: anchors, even }) } } };
}
