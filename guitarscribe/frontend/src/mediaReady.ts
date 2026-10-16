/** Wait for the current media element, cleaning up on cancellation or failure. */
export function waitForMediaMetadata(audio: HTMLMediaElement, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new DOMException("Cancelled", "AbortError"));
  if (audio.readyState >= 1) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      audio.removeEventListener("loadedmetadata", ready);
      audio.removeEventListener("error", failed);
      signal.removeEventListener("abort", cancelled);
    };
    const ready = () => { cleanup(); resolve(); };
    const failed = () => { cleanup(); reject(new Error("來源音訊無法載入，請確認來源仍可用或改聽工作譜。")); };
    const cancelled = () => { cleanup(); reject(new DOMException("Cancelled", "AbortError")); };
    const timer = window.setTimeout(() => { cleanup(); reject(new Error("來源音訊載入逾時，請稍後重試。")); }, 15000);
    audio.addEventListener("loadedmetadata", ready);
    audio.addEventListener("error", failed);
    signal.addEventListener("abort", cancelled, { once: true });
    if (audio.error) failed();
  });
}
