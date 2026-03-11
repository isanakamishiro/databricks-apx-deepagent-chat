import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";

// ─── Types ────────────────────────────────────────────────────────────────────

export type ToolCallState =
  | "input-streaming"
  | "input-available"
  | "output-available"
  | "output-error";

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
    pending: { label: "準備中", className: "bg-muted text-muted-foreground" },
    running: { label: "実行中", className: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300" },
    done: { label: "完了", className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300" },
    error: { label: "エラー", className: "bg-destructive/10 text-destructive" },
  }[state];

  return (
    <span className={cn("text-xs px-1.5 py-0.5 rounded-full font-medium", config.className)}>
      {config.label}
    </span>
  );
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
    <div
      className={cn(
        "rounded-lg border transition-colors",
        isRunning
          ? "border-purple-400 dark:border-purple-600"
          : "border-muted"
      )}
    >
      {/* Header */}
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 rounded-lg transition-colors"
      >
        <span className="text-muted-foreground shrink-0">
          {isExpanded ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronRight className="size-3.5" />
          )}
        </span>
        <span className="text-sm">🤖</span>
        <span className="text-sm font-medium flex-1">{agentLabel}</span>
        <StateBadge state={block.state} />
      </button>

      {/* Body */}
      {isExpanded && block.toolCalls.length > 0 && (
        <div className="px-3 pb-3 space-y-2">
          {block.toolCalls.map((tc, i) => {
            let parsedArgs: Record<string, unknown> = {};
            try {
              parsedArgs = JSON.parse(tc.arguments || "{}");
            } catch {
              parsedArgs = { raw: tc.arguments };
            }
            return (
              <Tool key={i}>
                <ToolHeader title={tc.name} type="tool-call" state={tc.state} />
                <ToolContent>
                  <ToolInput input={parsedArgs} />
                  {tc.result !== undefined && (
                    <ToolOutput
                      output={tc.result}
                      errorText={
                        tc.state === "output-error" ? tc.result : undefined
                      }
                    />
                  )}
                </ToolContent>
              </Tool>
            );
          })}
        </div>
      )}

      {/* Empty running state */}
      {isExpanded && block.toolCalls.length === 0 && isRunning && (
        <div className="px-3 pb-3">
          <div className="text-xs text-muted-foreground animate-pulse">
            サブエージェントを起動中...
          </div>
        </div>
      )}
    </div>
  );
}
