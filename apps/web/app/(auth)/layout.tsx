import { Logo } from "@/components/logo";

export default function AuthRouteGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-app)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo size="lg" href="/" />
        </div>
        {children}
      </div>
    </div>
  );
}
