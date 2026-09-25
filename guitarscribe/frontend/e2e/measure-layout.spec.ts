import { expect, test } from "@playwright/test";
import { measureLayout } from "../src/measureLayout";

const beats = [0, 0.5, 1.2, 1.8, 2.4].map((time, i) => ({ time, beat: i % 4 + 1, measure: i < 4 ? 1 : 2, confidence: 1 }));

test("beat widths represent 3:1, 2:2 and 2:1:1 even with uneven beat times", () => {
  const layout = measureLayout(beats, 0, 2.4, 100);
  expect(layout.ticks.map((tick) => tick.fraction)).toEqual([0, 0.25, 0.5, 0.75]);
  expect(layout.fraction(1.8)).toBe(0.75);
  expect(layout.length(0, 1.8)).toBe("3 拍");
  expect(layout.length(1.8, 2.4)).toBe("1 拍");
  expect(layout.length(0, 1.2)).toBe("2 拍");
  expect(layout.length(1.2, 2.4)).toBe("2 拍");
  expect(layout.length(1.2, 1.8)).toBe("1 拍");
  expect(layout.fraction(0.25)).toBe(0.125);
});

test("pickup, partial last measure and missing grid do not invent a full four-beat bar", () => {
  const pickup = measureLayout([{ time: 0, beat: 4, measure: 1, confidence: 1 }, { time: 0.5, beat: 1, measure: 2, confidence: 1 }], 0, 0.5, 120);
  expect(pickup.ticks).toEqual([{ beat: 4, fraction: 0 }]);
  expect(pickup.length(0, 0.5)).toBe("1 拍");
  const partial = measureLayout(beats.slice(0, 3), 0, 1.55, 100);
  expect(partial.length(1.2, 1.55)).toBe("0.5 拍");
  const missing = measureLayout([], 0, 2, 120);
  expect(missing.ticks).toEqual([]);
  expect(missing.fraction(1.5)).toBe(0.75);
  expect(missing.length(0, 1.5)).toBe("1.5s");
});
