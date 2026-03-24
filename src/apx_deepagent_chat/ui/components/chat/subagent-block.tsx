import { useEffect, useState } from "react";
import { Bot, CheckCircleIcon, CheckIcon, ChevronDownIcon, CircleIcon, ClockIcon, Loader2Icon, XCircleIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Task,
  TaskContent,
  TaskItem,
  TaskTrigger,
} from "@/components/ai-elements/task";

// ─── Types ────────────────────────────────────────────────────────────────────

export type ToolCallState =
  | "input-streaming"
  | "input-available"
  | "output-available"
  | "output-error"
  | "output-denied";

export type SubAgentToolCall = {
  callId: string;
  name: string;
  arguments: string;
  result?: string;
  state: ToolCallState;
};

export type SubAgentBlockData = {
  callId: string;
  agentType: string;
  toolCalls: SubAgentToolCall[];
  result?: string;
  state: "pending" | "running" | "done" | "error";
};

// ─── State Badge ──────────────────────────────────────────────────────────────

function StateBadge({ state }: { state: SubAgentBlockData["state"] }) {
  const config = {
    pending: { label: "Pending", icon: <CircleIcon className="size-4" /> },
    running: { label: "Running", icon: <ClockIcon className="size-4 animate-pulse" /> },
    done: { label: "Completed", icon: <CheckCircleIcon className="size-4 text-green-600" /> },
    error: { label: "Error", icon: <XCircleIcon className="size-4 text-red-600" /> },
  }[state];

  return (
    <Badge className="gap-1.5 rounded-full text-xs" variant="secondary">
      {config.icon}
      {config.label}
    </Badge>
  );
}

// ─── ToolCall State Icon ───────────────────────────────────────────────────────

function ToolCallStateIcon({ state }: { state: ToolCallState }) {
  switch (state) {
    case "input-streaming":
      return <CircleIcon className="size-3 shrink-0 text-muted-foreground" />;
    case "input-available":
      return <Loader2Icon className="size-3 shrink-0 animate-spin text-purple-500" />;
    case "output-available":
      return <CheckIcon className="size-3 shrink-0 text-green-500" />;
    case "output-error":
      return <XCircleIcon className="size-3 shrink-0 text-destructive" />;
    case "output-denied":
      return <XCircleIcon className="size-3 shrink-0 text-muted-foreground" />;
  }
}

// ─── SubAgentBlock ────────────────────────────────────────────────────────────

type SubAgentBlockProps = {
  block: SubAgentBlockData;
};

export function SubAgentBlock({ block }: SubAgentBlockProps) {
  const [isExpanded, setIsExpanded] = useState(
    block.state === "running" || block.state === "pending"
  );

  // 実行中は自動展開、完了後は自動折りたたみ
  useEffect(() => {
    if (block.state === "running" || block.state === "pending") {
      setIsExpanded(true);
    } else if (block.state === "done" || block.state === "error") {
      setIsExpanded(false);
    }
  }, [block.state]);

  const agentLabel = block.agentType || "agent";
  const isRunning = block.state === "running";

  return (
    <Task
      className={cn(
        "rounded-lg border transition-colors",
        isRunning
          ? "border-purple-400 dark:border-purple-600"
          : "border-muted"
      )}
      open={isExpanded}
      onOpenChange={setIsExpanded}
    >
      <TaskTrigger title={agentLabel}>
        <button
          type="button"
          className="flex w-full cursor-pointer items-center justify-between gap-4 text-sm hover:bg-muted/50 rounded-lg px-3 py-2 transition-colors"
        >
          <div className="flex min-w-0 items-center gap-2">
            <Bot className="size-4 shrink-0 text-muted-foreground" />
            <span className="font-medium">{agentLabel}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StateBadge state={block.state} />
            <ChevronDownIcon className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
          </div>
        </button>
      </TaskTrigger>

      <TaskContent>
        {block.toolCalls.map((tc, i) => {
          let firstParam: string | undefined;
          try {
            const args = JSON.parse(tc.arguments || "{}");
            const firstValue = Object.values(args)[0];
            if (firstValue !== undefined) {
              const raw = typeof firstValue === "string" ? firstValue : JSON.stringify(firstValue);
              firstParam = raw.length > 100 ? raw.slice(0, 100) + "..." : raw;
            }
          } catch {
            // ignore
          }
          return (
            <TaskItem key={i} className="flex items-center gap-2">
              <ToolCallStateIcon state={tc.state} />
              <span className="font-mono text-xs shrink-0">{tc.name}</span>
              {firstParam !== undefined && (
                <span className="text-xs text-muted-foreground truncate">{firstParam}</span>
              )}
            </TaskItem>
          );
        })}

        {block.toolCalls.length === 0 && isRunning && (
          <TaskItem className="animate-pulse text-muted-foreground text-xs">
            サブエージェントを起動中...
          </TaskItem>
        )}
      </TaskContent>
    </Task>
  );
}
