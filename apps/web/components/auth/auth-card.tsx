import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function AuthCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  // Padding and title scale up with the card. Card's own p-5 is tuned for
  // the dense dashboard surfaces it was built for; left alone on a 512px
  // auth card it reads as a small card that has been stretched rather
  // than a larger one. Overridden here rather than in ui/card.tsx, which
  // 60+ authenticated pages share.
  return (
    <Card className="w-full">
      <CardHeader className="text-center sm:p-7 sm:pb-4">
        <h1 className="text-xl font-semibold text-[var(--fg-default)] sm:text-2xl">{title}</h1>
        {description && (
          <p className="text-sm text-[var(--fg-muted)] sm:text-base">{description}</p>
        )}
      </CardHeader>
      <CardContent className="sm:p-7 sm:pt-0">{children}</CardContent>
    </Card>
  );
}
