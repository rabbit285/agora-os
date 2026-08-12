import { SectionHeader } from "@/components/marketing/section-header";
import { Badge } from "@/components/ui/badge";

const CUSTOMER_TYPES = [
  "B2B SaaS companies",
  "Software businesses",
  "Consulting firms",
  "Fintech companies",
  "Healthcare technology businesses",
  "Professional services teams",
  "Growing SMEs",
];

export function CustomerTypeSection() {
  return (
    <section className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
      <SectionHeader
        eyebrow="Who it's for"
        title="Built for growing, regulated businesses"
        description="Agora Origin fits any organization coordinating compliance, security, sales, and support in one place — typically 20–200 employees."
      />
      <div className="mt-8 flex flex-wrap justify-center gap-2">
        {CUSTOMER_TYPES.map((type) => (
          <Badge key={type} variant="secondary" className="px-3 py-1.5 text-sm">
            {type}
          </Badge>
        ))}
      </div>
    </section>
  );
}
