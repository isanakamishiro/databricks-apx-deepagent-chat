import SidebarLayout from "@/components/apx/sidebar-layout";
import { createFileRoute, useNavigate, useRouterState } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { ExternalLink, Loader2, MessageSquare, PenSquare, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

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

function buildCatalogExplorerUrl(workspaceUrl: string, volumePath: string): string | null {
  const parts = volumePath.split('/').filter(Boolean);
  // parts = ["Volumes", "catalog", "schema", "volume"]
  if (parts.length < 4 || parts[0] !== 'Volumes') return null;
  const [, catalog, schema, volume] = parts;
  const host = workspaceUrl.replace(/\/$/, '');
  return `${host}/explore/data/volumes/${catalog}/${schema}/${volume}`;
}

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
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [workspaceUrl, setWorkspaceUrl] = useState("");

  const userId = getOrCreateUserId();
  const volumePath = localStorage.getItem(STORAGE_KEY_VOLUME) ?? "";

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((data) => {
        if (data.workspace_url) setWorkspaceUrl(data.workspace_url);
      })
      .catch(() => {});
  }, []);

  const catalogExplorerUrl = workspaceUrl && volumePath
    ? buildCatalogExplorerUrl(workspaceUrl, volumePath)
    : null;

  // 現在のルートパスからthreadIdを取得
  const routerState = useRouterState();
  const currentMatch = routerState.matches.at(-1);
  const activeThreadId = (currentMatch?.params as { threadId?: string })?.threadId;

  const fetchChats = () => {
    if (!userId) return;
    const currentVolumePath = localStorage.getItem(STORAGE_KEY_VOLUME) ?? "";
    setIsLoading(true);
    fetch(
      `/api/chat-history?user_id=${encodeURIComponent(userId)}&limit=50`,
      {
        headers: currentVolumePath ? { "x-uc-volume-path": currentVolumePath } : {},
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

  const fetchChatsRef = useRef(fetchChats);
  useEffect(() => {
    fetchChatsRef.current = fetchChats;
  });

  useEffect(() => {
    fetchChats();
    const handler = () => fetchChatsRef.current();
    window.addEventListener("chat-list-updated", handler);
    return () => window.removeEventListener("chat-list-updated", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const handleNewChat = () => {
    navigate({ to: "/chat" });
  };

  const executeDelete = async (chatId: string) => {
    // 楽観的UI: 即座にリストから非表示
    const prevChats = chats;
    setChats((prev) => prev.filter((c) => c.id !== chatId));
    // アクティブなチャットを削除した場合のみホームへ戻る
    // 別のチャットを削除した場合は現在の画面をそのまま維持
    if (chatId === activeThreadId) {
      navigate({ to: "/chat" });
    }
    try {
      await fetch(
        `/api/chat-history/${chatId}?user_id=${encodeURIComponent(userId)}`,
        {
          method: "DELETE",
          headers: volumePath ? { "x-uc-volume-path": volumePath } : {},
        }
      );
    } catch {
      // API失敗時: リストをロールバック
      setChats(prevChats);
    }
  };

  const handleDeleteChat = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (e.shiftKey) {
      // Shift+クリック: ダイアログスキップ
      executeDelete(chatId);
    } else {
      // 通常クリック: 確認ダイアログ表示
      setPendingDeleteId(chatId);
    }
  };

  return (
    <>
    <SidebarLayout onLogoClick={handleNewChat}>
      <SidebarGroup>
        <SidebarGroupLabel className="flex items-center justify-between pr-1">
          <span>会話履歴</span>
          <div className="flex items-center gap-1">
            {isLoading && chats.length > 0 && (
              <Loader2 size={12} className="animate-spin text-muted-foreground" />
            )}
            {catalogExplorerUrl && (
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5"
                title="カタログエクスプローラで開く"
                onClick={() => window.open(catalogExplorerUrl, '_blank')}
              >
                <ExternalLink size={13} />
              </Button>
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
                      "group/chat-item w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm cursor-pointer",
                      activeThreadId === chat.id
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    )}
                    onClick={() =>
                      navigate({
                        to: "/chat/$threadId",
                        params: { threadId: chat.id },
                        search: { q: undefined, files: undefined },
                      })
                    }
                  >
                    <MessageSquare size={13} className="shrink-0" />
                    <span className="truncate flex-1">{chat.title}</span>
                    <button
                      className="shrink-0 opacity-0 group-hover/chat-item:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
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

    <AlertDialog
      open={pendingDeleteId !== null}
      onOpenChange={(open) => {
        if (!open) setPendingDeleteId(null);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>チャットを削除しますか？</AlertDialogTitle>
          <AlertDialogDescription>
            この操作は取り消せません。チャット履歴が完全に削除されます。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>キャンセル</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => {
              if (pendingDeleteId) {
                executeDelete(pendingDeleteId);
                setPendingDeleteId(null);
              }
            }}
          >
            削除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}
