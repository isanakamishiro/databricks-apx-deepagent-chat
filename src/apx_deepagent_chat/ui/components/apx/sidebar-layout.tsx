import { Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import SidebarUserFooter from "@/components/apx/sidebar-user-footer";
import { ModeToggle } from "@/components/apx/mode-toggle";
import Logo from "@/components/apx/logo";

interface SidebarLayoutProps {
  children?: ReactNode;
  defaultOpen?: boolean;
  onLogoClick?: () => void;
}

// Cookieからサイドバーの初期状態を読み込むヘルパー
function getSidebarDefaultOpen(): boolean {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("sidebar_state="));
  if (match) return match.split("=")[1] === "true";
  return true; // Cookie未設定時はデフォルトで開く
}

function SidebarLayout({ children, defaultOpen = getSidebarDefaultOpen(), onLogoClick }: SidebarLayoutProps) {
  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <Sidebar>
        <SidebarHeader>
          <div className="px-2 py-2">
            <Logo to="" onClick={onLogoClick} />
          </div>
        </SidebarHeader>
        <SidebarContent>{children}</SidebarContent>
        <SidebarFooter>
          <SidebarUserFooter />
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="flex flex-col h-screen">
        <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-sm border-b flex h-16 shrink-0 items-center gap-2 px-4">
          <SidebarTrigger className="-ml-1 cursor-pointer" />
          <div className="flex-1" />
          <ModeToggle />
        </header>
        <div className="flex flex-1 min-h-0 overflow-hidden">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
export default SidebarLayout;
