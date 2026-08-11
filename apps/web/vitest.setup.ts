import { configure } from "@testing-library/dom";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Testing Library's default 1000ms budget for findBy*/waitFor is a
// wall-clock timeout, and Vitest runs test files across parallel workers
// that compete for CPU. A file that passes comfortably on its own can lose
// that race when the whole suite runs — which showed up here as a handful
// of files failing only in full runs and passing every time in isolation.
// Nothing was actually slow; the budget was just tight enough to be
// load-sensitive. Raising it does not slow passing tests down (these
// helpers resolve as soon as the assertion succeeds, they don't wait out
// the timeout), it only stops a busy machine from being reported as a
// product failure.
configure({ asyncUtilTimeout: 5000 });

// Vitest doesn't auto-run RTL's cleanup the way Jest's global environment
// does — without this, DOM from one test leaks into the next within the
// same file (duplicate elements, stale event handlers).
afterEach(() => {
  cleanup();
});
