import { createFileRoute } from "@tanstack/react-router";
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
  usePromptInputController,
} from "@/components/ai-elements/prompt-input";
import {
  Suggestion,
  Suggestions,
} from "@/components/ai-elements/suggestion";
import { SettingsDialog } from "@/components/chat/settings-dialog";

export const Route = createFileRoute("/_sidebar/chat/$threadId")({
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

const STARTER_SUGGESTIONS = [
  "最新のデータを分析してください",
  "データを可視化してください",
  "SQLクエリを書いてください",
  "このデータセットを要約してください",
];

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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

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
    // 前のストリーミングを中断
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setStreaming(false);
    setMessages([]);

    if (!userId) return;

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
        if (data && Array.isArray(data.messages)) {
          setMessages(data.messages as ChatMessage[]);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

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
    if (streaming) {
      handleStop();
      return;
    }

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

  const hasMessages = messages.length > 0;

  return (
    <PromptInputProvider>
      <ChatContent
        messages={messages}
        streaming={streaming}
        hasMessages={hasMessages}
        volumePath={volumePath}
        selectedModel={selectedModel}
        availableModels={availableModels}
        onSubmit={handleSubmit}
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
  hasMessages: boolean;
  volumePath: string;
  selectedModel: string;
  availableModels: string[];
  onSubmit: (text: string) => void;
  onRetry: () => void;
  onSaveSettings: (vp: string) => void;
  onModelChange: (model: string) => void;
};

function ChatContent({
  messages,
  streaming,
  hasMessages,
  volumePath,
  selectedModel,
  availableModels,
  onSubmit,
  onRetry,
  onSaveSettings,
  onModelChange,
}: ChatContentProps) {
  const { textInput } = usePromptInputController();

  const handleFormSubmit = ({ text }: { text: string; files: unknown[] }) => {
    onSubmit(text);
  };

  const handleSuggestionClick = (suggestion: string) => {
    textInput.setInput(suggestion);
  };

  const promptInput = (
    <PromptInput onSubmit={handleFormSubmit}>
      <PromptInputBody>
        <PromptInputTextarea
          placeholder="メッセージを入力... (Enter で送信、Shift+Enter で改行)"
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
        <PromptInputSubmit status={streaming ? "streaming" : undefined} />
      </PromptInputFooter>
    </PromptInput>
  );

  if (!hasMessages) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-8 px-[20%] overflow-auto">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold">APX-Agent</h1>
          <p className="text-muted-foreground text-sm">
            何でも聞いてください
          </p>
        </div>
        <div className="flex justify-center w-full max-w-2xl">
          <Suggestions>
            {STARTER_SUGGESTIONS.map((s) => (
              <Suggestion key={s} suggestion={s} onClick={handleSuggestionClick} />
            ))}
          </Suggestions>
        </div>
        <div className="w-full max-w-2xl">{promptInput}</div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      <Conversation className="flex-1">
        <ConversationContent className="max-w-2xl mx-auto w-full">
          {messages.map((msg, i) => {
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
