export type TransportClock = Readonly<{
  now: () => number;
  seek?: (seconds: number) => void;
}>;

/**
 * The media element remains the sole clock for original-audio playback.
 * UI animation frames only sample this value; they do not advance time.
 */
export function createMediaTransportClock(media: Pick<HTMLMediaElement, "currentTime">): TransportClock {
  return {
    now: () => Math.max(0, media.currentTime),
    seek: (seconds) => { media.currentTime = Math.max(0, seconds); },
  };
}

/**
 * Convert an AudioContext time anchor into score seconds for synthesized
 * playback. This is deliberately independent of React render timing.
 */
export function createAudioContextTransportClock(
  context: Pick<AudioContext, "currentTime">,
  anchor: { contextStart: number; scoreStart: number },
  playbackRate: number,
): TransportClock {
  return {
    now: () => Math.max(anchor.scoreStart, anchor.scoreStart + (context.currentTime - anchor.contextStart) * playbackRate),
  };
}
