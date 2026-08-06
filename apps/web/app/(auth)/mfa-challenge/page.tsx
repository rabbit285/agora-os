import type { Metadata } from "next";

import { MfaChallengeClient } from "./mfa-challenge-client";

export const metadata: Metadata = {
  title: "Two-factor verification — Agora Origin",
  robots: { index: false, follow: false },
};

export default function MfaChallengePage() {
  return <MfaChallengeClient />;
}
