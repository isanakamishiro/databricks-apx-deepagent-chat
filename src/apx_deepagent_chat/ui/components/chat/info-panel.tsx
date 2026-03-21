import { useEffect, useRef, useState } from "react";
import { FileText, CheckSquare, Paperclip, ChevronDown, ChevronUp, Clock, X } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GeneratedFiles } from "@/components/chat/generated-files";
import { TodoPanel, type AgentTodosGroup } from "@/components/chat/todo-panel";
import { AttachmentPanel, type UploadedAttachment } from "@/components/chat/attachment-panel";

const MIN_HEIGHT = 80;
const MAX_HEIGHT = 400;
const DRAG_HANDLE_HEIGHT = 6;
const TAB_HEADER_HEIGHT = 37;
const HEADER_HEIGHT = DRAG_HANDLE_HEIGHT + TAB_HEADER_HEIGHT;

type InfoPanelProps = {
  files: string[];
  volumePath: string;
  todoGroups: AgentTodosGroup[];
  messageQueue: string[];
  onRemoveQueueItem: (index: number) => void;
  uploadedAttachments: UploadedAttachment[];
  onAttachmentRemove: (id: string) => void;
};

export function InfoPanel({ files, volumePath, todoGroups, messageQueue, onRemoveQueueItem, uploadedAttachments, onAttachmentRemove }: InfoPanelProps) {
  const [height, setHeight] = useState(200);
  const [isVisible, setIsVisible] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<"files" | "tasks" | "queue" | "attachments">("files");
  const [isDragging, setIsDragging] = useState(false);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(200);
  const prevFilesLengthRef = useRef(0);
  const prevTodosCountRef = useRef(0);
  const prevQueueLengthRef = useRef(0);
  const prevAttachmentsLengthRef = useRef(0);

  const totalTodosCount = todoGroups.reduce((s, g) => s + g.todos.length, 0);

  // コンテンツが追加されたら自動表示、なくなったら自動非表示
  useEffect(() => {
    const filesAdded = files.length > prevFilesLengthRef.current;
    const todosAdded = totalTodosCount > prevTodosCountRef.current;
    const queueAdded = messageQueue.length > prevQueueLengthRef.current;
    const attachmentsAdded = uploadedAttachments.length > prevAttachmentsLengthRef.current;
    prevFilesLengthRef.current = files.length;
    prevTodosCountRef.current = totalTodosCount;
    prevQueueLengthRef.current = messageQueue.length;
    prevAttachmentsLengthRef.current = uploadedAttachments.length;

    const somethingAdded = filesAdded || todosAdded || queueAdded || attachmentsAdded;

    if (somethingAdded) {
      // コンテンツが追加されたら表示してタブ切り替え
      setIsVisible(true);
      setIsCollapsed(false);
      if (queueAdded) setActiveTab("queue");
      else if (attachmentsAdded) setActiveTab("attachments");
      else if (filesAdded) setActiveTab("files");
      else setActiveTab("tasks");
    } else {
      // コンテンツが減った場合のみフォールバック処理
      if (files.length === 0 && totalTodosCount === 0 && messageQueue.length === 0 && uploadedAttachments.length === 0) {
        setIsVisible(false);
      }
      // アクティブなタブのコンテンツがなくなったら別タブへ切り替え
      const findFallbackTab = () => {
        if (files.length > 0) return "files" as const;
        if (totalTodosCount > 0) return "tasks" as const;
        if (uploadedAttachments.length > 0) return "attachments" as const;
        if (messageQueue.length > 0) return "queue" as const;
        return null;
      };
      if (activeTab === "queue" && messageQueue.length === 0) {
        const tab = findFallbackTab();
        if (tab) setActiveTab(tab);
      }
      if (activeTab === "files" && files.length === 0) {
        const tab = findFallbackTab();
        if (tab) setActiveTab(tab);
      }
      if (activeTab === "tasks" && totalTodosCount === 0) {
        const tab = findFallbackTab();
        if (tab) setActiveTab(tab);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files.length, totalTodosCount, messageQueue.length, uploadedAttachments.length]);

  // ドラッグリサイズ
  const handleDragMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    dragStartYRef.current = e.clientY;
    dragStartHeightRef.current = height;
    setIsDragging(true);
  };

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      const delta = dragStartYRef.current - e.clientY;
      const newHeight = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, dragStartHeightRef.current + delta));
      setHeight(newHeight);
    };
    const handleMouseUp = () => setIsDragging(false);
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);

  useEffect(() => {
    document.body.style.cursor = isDragging ? "row-resize" : "";
    document.body.style.userSelect = isDragging ? "none" : "";
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  if (!isVisible) return null;

  const panelHeight = isCollapsed ? TAB_HEADER_HEIGHT : height;
  const contentHeight = height - HEADER_HEIGHT;

  return (
    <div className="shrink-0 border-t bg-background" style={{ height: `${panelHeight}px` }}>
      {/* ドラッグハンドル：collapsed時は非表示 */}
      {!isCollapsed && (
        <div
          className="h-1.5 cursor-row-resize hover:bg-muted/50 transition-colors w-full"
          onMouseDown={handleDragMouseDown}
        />
      )}
      {/* タブUI */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "files" | "tasks" | "queue" | "attachments")} className="flex flex-col h-full">
        <div className="flex items-center px-3 border-b" style={{ height: `${TAB_HEADER_HEIGHT}px` }}>
          <TabsList className="h-7 bg-transparent p-0 gap-1">
            {files.length > 0 && (
              <TabsTrigger
                value="files"
                className="text-xs h-6 px-2 data-[state=active]:bg-muted data-[state=active]:shadow-none"
              >
                <FileText className="size-3 mr-1" />
                生成されたファイル
                <Badge variant="secondary" className="ml-1 text-xs h-4 px-1 min-w-4">{files.length}</Badge>
              </TabsTrigger>
            )}
            {totalTodosCount > 0 && (
              <TabsTrigger
                value="tasks"
                className="text-xs h-6 px-2 data-[state=active]:bg-muted data-[state=active]:shadow-none"
              >
                <CheckSquare className="size-3 mr-1" />
                Tasks
                <Badge variant="secondary" className="ml-1 text-xs h-4 px-1 min-w-4">{totalTodosCount}</Badge>
              </TabsTrigger>
            )}
            {messageQueue.length > 0 && (
              <TabsTrigger
                value="queue"
                className="text-xs h-6 px-2 data-[state=active]:bg-muted data-[state=active]:shadow-none"
              >
                <Clock className="size-3 mr-1" />
                待機中
                <Badge variant="secondary" className="ml-1 text-xs h-4 px-1 min-w-4">{messageQueue.length}</Badge>
              </TabsTrigger>
            )}
            {uploadedAttachments.length > 0 && (
              <TabsTrigger
                value="attachments"
                className="text-xs h-6 px-2 data-[state=active]:bg-muted data-[state=active]:shadow-none"
              >
                <Paperclip className="size-3 mr-1" />
                添付ファイル
                <Badge variant="secondary" className="ml-1 text-xs h-4 px-1 min-w-4">{uploadedAttachments.length}</Badge>
              </TabsTrigger>
            )}
          </TabsList>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto h-6 w-6"
            onClick={() => setIsCollapsed((v) => !v)}
            aria-label={isCollapsed ? "展開" : "折りたたむ"}
          >
            {isCollapsed ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </Button>
        </div>
        {/* コンテンツエリア：collapsed時は非表示 */}
        {!isCollapsed && (
          <div style={{ height: `${contentHeight}px`, overflow: "auto" }}>
            <TabsContent value="files" className="mt-0 p-3 h-full">
              {files.length === 0 ? (
                <p className="text-xs text-muted-foreground">ファイルはまだありません</p>
              ) : (
                <GeneratedFiles files={files} volumePath={volumePath} />
              )}
            </TabsContent>
            <TabsContent value="tasks" className="mt-0 h-full">
              <TodoPanel groups={todoGroups} />
            </TabsContent>
            <TabsContent value="attachments" className="mt-0 p-3 h-full">
              <AttachmentPanel
                attachments={uploadedAttachments}
                onRemove={onAttachmentRemove}
              />
            </TabsContent>
            <TabsContent value="queue" className="mt-0 p-3 h-full">
              {messageQueue.length === 0 ? (
                <p className="text-xs text-muted-foreground">待機中のメッセージはありません</p>
              ) : (
                <div className="space-y-2">
                  {messageQueue.map((item, index) => (
                    <div key={index} className="flex items-start gap-2 text-xs bg-muted/50 rounded px-2 py-1.5">
                      <span className="flex-1 text-muted-foreground truncate">
                        {item.slice(0, 50)}{item.length > 50 ? "…" : ""}
                      </span>
                      <button
                        onClick={() => onRemoveQueueItem(index)}
                        className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                        aria-label="削除"
                      >
                        <X className="size-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>
          </div>
        )}
      </Tabs>
    </div>
  );
}
