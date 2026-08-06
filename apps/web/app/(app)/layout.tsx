import type { Metadata } from "next";

import { AppSidebar } from "@/components/app-sidebar";
import { AuthGuard } from "@/components/auth-guard";
import { SidebarProvider } from "@/components/sidebar-context";
import { TopNavigation } from "@/components/top-navigation";

// A blanket noindex for the entire authenticated app — every real page
// under this route group is a private, per-organization workspace, not
// public content, and none of them override this metadata individually.
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

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
