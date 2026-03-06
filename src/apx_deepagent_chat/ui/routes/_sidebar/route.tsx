import SidebarLayout from "@/components/apx/sidebar-layout";
import { createFileRoute, Link, useLocation, useNavigate } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { MessageSquare, PenSquare, User } from "lucide-react";
import { useEffect, useState } from "react";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_sidebar")({
  component: () => <Layout />,
});

type ChatSummary = {
  id: string;
  title: string;
  createdAt: string;
};

const STORAGE_KEY_VOLUME = "apx_volume_path";
const STORAGE_KEY_USER = "apx_user_id";

function getOrCreateUserId(): string {
  let id = localStorage.getItem(STORAGE_KEY_USER);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY_USER, id);
  }
  return id;
}

function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | undefined>();

  const volumePath = localStorage.getItem(STORAGE_KEY_VOLUME) ?? "";
  const userId = getOrCreateUserId();

  const fetchChats = () => {
    if (!volumePath || !userId) return;
    fetch(
      `/api/chat-history?user_id=${encodeURIComponent(userId)}&limit=30`,
      {
        headers: volumePath ? { "x-uc-volume-path": volumePath } : {},
      }
    )
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.chats)) {
          setChats(data.chats);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [volumePath]);

  const handleNewChat = () => {
    const newId = crypto.randomUUID();
    setActiveThreadId(newId);
    navigate({ to: "/chat" });
  };

  const navItems = [
    {
      to: "/profile",
      label: "Profile",
      icon: <User size={16} />,
      match: (path: string) => path === "/profile",
    },
    {
      to: "/chat",
      label: "Chat",
      icon: <MessageSquare size={16} />,
      match: (path: string) => path === "/chat",
    },
  ];

  return (
    <SidebarLayout>
      {/* ナビゲーション */}
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            {navItems.map((item) => (
              <SidebarMenuItem key={item.to}>
                <Link
                  to={item.to}
                  className={cn(
                    "flex items-center gap-2 p-2 rounded-lg",
                    item.match(location.pathname)
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  )}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      {/* チャット履歴 */}
      {location.pathname === "/chat" && (
        <SidebarGroup>
          <SidebarGroupLabel className="flex items-center justify-between pr-1">
            <span>会話履歴</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5"
              title="新しいチャット"
              onClick={handleNewChat}
            >
              <PenSquare size={13} />
            </Button>
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {chats.map((chat) => (
                <SidebarMenuItem key={chat.id}>
                  <button
                    className={cn(
                      "w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm truncate",
                      activeThreadId === chat.id
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    )}
                    onClick={() => {
                      setActiveThreadId(chat.id);
                      navigate({ to: "/chat" });
                    }}
                  >
                    <MessageSquare size={13} className="shrink-0" />
                    <span className="truncate">{chat.title}</span>
                  </button>
                </SidebarMenuItem>
              ))}
              {chats.length === 0 && volumePath && (
                <p className="px-2 py-2 text-xs text-muted-foreground">
                  会話履歴がありません
                </p>
              )}
              {!volumePath && (
                <p className="px-2 py-2 text-xs text-muted-foreground">
                  Volume Path を設定すると履歴が表示されます
                </p>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      )}
    </SidebarLayout>
  );
}
