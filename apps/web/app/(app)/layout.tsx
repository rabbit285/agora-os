import { AppSidebar } from "@/components/app-sidebar";
import { AuthGuard } from "@/components/auth-guard";
import { SidebarProvider } from "@/components/sidebar-context";
import { TopNavigation } from "@/components/top-navigation";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <SidebarProvider>
        <div className="flex h-screen">
          <AppSidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <TopNavigation />
            <main id="main-content" className="flex-1 overflow-y-auto bg-[var(--bg-app)] p-4 sm:p-6">
              <div className="mx-auto max-w-[var(--content-max-width)]">{children}</div>
            </main>
          </div>
        </div>
      </SidebarProvider>
    </AuthGuard>
  );
}
