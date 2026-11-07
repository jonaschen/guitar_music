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

/** Same source-buffer clock used by review playback, including rate and loop wrap. */
export function createReviewTransportClock(context:Pick<AudioContext,'currentTime'>,anchor:{contextStart:number;scoreStart:number;end:number;loop:readonly[number,number]|null},rate:number):TransportClock{
  const firstEnd=anchor.contextStart+(anchor.end-anchor.scoreStart)/rate;
  const loopDuration=anchor.loop?(anchor.loop[1]-anchor.loop[0])/rate:0;
  return {now:()=>anchor.loop&&loopDuration>0&&context.currentTime>=firstEnd
    ?anchor.loop[0]+((context.currentTime-firstEnd)%loopDuration)*rate
    :Math.min(anchor.end,anchor.scoreStart+Math.max(0,context.currentTime-anchor.contextStart)*rate)};
}
