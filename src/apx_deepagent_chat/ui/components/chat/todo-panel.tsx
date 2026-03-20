import {
  Queue,
  QueueItem,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
  QueueSection,
  QueueSectionContent,
  QueueSectionLabel,
  QueueSectionTrigger,
} from "@/components/ai-elements/queue";
import { ScrollArea } from "@/components/ui/scroll-area";

// ─── Types ────────────────────────────────────────────────────────────────────

export type AgentTodoItem = {
  id: string;
  content: string;
  status?: "pending" | "in_progress" | "completed";
};

export type AgentTodosGroup = {
  agentId: string;
  agentType: string;
  todos: AgentTodoItem[];
};

// ─── TodoPanel ────────────────────────────────────────────────────────────────

type TodoPanelProps = {
  groups: AgentTodosGroup[];
};

export function TodoPanel({ groups }: TodoPanelProps) {
  const totalCount = groups.reduce((sum, g) => sum + g.todos.length, 0);

  return (
    <ScrollArea className="h-full">
      <div className="p-3 space-y-3">
        <div className="flex items-center gap-2 px-1">
          <span className="text-sm font-semibold text-foreground">Tasks</span>
          <span className="text-xs text-muted-foreground bg-muted rounded-full px-1.5 py-0.5">
            {totalCount}
          </span>
        </div>

        {groups.map((group) => (
          <Queue key={group.agentId}>
            <QueueSection defaultOpen={true}>
              <QueueSectionTrigger>
                <QueueSectionLabel
                  label={group.agentType}
                  count={group.todos.length}
                />
              </QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList className="mt-1">
                  {group.todos.map((todo) => {
                    const completed = todo.status === "completed";
                    return (
                      <QueueItem key={todo.id}>
                        <div className="flex items-start gap-2">
                          <QueueItemIndicator completed={completed} />
                          <QueueItemContent completed={completed}>
                            {todo.content}
                          </QueueItemContent>
                        </div>
                      </QueueItem>
                    );
                  })}
                </QueueList>
              </QueueSectionContent>
            </QueueSection>
          </Queue>
        ))}
      </div>
    </ScrollArea>
  );
}
