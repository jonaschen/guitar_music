from collections import defaultdict

from ..models.score import SongScore


class ChordProExporter:
    """Export chords and only the lyrics explicitly supplied in the score."""

    def export(self, score: SongScore) -> str:
        lines = [
            f"{{title: {self._directive_value(score.song.title)}}}",
            f"{{key: {score.key_context.target.key} {score.key_context.target.mode}}}",
            f"{{tempo: {round(score.analysis.bpm)}}}",
            f"{{time: {score.analysis.time_signature}}}",
        ]
        if score.analysis.capo:
            lines.append(f"{{capo: {score.analysis.capo}}}")
        lines.append("")

        if score.lyrics and score.lyrics.lines:
            lines.append(
                "{comment: Lyrics · language: "
                f"{self._directive_value(score.lyrics.language)} · source: "
                f"{self._directive_value(score.lyrics.source)} · timing: "
                f"{self._directive_value(score.lyrics.timing_level)}}}"
            )
            for lyric in sorted(score.lyrics.lines, key=lambda line: line.order):
                if score.lyrics.timing_level == "word" and lyric.words:
                    lines.append(self._word_timed_line(score, lyric))
                    continue
                chords = self._chords_between(score, lyric.start, lyric.end)
                if chords:
                    lines.append(" ".join(f"[{chord.symbol}]" for chord in chords))
                lines.append(self._escape_lyric(lyric.text))
        else:
            by_measure: dict[int, list[str]] = defaultdict(list)
            for chord in score.chords:
                measure = next((beat.measure for beat in reversed(score.beats) if beat.time <= chord.start), 1)
                by_measure[measure].append(f"[{chord.symbol}]")
            lines.extend(" ".join(chords) for _, chords in sorted(by_measure.items()))
        return "\n".join(lines).rstrip() + "\n"

    def _chords_between(self, score: SongScore, start: float | None, end: float | None):
        if start is None:
            return []
        line_end = end if end is not None else start + 0.001
        return [chord for chord in score.chords if chord.start < line_end and chord.end > start]

    def _word_timed_line(self, score: SongScore, lyric) -> str:
        pieces: list[str] = []
        emitted: set[str] = set()
        for word in lyric.words:
            prefix = ""
            for chord in self._chords_between(score, word.start, word.end):
                if chord.id not in emitted:
                    prefix += f"[{chord.symbol}]"
                    emitted.add(chord.id)
            pieces.append(prefix + self._escape_lyric(word.text))
        return " ".join(pieces)

    @staticmethod
    def _escape_lyric(text: str) -> str:
        return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("{", "\\{").replace("}", "\\}")

    @staticmethod
    def _directive_value(text: str) -> str:
        return text.replace("\n", " ").replace("\r", " ").replace("}", ")").strip()
