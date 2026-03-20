import { useEffect, useRef, useState } from "react";
import { FileText, CheckSquare, ChevronDown, ChevronUp } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GeneratedFiles } from "@/components/chat/generated-files";
import { TodoPanel, type AgentTodosGroup } from "@/components/chat/todo-panel";

const MIN_HEIGHT = 80;
const MAX_HEIGHT = 400;
const DRAG_HANDLE_HEIGHT = 6;
const TAB_HEADER_HEIGHT = 37;
const HEADER_HEIGHT = DRAG_HANDLE_HEIGHT + TAB_HEADER_HEIGHT;

type InfoPanelProps = {
  files: string[];
  volumePath: string;
  todoGroups: AgentTodosGroup[];
};

export function InfoPanel({ files, volumePath, todoGroups }: InfoPanelProps) {
  const [height, setHeight] = useState(200);
  const [isVisible, setIsVisible] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<"files" | "tasks">("files");
  const [isDragging, setIsDragging] = useState(false);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(200);
  const prevFilesLengthRef = useRef(0);
  const prevTodosCountRef = useRef(0);

  const totalTodosCount = todoGroups.reduce((s, g) => s + g.todos.length, 0);

  // コンテンツが追加されたら自動表示、なくなったら自動非表示
  useEffect(() => {
    const filesAdded = files.length > prevFilesLengthRef.current;
    const todosAdded = totalTodosCount > prevTodosCountRef.current;
    prevFilesLengthRef.current = files.length;
    prevTodosCountRef.current = totalTodosCount;

    if (filesAdded || todosAdded) {
      setIsVisible(true);
      setIsCollapsed(false);
      if (filesAdded) setActiveTab("files");
      else setActiveTab("tasks");
    }
    if (files.length === 0 && totalTodosCount === 0) {
      setIsVisible(false);
    }
  }, [files.length, totalTodosCount]);

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
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "files" | "tasks")} className="flex flex-col h-full">
        <div className="flex items-center px-3 border-b" style={{ height: `${TAB_HEADER_HEIGHT}px` }}>
          <TabsList className="h-7 bg-transparent p-0 gap-1">
            <TabsTrigger
              value="files"
              className="text-xs h-6 px-2 data-[state=active]:bg-muted data-[state=active]:shadow-none"
            >
              <FileText className="size-3 mr-1" />
              生成されたファイル
              {files.length > 0 && (
                <Badge variant="secondary" className="ml-1 text-xs h-4 px-1 min-w-4">{files.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger
              value="tasks"
              className="text-xs h-6 px-2 data-[state=active]:bg-muted data-[state=active]:shadow-none"
            >
              <CheckSquare className="size-3 mr-1" />
              Tasks
              {totalTodosCount > 0 && (
                <Badge variant="secondary" className="ml-1 text-xs h-4 px-1 min-w-4">{totalTodosCount}</Badge>
              )}
            </TabsTrigger>
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
          </div>
        )}
      </Tabs>
    </div>
  );
}
