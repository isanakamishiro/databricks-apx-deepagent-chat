import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, ChevronDown, ChevronRight, Loader2, SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import { SettingsDialog } from "@/components/chat/settings-dialog";

export const Route = createFileRoute("/_sidebar/chat")({
  component: () => <Chat />,
});

// ストレージキー
const STORAGE_KEY_VOLUME = "apx_volume_path";
const STORAGE_KEY_MODEL = "apx_selected_model";

type SubagentBlock = {
  name: string;
  content: string;
};

type ToolCallBlock = {
  callId: string;
  name: string;
  arguments: string; // JSON文字列
  result?: string;   // function_call_output が来たら埋める
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  subagentBlocks?: SubagentBlock[];
  toolCallBlocks?: ToolCallBlock[];
  isError?: boolean;
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  model?: string;
  maxContextTokens?: number;
};


function SubagentSection({ block }: { block: SubagentBlock }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="my-1 rounded border border-border bg-muted/40 text-xs">
      <button
        className="flex w-full items-center gap-1 px-2 py-1 text-left text-muted-foreground hover:text-foreground"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span className="font-mono">{block.name}</span>
      </button>
      {expanded && (
        <div className="border-t border-border px-3 py-2 text-muted-foreground whitespace-pre-wrap">
          {block.content || "(no output)"}
        </div>
      )}
    </div>
  );
}

function ToolCallSection({
  block,
  isStreaming,
}: {
  block: ToolCallBlock;
  isStreaming?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const isDone = block.result !== undefined;
  let prettyArgs = block.arguments;
  try {
    prettyArgs = JSON.stringify(JSON.parse(block.arguments), null, 2);
  } catch {
    // そのまま表示
  }
  return (
    <div className="my-1 rounded border border-border bg-muted/40 text-xs">
      <button
        className="flex w-full items-center gap-1 px-2 py-1 text-left text-muted-foreground hover:text-foreground"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {isStreaming && !isDone ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <span className="text-green-600">✓</span>
        )}
        <span className="font-mono">🔧 {block.name}</span>
      </button>
      {expanded && (
        <div className="border-t border-border px-3 py-2 space-y-2">
          <div>
            <div className="text-muted-foreground font-semibold mb-1">引数</div>
            <pre className="whitespace-pre-wrap text-muted-foreground">{prettyArgs}</pre>
          </div>
          {isDone && (
            <div>
              <div className="text-muted-foreground font-semibold mb-1">結果</div>
              <pre className="whitespace-pre-wrap text-muted-foreground">{block.result || "(no output)"}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ErrorMessage({
  content,
  onRetry,
}: {
  content: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm">
      <div className="flex items-start gap-2">
        <AlertCircle size={16} className="mt-0.5 shrink-0 text-destructive" />
        <span className="text-destructive">{content}</span>
      </div>
      {onRetry && (
        <button
          className="mt-2 text-xs text-destructive underline hover:no-underline"
          onClick={onRetry}
        >
          再試行
        </button>
      )}
    </div>
  );
}

function UsageBadge({
  usage,
  maxContextTokens,
}: {
  usage: ChatMessage["usage"];
  maxContextTokens?: number;
}) {
  if (!usage) return null;
  const pct =
    maxContextTokens && maxContextTokens > 0
      ? Math.round((usage.total_tokens / maxContextTokens) * 100)
      : null;
  return (
    <div className="mt-1 flex gap-2 text-[11px] text-muted-foreground">
      <span>in: {usage.input_tokens.toLocaleString()}</span>
      <span>out: {usage.output_tokens.toLocaleString()}</span>
      <span>total: {usage.total_tokens.toLocaleString()}</span>
      {pct !== null && <span>ctx: {pct}%</span>}
    </div>
  );
}

export function Chat({
  threadId,
  onFirstMessage,
}: {
  threadId?: string;
  onFirstMessage?: (threadId: string, title: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 設定
  const [volumePath, setVolumePath] = useState(
    () => localStorage.getItem(STORAGE_KEY_VOLUME) ?? ""
  );
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem(STORAGE_KEY_MODEL) ?? ""
  );
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // スレッドID（外から渡されない場合は内部で管理）
  const [currentThreadId, setCurrentThreadId] = useState<string>(
    threadId ?? crypto.randomUUID()
  );

  useEffect(() => {
    if (threadId) setCurrentThreadId(threadId);
  }, [threadId]);

  // /api/config からモデル一覧を取得
  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.models)) {
          setAvailableModels(data.models);
          if (!selectedModel && data.default_model) {
            setSelectedModel(data.default_model);
            localStorage.setItem(STORAGE_KEY_MODEL, data.default_model);
          }
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSaveSettings = (vp: string, model: string) => {
    setVolumePath(vp);
    setSelectedModel(model);
    localStorage.setItem(STORAGE_KEY_VOLUME, vp);
    localStorage.setItem(STORAGE_KEY_MODEL, model);
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMessage: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setStreaming(true);

    // 最初のメッセージ時にチャット履歴を保存 + コールバック
    if (messages.length === 0) {
      const userId =
        localStorage.getItem("apx_user_id") ?? (() => {
          const id = crypto.randomUUID();
          localStorage.setItem("apx_user_id", id);
          return id;
        })();
      if (volumePath) {
        fetch("/api/chat-history", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-uc-volume-path": volumePath,
          },
          body: JSON.stringify({
            id: currentThreadId,
            userId,
            title: text.slice(0, 60),
            createdAt: new Date().toISOString(),
            visibility: "private",
          }),
        }).catch(() => {});
      }
      if (onFirstMessage) {
        onFirstMessage(currentThreadId, text.slice(0, 60));
      }
    }

    // 空のアシスタントメッセージを追加
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", subagentBlocks: [], toolCallBlocks: [] },
    ]);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(volumePath ? { "x-uc-volume-path": volumePath } : {}),
        },
        body: JSON.stringify({
          input: [{ role: "user", content: text }],
          stream: true,
          custom_inputs: {
            volume_path: volumePath,
            llm_model: selectedModel,
            thread_id: currentThreadId,
          },
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6).trim();
            if (!dataStr || dataStr === "[DONE]") continue;
            try {
              const data = JSON.parse(dataStr);
              const resolvedType = eventType || data.type || "";

              if (
                resolvedType === "response.output_text.delta" &&
                typeof data.delta === "string"
              ) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      content: (last.content ?? "") + data.delta,
                    };
                  }
                  return updated;
                });
              } else if (resolvedType === "subagent.start") {
                const name = (data as { name?: string }).name ?? "";
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      subagentBlocks: [...(last.subagentBlocks ?? []), { name, content: "" }],
                    };
                  }
                  return updated;
                });
              } else if (resolvedType === "subagent.end") {
                // 将来的にアクティブ/完了状態の切り替えに使用可能（現時点では何もしない）
              } else if (resolvedType === "response.output_item.done") {
                const item = data.item ?? {};
                if (item.type === "function_call") {
                  const newBlock: ToolCallBlock = {
                    callId: item.call_id ?? item.id ?? "",
                    name: item.name ?? "",
                    arguments: item.arguments ?? "",
                  };
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last?.role === "assistant") {
                      updated[updated.length - 1] = {
                        ...last,
                        toolCallBlocks: [...(last.toolCallBlocks ?? []), newBlock],
                      };
                    }
                    return updated;
                  });
                } else if (item.type === "function_call_output") {
                  const callId = item.call_id ?? "";
                  const result = item.output ?? "";
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last?.role === "assistant" && last.toolCallBlocks) {
                      const updatedBlocks = last.toolCallBlocks.map((b) =>
                        b.callId === callId ? { ...b, result } : b
                      );
                      updated[updated.length - 1] = {
                        ...last,
                        toolCallBlocks: updatedBlocks,
                      };
                    }
                    return updated;
                  });
                }
              } else if (resolvedType === "response.completed") {
                const resp = data.response ?? {};
                const usage = resp.usage;
                const model = resp.model;
                const maxCtx = resp.max_context_tokens;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      usage,
                      model,
                      maxContextTokens: maxCtx,
                    };
                  }
                  return updated;
                });
              } else if (resolvedType === "error" && data.error) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      content: `Error: ${data.error}`,
                      isError: true,
                    };
                  }
                  return updated;
                });
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === "assistant") {
          updated[updated.length - 1] = {
            ...last,
            content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
            isError: true,
          };
        }
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* ヘッダー */}
      <div className="flex items-center justify-end border-b px-3 py-1.5">
        <SettingsDialog
          volumePath={volumePath}
          selectedModel={selectedModel}
          availableModels={availableModels}
          onSave={handleSaveSettings}
        />
      </div>

      {/* Volume Path 未設定の警告 */}
      {!volumePath && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800 px-4 py-2 text-xs text-yellow-800 dark:text-yellow-200">
          ⚠ UC Volume Path が未設定です。右上の設定ボタンから入力してください。
        </div>
      )}

      {/* メッセージリスト */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
            Send a message to start chatting
          </div>
        )}
        {messages.map((msg, i) => {
          const isLastAssistant =
            i === messages.length - 1 && msg.role === "assistant";
          const showTypingIndicator =
            isLastAssistant &&
            streaming &&
            msg.content === "" &&
            (!msg.subagentBlocks || msg.subagentBlocks.length === 0) &&
            (!msg.toolCallBlocks || msg.toolCallBlocks.length === 0);

          return (
            <Message key={i} from={msg.role}>
              <MessageContent>
                {msg.role === "assistant" ? (
                  showTypingIndicator ? (
                    <div className="flex items-center gap-1 px-1 py-1">
                      <span className="h-2 w-2 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
                      <span className="h-2 w-2 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
                      <span className="h-2 w-2 rounded-full bg-current animate-bounce" />
                    </div>
                  ) : (
                    <div>
                      {/* ToolCall ブロック */}
                      {msg.toolCallBlocks && msg.toolCallBlocks.length > 0 && (
                        <div className="mb-2 space-y-1">
                          {msg.toolCallBlocks.map((block, bi) => (
                            <ToolCallSection
                              key={bi}
                              block={block}
                              isStreaming={isLastAssistant && streaming}
                            />
                          ))}
                        </div>
                      )}
                      {/* サブエージェントブロック */}
                      {msg.subagentBlocks && msg.subagentBlocks.length > 0 && (
                        <div className="mb-2 space-y-1">
                          {msg.subagentBlocks.map((block, bi) => (
                            <SubagentSection key={bi} block={block} />
                          ))}
                        </div>
                      )}
                      {/* メイン応答またはエラー */}
                      {msg.isError ? (
                        <ErrorMessage
                          content={msg.content}
                          onRetry={() => {
                            // 直前のユーザーメッセージを再送信
                            const lastUser = [...messages]
                              .reverse()
                              .find((m) => m.role === "user");
                            if (lastUser) {
                              setMessages((prev) => prev.slice(0, -1));
                              setInput(lastUser.content);
                            }
                          }}
                        />
                      ) : (
                        <MessageResponse>{msg.content}</MessageResponse>
                      )}
                      {/* Usage */}
                      <UsageBadge
                        usage={msg.usage}
                        maxContextTokens={msg.maxContextTokens}
                      />
                    </div>
                  )
                ) : (
                  msg.content
                )}
              </MessageContent>
            </Message>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* 入力エリア */}
      <div className="border-t px-4 py-3">
        <div className="flex items-end gap-2">
          <Textarea
            className="min-h-[60px] max-h-[160px] resize-none"
            placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming}
          />
          <Button
            size="icon"
            onClick={sendMessage}
            disabled={streaming || !input.trim()}
          >
            <SendHorizonal size={18} />
          </Button>
        </div>
      </div>
    </div>
  );
}
