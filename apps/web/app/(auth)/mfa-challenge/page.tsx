import type { Metadata } from "next";

import { MfaChallengeClient } from "./mfa-challenge-client";

export const metadata: Metadata = {
  title: "Two-factor verification — Veyntra",
  robots: { index: false, follow: false },
};

export default function MfaChallengePage() {
  return <MfaChallengeClient />;
}
