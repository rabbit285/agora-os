import { AppSidebar } from "@/components/app-sidebar";
import { AuthGuard } from "@/components/auth-guard";
import { TopNavigation } from "@/components/top-navigation";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen">
        <AppSidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <TopNavigation />
          <main className="flex-1 overflow-y-auto bg-neutral-50 p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
