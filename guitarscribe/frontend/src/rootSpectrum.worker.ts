import {makeSpectrum} from './rootSpectrum';
self.onmessage = (event: MessageEvent<{channels: Float32Array[]; rate: number}>) => {
  try {
    const result = makeSpectrum(event.data.channels, event.data.rate, progress => self.postMessage({progress}));
    self.postMessage({result}, {transfer: [result.values.buffer]});
  } catch (error) { self.postMessage({error: error instanceof Error ? error.message : '頻譜計算失敗'}); }
};
