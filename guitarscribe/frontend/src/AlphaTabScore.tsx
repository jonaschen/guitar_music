import { useEffect, useRef, useState } from "react";
import * as alphaTab from "@coderline/alphatab";
import type { SongScore } from "./types";

const API_BASE = "http://localhost:8000";

/** Render the existing MusicXML export without enabling alphaTab's own player. */
function AlphaTabScore({ score }: { score: SongScore }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<alphaTab.AlphaTabApi | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hostRef.current) return;
    const api = new alphaTab.AlphaTabApi(hostRef.current, {
      display: { layoutMode: "page", barsPerRow: 4, scale: 0.8 },
      player: { enablePlayer: false },
    });
    apiRef.current = api;
    const onError = (event: { message?: string }) => setError(event.message ?? "Could not render the MusicXML score.");
    api.error.on(onError);
    return () => {
      api.error.off(onError);
      api.destroy();
      apiRef.current = null;
    };
  }, []);

  useEffect(() => {
    const api = apiRef.current;
    if (!api) return;
    let cancelled = false;
    setError("");
    void fetch(API_BASE + "/scores/musicxml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(score),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.arrayBuffer();
      })
      .then((musicXml) => {
        if (!cancelled) api.load(musicXml);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Could not load the MusicXML score.");
      });
    return () => { cancelled = true; };
  }, [score]);

  return <section className="alphatab-panel">
    <div><h3>Notation &amp; Tab</h3><p>Rendered from the current MusicXML export. Playback remains controlled by GuitarScribe.</p></div>
    {error ? <p className="alphatab-error">Notation preview unavailable: {error}</p> : null}
    <div className="alphatab-host" ref={hostRef} aria-label="Standard notation and guitar tab preview" />
  </section>;
}

export default AlphaTabScore;
