type ChordDiagramProps = {
  frets: Array<number | null>;
  baseFret: number;
  label: string;
};

const STRING_X = [18, 34, 50, 66, 82, 98];
const FRET_Y = [28, 43, 58, 73, 88];

export function ChordDiagram({ frets, baseFret, label }: ChordDiagramProps) {
  return (
    <svg className="chord-diagram" viewBox="0 0 116 104" role="img" aria-label={`${label} chord diagram`}>
      {STRING_X.map((x) => <line key={`string-${x}`} x1={x} y1="18" x2={x} y2="92" />)}
      {FRET_Y.map((y) => <line key={`fret-${y}`} x1="18" y1={y} x2="98" y2={y} />)}
      {frets.map((fret, index) => {
        const x = STRING_X[index];
        if (fret === null) return <text key={`mute-${x}`} x={x} y="13" textAnchor="middle">×</text>;
        if (fret === 0) return <text key={`open-${x}`} x={x} y="13" textAnchor="middle">○</text>;
        const relativeFret = fret - baseFret;
        if (relativeFret < 0 || relativeFret > 4) return null;
        return <circle key={`finger-${x}`} cx={x} cy={35 + relativeFret * 15} r="5" />;
      })}
      {baseFret > 1 ? <text x="2" y="39" className="chord-diagram-position">{baseFret}</text> : null}
    </svg>
  );
}
