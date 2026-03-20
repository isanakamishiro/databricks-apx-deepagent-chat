import { Outlet } from "@tanstack/react-router";
import { type ReactNode, useRef, useState, useEffect } from "react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import SidebarUserFooter from "@/components/apx/sidebar-user-footer";
import { ModeToggle } from "@/components/apx/mode-toggle";
import Logo from "@/components/apx/logo";

const SIDEBAR_MIN_WIDTH = 160;
const SIDEBAR_MAX_WIDTH = 480;
const SIDEBAR_WIDTH_STORAGE_KEY = "apx_sidebar_width";
const DRAG_THRESHOLD = 4;

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

type ResizableSidebarRailProps = {
  sidebarWidth: number;
  onWidthChange: (width: number) => void;
};

function ResizableSidebarRail({ sidebarWidth, onWidthChange }: ResizableSidebarRailProps) {
  const { toggleSidebar } = useSidebar();
  const [isDragging, setIsDragging] = useState(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);
  const hasMovedRef = useRef(false);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = sidebarWidth;
    hasMovedRef.current = false;
    setIsDragging(true);
  };

  const handleClick = () => {
    if (!hasMovedRef.current) toggleSidebar();
  };

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - dragStartXRef.current;
      if (Math.abs(delta) > DRAG_THRESHOLD) hasMovedRef.current = true;
      const newWidth = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, dragStartWidthRef.current + delta));
      onWidthChange(newWidth);
    };
    const handleMouseUp = () => {
      if (hasMovedRef.current) {
        localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
      }
      setIsDragging(false);
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, sidebarWidth, onWidthChange]);

  useEffect(() => {
    document.body.style.cursor = isDragging ? "col-resize" : "";
    document.body.style.userSelect = isDragging ? "none" : "";
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  return <SidebarRail onMouseDown={handleMouseDown} onClick={handleClick} />;
}

function SidebarLayout({ children, defaultOpen = getSidebarDefaultOpen(), onLogoClick }: SidebarLayoutProps) {
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const stored = localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    return stored
      ? Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Number(stored)))
      : 256;
  });

  return (
    <SidebarProvider
      defaultOpen={defaultOpen}
      style={{ "--sidebar-width": `${sidebarWidth}px` } as React.CSSProperties}
    >
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
        <ResizableSidebarRail sidebarWidth={sidebarWidth} onWidthChange={setSidebarWidth} />
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
