import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// Browser APIs used by the accessible portalled primitives, absent in jsdom.
if (!window.PointerEvent)
  window.PointerEvent = MouseEvent as typeof PointerEvent;
HTMLElement.prototype.hasPointerCapture ??= () => false;
HTMLElement.prototype.setPointerCapture ??= () => {};
HTMLElement.prototype.releasePointerCapture ??= () => {};
HTMLElement.prototype.scrollIntoView ??= () => {};

// Floating UI probes browser top-layer selectors. jsdom's selector engine
// recursively evaluates :fullscreen; jsdom cannot enter these native states.
const nativeMatches = Element.prototype.matches;
Element.prototype.matches = function (selector: string) {
  if ([":fullscreen", ":modal", ":popover-open"].includes(selector))
    return false;
  return nativeMatches.call(this, selector);
};
