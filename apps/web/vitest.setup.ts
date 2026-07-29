import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Vitest doesn't auto-run RTL's cleanup the way Jest's global environment
// does — without this, DOM from one test leaks into the next within the
// same file (duplicate elements, stale event handlers).
afterEach(() => {
  cleanup();
});
