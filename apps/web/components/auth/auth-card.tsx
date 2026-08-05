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
  return (
    <Card className="w-full">
      <CardHeader className="text-center">
        <h1 className="text-xl font-semibold text-[var(--fg-default)]">{title}</h1>
        {description && <p className="text-sm text-[var(--fg-muted)]">{description}</p>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
