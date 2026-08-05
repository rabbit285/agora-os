import Link from "next/link";

import { Button } from "@/components/ui/button";

export function FinalCTA() {
  return (
    <section className="border-t border-[var(--border-default)] bg-[var(--gray-900)]">
      <div className="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6 lg:px-8">
        <h2 className="text-[var(--text-3xl)] font-semibold tracking-tight text-white">
          Bring your compliance, security, sales, and operations into one intelligent workspace.
        </h2>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/signup">Start free</Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="border-[var(--gray-700)] bg-transparent text-white hover:bg-[var(--gray-800)]"
          >
            <Link href="/contact">Book a demo</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
