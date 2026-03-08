import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputProvider,
  PromptInputSelect,
  PromptInputSelectContent,
  PromptInputSelectItem,
  PromptInputSelectTrigger,
  PromptInputSelectValue,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { SettingsDialog } from "@/components/chat/settings-dialog";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/_sidebar/chat/$threadId")({
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : undefined,
  }),
  component: () => <ChatPage />,
});

// ─── Types ───────────────────────────────────────────────────────────────────

type ToolCallState =
  | "input-streaming"
  | "input-available"
  | "output-available"
  | "output-error";

type ToolCallBlock = {
  callId: string;
  name: string;
  arguments: string;
  result?: string;
  state: ToolCallState;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  toolCallBlocks?: ToolCallBlock[];
  isError?: boolean;
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  model?: string;
};

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_VOLUME = "apx_volume_path";
const STORAGE_KEY_MODEL = "apx_selected_model";
const STORAGE_KEY_USER = "apx_user_id";

function getOrCreateUserId(): string {
  let id = localStorage.getItem(STORAGE_KEY_USER);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY_USER, id);
  }
  return id;
}

// ─── Main Page ────────────────────────────────────────────────────────────────

function ChatPage() {
  const { threadId } = Route.useParams();
  const { q: initialQuery } = Route.useSearch();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const prevStreamingRef = useRef(false);
  const initialQueryFiredRef = useRef(false);
  const prevThreadIdRef = useRef<string | null>(null);
  messagesRef.current = messages;

  const [volumePath, setVolumePath] = useState(
    () => localStorage.getItem(STORAGE_KEY_VOLUME) ?? ""
  );
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem(STORAGE_KEY_MODEL) ?? ""
  );
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  const userId = getOrCreateUserId();

  // threadId 変更時に履歴をロード
  useEffect(() => {
    // 本物のthreadId変更時のみリセット（StrictModeの二重実行を無視）
    const isNewThread = prevThreadIdRef.current !== threadId;
    prevThreadIdRef.current = threadId;

    if (isNewThread) {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      setStreaming(false);
      setMessages([]);
      initialQueryFiredRef.current = false;
    }

    if (!userId) return;

    setIsLoadingHistory(true);

    fetch(
      `/api/chat-history/${threadId}/messages?user_id=${encodeURIComponent(userId)}`,
      {
        headers: volumePath ? { "x-uc-volume-path": volumePath } : {},
      }
    )
      .then((r) => {
        if (!r.ok) return;
        return r.json();
      })
      .then((data) => {
        const msgs = Array.isArray(data) ? data : (data?.messages ?? []);
        if (msgs.length > 0) {
          setMessages(msgs as ChatMessage[]);
        }
      })
      .catch(() => {})
      .finally(() => {
        setIsLoadingHistory(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  // ストリーミング完了時にメッセージを永続化
  useEffect(() => {
    if (!streaming && prevStreamingRef.current && messagesRef.current.length > 0 && volumePath) {
      fetch(`/api/chat-history/${threadId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-uc-volume-path": volumePath,
        },
        body: JSON.stringify({ userId, messages: messagesRef.current }),
      }).catch(() => {});
    }
    prevStreamingRef.current = streaming;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming]);

  // モデル一覧取得
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStop = () => {
    abortControllerRef.current?.abort();
    setStreaming(false);
  };

  const handleSaveSettings = (vp: string) => {
    setVolumePath(vp);
    localStorage.setItem(STORAGE_KEY_VOLUME, vp);
  };

  const handleModelChange = (model: string) => {
    setSelectedModel(model);
    localStorage.setItem(STORAGE_KEY_MODEL, model);
  };

  const handleSubmit = async (text: string) => {
    if (!text.trim()) return;
    if (streaming || isLoadingHistory) return;

    // 最初のメッセージ時にチャット履歴を保存
    if (messages.length === 0 && volumePath) {
      fetch("/api/chat-history", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-uc-volume-path": volumePath,
        },
        body: JSON.stringify({
          id: threadId,
          userId,
          title: text.slice(0, 60),
          createdAt: new Date().toISOString(),
          visibility: "private",
        }),
      })
        .then(() => window.dispatchEvent(new CustomEvent("chat-list-updated")))
        .catch(() => {});
    }

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", toolCallBlocks: [] },
    ]);

    const ctrl = new AbortController();
    abortControllerRef.current = ctrl;
    setStreaming(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        signal: ctrl.signal,
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
            thread_id: threadId,
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
              } else if (
                resolvedType === "response.output_text.reasoning.delta" &&
                typeof data.delta === "string"
              ) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = {
                      ...last,
                      thinking: (last.thinking ?? "") + data.delta,
                    };
                  }
                  return updated;
                });
              } else if (resolvedType === "response.output_item.done") {
                const item = data.item ?? {};
                if (item.type === "function_call") {
                  const newBlock: ToolCallBlock = {
                    callId: item.call_id ?? item.id ?? "",
                    name: item.name ?? "",
                    arguments: item.arguments ?? "",
                    state: "input-available",
                  };
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last?.role === "assistant") {
                      updated[updated.length - 1] = {
                        ...last,
                        toolCallBlocks: [
                          ...(last.toolCallBlocks ?? []),
                          newBlock,
                        ],
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
                      updated[updated.length - 1] = {
                        ...last,
                        toolCallBlocks: last.toolCallBlocks.map((b) =>
                          b.callId === callId
                            ? { ...b, result, state: "output-available" as const }
                            : b
                        ),
                      };
                    }
                    return updated;
                  });
                }
              } else if (resolvedType === "response.completed") {
                const resp = data.response ?? {};
                const usage = resp.usage;
                const model = resp.model;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === "assistant") {
                    updated[updated.length - 1] = { ...last, usage, model };
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
              // ignore parse errors
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        // ユーザーが停止 - 空のアシスタントメッセージを削除
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant" && !last.content && !last.toolCallBlocks?.length) {
            return updated.slice(0, -1);
          }
          return updated;
        });
      } else {
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
      }
    } finally {
      setStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleRetry = () => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) {
      setMessages((prev) => prev.slice(0, -1));
      handleSubmit(lastUser.content);
    }
  };

  // search.q による初期メッセージの自動送信
  useEffect(() => {
    if (!initialQuery || initialQueryFiredRef.current) return;
    initialQueryFiredRef.current = true;
    // URLから q を除去（ブラウザ履歴に残さない）
    navigate({
      to: "/chat/$threadId",
      params: { threadId },
      search: { q: undefined },
      replace: true,
    });
    handleSubmit(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  return (
    <PromptInputProvider>
      <ChatContent
        messages={messages}
        streaming={streaming}
        isLoadingHistory={isLoadingHistory}
        volumePath={volumePath}
        selectedModel={selectedModel}
        availableModels={availableModels}
        onSubmit={handleSubmit}
        onStop={handleStop}
        onRetry={handleRetry}
        onSaveSettings={handleSaveSettings}
        onModelChange={handleModelChange}
      />
    </PromptInputProvider>
  );
}

// ─── Chat Content ─────────────────────────────────────────────────────────────

type ChatContentProps = {
  messages: ChatMessage[];
  streaming: boolean;
  isLoadingHistory: boolean;
  volumePath: string;
  selectedModel: string;
  availableModels: string[];
  onSubmit: (text: string) => void;
  onStop: () => void;
  onRetry: () => void;
  onSaveSettings: (vp: string) => void;
  onModelChange: (model: string) => void;
};

function ChatContent({
  messages,
  streaming,
  isLoadingHistory,
  volumePath,
  selectedModel,
  availableModels,
  onSubmit,
  onStop,
  onRetry,
  onSaveSettings,
  onModelChange,
}: ChatContentProps) {
  const handleFormSubmit = ({ text }: { text: string; files: unknown[] }) => {
    onSubmit(text);
  };

  const promptInput = (
    <PromptInput onSubmit={handleFormSubmit}>
      <PromptInputBody>
        <PromptInputTextarea
          placeholder="メッセージを入力... (Enter で送信、Shift+Enter で改行)"
          disabled={streaming || isLoadingHistory}
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          {availableModels.length > 0 && (
            <PromptInputSelect
              value={selectedModel}
              onValueChange={(v) => {
                localStorage.setItem("apx_selected_model", v);
                onModelChange(v);
              }}
            >
              <PromptInputSelectTrigger className="h-7 text-xs max-w-[180px]">
                <PromptInputSelectValue placeholder="モデル選択" />
              </PromptInputSelectTrigger>
              <PromptInputSelectContent>
                {availableModels.map((m) => (
                  <PromptInputSelectItem key={m} value={m}>
                    {m}
                  </PromptInputSelectItem>
                ))}
              </PromptInputSelectContent>
            </PromptInputSelect>
          )}
          <SettingsDialog
            volumePath={volumePath}
            onSave={onSaveSettings}
          />
        </PromptInputTools>
        <PromptInputSubmit
          status={streaming ? "streaming" : undefined}
          onClick={streaming ? onStop : undefined}
        />
      </PromptInputFooter>
    </PromptInput>
  );

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      <Conversation className="flex-1">
        <ConversationContent className="max-w-2xl mx-auto w-full">
          {isLoadingHistory ? (
            <div className="space-y-4 py-4">
              <div className="flex justify-end">
                <Skeleton className="h-10 w-48 rounded-2xl" />
              </div>
              <div className="flex justify-start">
                <Skeleton className="h-16 w-64 rounded-2xl" />
              </div>
              <div className="flex justify-end">
                <Skeleton className="h-10 w-40 rounded-2xl" />
              </div>
              <div className="flex justify-start">
                <Skeleton className="h-24 w-72 rounded-2xl" />
              </div>
            </div>
          ) : messages.map((msg, i) => {
            const isLast = i === messages.length - 1;
            return (
              <Message key={i} from={msg.role}>
                {msg.thinking && (
                  <Reasoning
                    isStreaming={streaming && isLast}
                    defaultOpen={streaming && isLast}
                  >
                    <ReasoningTrigger />
                    <ReasoningContent>{msg.thinking}</ReasoningContent>
                  </Reasoning>
                )}
                {msg.toolCallBlocks && msg.toolCallBlocks.length > 0 && (
                  <div className="space-y-2 w-full">
                    {msg.toolCallBlocks.map((block, bi) => {
                      let parsedArgs: Record<string, unknown> = {};
                      try {
                        parsedArgs = JSON.parse(block.arguments || "{}");
                      } catch {
                        parsedArgs = { raw: block.arguments };
                      }
                      return (
                        <Tool key={bi}>
                          <ToolHeader
                            title={block.name}
                            type="tool-call"
                            state={block.state}
                          />
                          <ToolContent>
                            <ToolInput input={parsedArgs} />
                            {block.result !== undefined && (
                              <ToolOutput
                                output={block.result}
                                errorText={
                                  block.state === "output-error"
                                    ? block.result
                                    : undefined
                                }
                              />
                            )}
                          </ToolContent>
                        </Tool>
                      );
                    })}
                  </div>
                )}
                <MessageContent>
                  {msg.isError ? (
                    <div className="text-destructive text-sm">{msg.content}</div>
                  ) : msg.role === "assistant" && !msg.content && streaming && isLast ? (
                    <div className="space-y-2 py-1">
                      <Skeleton className="h-3 w-48" />
                      <Skeleton className="h-3 w-64" />
                      <Skeleton className="h-3 w-40" />
                    </div>
                  ) : (
                    <MessageResponse>{msg.content}</MessageResponse>
                  )}
                </MessageContent>
                {msg.role === "assistant" && !streaming && msg.content && (
                  <MessageActions>
                    <MessageAction
                      tooltip="コピー"
                      onClick={() =>
                        navigator.clipboard.writeText(msg.content)
                      }
                    >
                      <Copy className="size-3.5" />
                    </MessageAction>
                    {isLast && (
                      <MessageAction tooltip="再生成" onClick={onRetry}>
                        <RefreshCw className="size-3.5" />
                      </MessageAction>
                    )}
                  </MessageActions>
                )}
              </Message>
            );
          })}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
      <div className="shrink-0 border-t p-4">
        <div className="max-w-2xl mx-auto">{promptInput}</div>
      </div>
    </div>
  );
}
