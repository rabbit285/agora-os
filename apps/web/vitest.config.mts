import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    exclude: ["node_modules/**", ".next/**", "e2e/**"],
    // Vitest defaults to one worker per core. Each of these files boots a
    // jsdom document and a React tree, which is heavy enough that a full
    // fan-out leaves every worker fighting for CPU — and since Testing
    // Library's findBy*/waitFor budgets are wall-clock, starvation surfaces
    // as "element not found" rather than as slowness. That made a handful
    // of files fail only in full runs while passing alone. Halving the
    // fan-out keeps real parallelism but leaves each worker enough CPU to
    // meet those budgets; combined with the raised asyncUtilTimeout in
    // vitest.setup.ts it takes the suite from intermittently red to
    // repeatably green across consecutive full runs. This does cost wall
    // time (roughly 45s -> 70-100s on an 8-core machine) — a deliberate
    // trade of some speed for a suite whose result means something.
    maxWorkers: "50%",
    // Vitest's own per-test budget, raised alongside the Testing Library
    // one in vitest.setup.ts. Leaving it at the 5s default made that
    // setting largely pointless: a findBy* given 5s to resolve inside a
    // test that is killed at 5s can never actually use its budget, so
    // contended runs still failed. Both now have real headroom, and
    // neither costs a passing test anything.
    testTimeout: 20000,
    hookTimeout: 20000,
  },
});
