import SidebarLayout from "@/components/apx/sidebar-layout";
import { createFileRoute, useNavigate, useRouterState } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { Loader2, MessageSquare, PenSquare, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
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
  const navigate = useNavigate();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const volumePath = localStorage.getItem(STORAGE_KEY_VOLUME) ?? "";
  const userId = getOrCreateUserId();

  // 現在のルートパスからthreadIdを取得
  const routerState = useRouterState();
  const currentMatch = routerState.matches.at(-1);
  const activeThreadId = (currentMatch?.params as { threadId?: string })?.threadId;

  const fetchChats = () => {
    if (!userId) return;
    setIsLoading(true);
    fetch(
      `/api/chat-history?user_id=${encodeURIComponent(userId)}&limit=50`,
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
      .catch(() => {})
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchChats();
    window.addEventListener("chat-list-updated", fetchChats);
    return () => window.removeEventListener("chat-list-updated", fetchChats);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, volumePath]);

  const handleNewChat = () => {
    navigate({ to: "/chat" });
  };

  const handleDeleteChat = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await fetch(
        `/api/chat-history/${chatId}?user_id=${encodeURIComponent(userId)}`,
        {
          method: "DELETE",
          headers: volumePath ? { "x-uc-volume-path": volumePath } : {},
        }
      );
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      // 削除したチャットが現在表示中なら初期画面へ
      if (chatId === activeThreadId) {
        navigate({ to: "/chat" });
      }
    } catch {
      // ignore
    }
  };

  return (
    <SidebarLayout defaultOpen={false} onLogoClick={handleNewChat}>
      <SidebarGroup>
        <SidebarGroupLabel className="flex items-center justify-between pr-1">
          <span>会話履歴</span>
          <div className="flex items-center gap-1">
            {isLoading && chats.length > 0 && (
              <Loader2 size={12} className="animate-spin text-muted-foreground" />
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5"
              title="新しいチャット"
              onClick={handleNewChat}
            >
              <PenSquare size={13} />
            </Button>
          </div>
        </SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {isLoading && chats.length === 0 ? (
              <div className="space-y-1 px-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : !isLoading && chats.length === 0 ? (
              <p className="px-2 py-2 text-xs text-muted-foreground">
                {volumePath
                  ? "会話履歴がありません"
                  : "Volume Path を設定すると履歴が表示されます"}
              </p>
            ) : (
              chats.map((chat) => (
                <SidebarMenuItem key={chat.id}>
                  <div
                    className={cn(
                      "group w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm cursor-pointer",
                      activeThreadId === chat.id
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    )}
                    onClick={() =>
                      navigate({
                        to: "/chat/$threadId",
                        params: { threadId: chat.id },
                        search: { q: undefined },
                      })
                    }
                  >
                    <MessageSquare size={13} className="shrink-0" />
                    <span className="truncate flex-1">{chat.title}</span>
                    <button
                      className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                      onClick={(e) => handleDeleteChat(chat.id, e)}
                      title="削除"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </SidebarMenuItem>
              ))
            )}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarLayout>
  );
}
