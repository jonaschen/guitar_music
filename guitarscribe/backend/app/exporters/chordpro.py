from collections import defaultdict

from ..models.score import SongScore


class ChordProExporter:
    """Exports the time-aligned chord chart without reproducing lyrics."""

    def export(self, score: SongScore) -> str:
        lines = [
            f"{{title: {score.song.title}}}",
            f"{{key: {score.key_context.target.key} {score.key_context.target.mode}}}",
            f"{{tempo: {round(score.analysis.bpm)}}}",
            f"{{time: {score.analysis.time_signature}}}",
        ]
        if score.analysis.capo:
            lines.append(f"{{capo: {score.analysis.capo}}}")
        lines.append("")

        by_measure: dict[int, list[str]] = defaultdict(list)
        for chord in score.chords:
            measure = next((beat.measure for beat in reversed(score.beats) if beat.time <= chord.start), 1)
            by_measure[measure].append(f"[{chord.symbol}]")

        lines.extend(" ".join(chords) for _, chords in sorted(by_measure.items()))
        return "\n".join(lines).rstrip() + "\n"
