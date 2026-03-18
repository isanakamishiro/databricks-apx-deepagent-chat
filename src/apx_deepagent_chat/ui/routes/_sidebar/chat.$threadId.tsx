import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { SubAgentBlock, type SubAgentBlockData } from "@/components/chat/subagent-block";
import { AlertCircle, Copy, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
  Context,
  ContextTrigger,
  ContextContent,
  ContextContentHeader,
  ContextContentBody,
  ContextInputUsage,
  ContextOutputUsage,
  ContextContentFooter,
} from "@/components/ai-elements/context";
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
import { VolumeExplorer } from "@/components/chat/volume-explorer";
import { GeneratedFiles } from "@/components/chat/generated-files";
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

// 実行順を保持するための統合ブロック型
type ChatBlock =
  | (ToolCallBlock & { type: "tool" })
  | (SubAgentBlockData & { type: "subagent" });

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  blocks?: ChatBlock[];               // 実行順の統合ブロック配列
  toolCallBlocks?: ToolCallBlock[];   // 後方互換性のために残す
  subAgentBlocks?: SubAgentBlockData[]; // 後方互換性のために残す
  isError?: boolean;
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  model?: string;
  maxInputTokens?: number;
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

const FILE_WRITE_TOOL_NAMES = new Set(["write_file", "edit_file"]);

function extractWrittenFiles(message: ChatMessage): string[] {
  const paths = new Set<string>();

  if (message.blocks) {
    for (const block of message.blocks) {
      if (block.type === "tool") {
        if (FILE_WRITE_TOOL_NAMES.has(block.name) && block.state === "output-available") {
          try {
            const args = JSON.parse(block.arguments);
            if (args.file_path) paths.add(args.file_path);
          } catch {
            // ignore
          }
        }
      } else {
        for (const tc of block.toolCalls) {
          if (FILE_WRITE_TOOL_NAMES.has(tc.name) && tc.state === "output-available") {
            try {
              const args = JSON.parse(tc.arguments);
              if (args.file_path) paths.add(args.file_path);
            } catch {
              // ignore
            }
          }
        }
      }
    }
  } else {
    for (const block of message.toolCallBlocks ?? []) {
      if (FILE_WRITE_TOOL_NAMES.has(block.name) && block.state === "output-available") {
        try {
          const args = JSON.parse(block.arguments);
          if (args.file_path) paths.add(args.file_path);
        } catch {
          // ignore
        }
      }
    }

    for (const sub of message.subAgentBlocks ?? []) {
      for (const tc of sub.toolCalls) {
        if (FILE_WRITE_TOOL_NAMES.has(tc.name) && tc.state === "output-available") {
          try {
            const args = JSON.parse(tc.arguments);
            if (args.file_path) paths.add(args.file_path);
          } catch {
            // ignore
          }
        }
      }
    }
  }

  return Array.from(paths);
}

// ─── Constants ───────────────────────────────────────────────────────────────

function getModelMaxTokens(model?: string): number {
  if (!model) return 200_000;
  if (model.includes("opus")) return 200_000;
  if (model.includes("sonnet")) return 200_000;
  if (model.includes("haiku")) return 200_000;
  if (model.includes("gpt-4o")) return 128_000;
  if (model.includes("gpt-4")) return 128_000;
  return 200_000;
}

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
  const activeSubagentCallIdRef = useRef<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const prevStreamingRef = useRef(false);
  const initialQueryFiredRef = useRef(false);
  const persistedCountRef = useRef(0);
  const prevThreadIdRef = useRef<string | null>(null);
  messagesRef.current = messages;

  const [volumePath, setVolumePath] = useState(
    () => localStorage.getItem(STORAGE_KEY_VOLUME) ?? ""
  );
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem(STORAGE_KEY_MODEL) ?? ""
  );
  const [availableModels, setAvailableModels] = useState<{id: string; display_name: string}[]>([]);

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
      persistedCountRef.current = 0;
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
          persistedCountRef.current = msgs.length;
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
      const newMessages = messagesRef.current.slice(persistedCountRef.current);
      if (newMessages.length > 0) {
        fetch(`/api/chat-history/${threadId}/messages`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-uc-volume-path": volumePath,
          },
          body: JSON.stringify({ userId, messages: newMessages }),
        }).catch(() => {});
        persistedCountRef.current = messagesRef.current.length;
      }
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

  const handleVolumeSelect = (vp: string) => {
    setVolumePath(vp);
    localStorage.setItem(STORAGE_KEY_VOLUME, vp);
    window.location.href = '/chat';
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
      { role: "assistant", content: "", blocks: [], toolCallBlocks: [] },
    ]);

    const ctrl = new AbortController();
    abortControllerRef.current = ctrl;
    activeSubagentCallIdRef.current = null;
    setStreaming(true);

    try {
      // Step 1: エージェント処理をバックグラウンドで開始し、job_id を取得
      const startRes = await fetch("/api/chat/start", {
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

      if (!startRes.ok) {
        throw new Error(`Failed to start job: ${startRes.status}`);
      }

      const { job_id: jobId } = await startRes.json() as { job_id: string };

      // Step 2: SSE で結果を受け取る（115秒ごとに自動再接続）
      let lastEventId = -1;
      let streamCompleted = false;

      outerLoop: while (!streamCompleted) {
        if (ctrl.signal.aborted) break;

        const reconnectCtrl = new AbortController();
        const reconnectTimer = setTimeout(() => reconnectCtrl.abort(), 115_000);
        const onParentAbort = () => reconnectCtrl.abort();
        ctrl.signal.addEventListener("abort", onParentAbort, { once: true });

        try {
          const response = await fetch(`/api/chat/stream/${jobId}`, {
            signal: reconnectCtrl.signal,
            headers: lastEventId >= 0 ? { "Last-Event-ID": String(lastEventId) } : {},
          });

          if (!response.ok || !response.body) {
            throw new Error(`Stream request failed: ${response.status}`);
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
              if (line.startsWith("id: ")) {
                const parsed = parseInt(line.slice(4).trim(), 10);
                if (!isNaN(parsed)) lastEventId = parsed;
              } else if (line.startsWith("event: ")) {
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
                  } else if (resolvedType === "subagent.start") {
                    const callId: string = data.call_id ?? "";
                    const agentType: string = data.name ?? "";
                    activeSubagentCallIdRef.current = callId;
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last?.role === "assistant") {
                        const subAgentBlocks = (last.subAgentBlocks ?? []).map((b) =>
                          b.callId === callId
                            ? { ...b, agentType, state: "running" as const }
                            : b
                        );
                        const newBlocks = (last.blocks ?? []).map((b) =>
                          b.type === "subagent" && b.callId === callId
                            ? { ...b, agentType, state: "running" as const }
                            : b
                        );
                        updated[updated.length - 1] = { ...last, subAgentBlocks, blocks: newBlocks };
                      }
                      return updated;
                    });
                  } else if (resolvedType === "subagent.end") {
                    const callId: string = data.call_id ?? "";
                    activeSubagentCallIdRef.current = null;
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last?.role === "assistant") {
                        const subAgentBlocks = (last.subAgentBlocks ?? []).map((b) =>
                          b.callId === callId
                            ? { ...b, state: "done" as const }
                            : b
                        );
                        const newBlocks = (last.blocks ?? []).map((b) =>
                          b.type === "subagent" && b.callId === callId
                            ? { ...b, state: "done" as const }
                            : b
                        );
                        updated[updated.length - 1] = { ...last, subAgentBlocks, blocks: newBlocks };
                      }
                      return updated;
                    });
                  } else if (resolvedType === "response.output_item.done") {
                    const item = data.item ?? {};
                    if (item.type === "function_call") {
                      const activeCallId = activeSubagentCallIdRef.current;
                      if (item.name === "task") {
                        // task ツール → SubAgentBlock を作成（pending）
                        const newSubAgent: SubAgentBlockData = {
                          callId: item.call_id ?? item.id ?? "",
                          agentType: "",
                          toolCalls: [],
                          state: "pending",
                        };
                        setMessages((prev) => {
                          const updated = [...prev];
                          const last = updated[updated.length - 1];
                          if (last?.role === "assistant") {
                            updated[updated.length - 1] = {
                              ...last,
                              subAgentBlocks: [
                                ...(last.subAgentBlocks ?? []),
                                newSubAgent,
                              ],
                              blocks: [
                                ...(last.blocks ?? []),
                                { type: "subagent" as const, ...newSubAgent },
                              ],
                            };
                          }
                          return updated;
                        });
                      } else if (activeCallId) {
                        // サブエージェント内のツール呼び出し → 該当 SubAgentBlock に追加
                        const newTool = {
                          callId: item.call_id ?? item.id ?? "",
                          name: item.name ?? "",
                          arguments: item.arguments ?? "",
                          state: "input-available" as ToolCallState,
                        };
                        setMessages((prev) => {
                          const updated = [...prev];
                          const last = updated[updated.length - 1];
                          if (last?.role === "assistant") {
                            const subAgentBlocks = (last.subAgentBlocks ?? []).map((b) =>
                              b.callId === activeCallId
                                ? { ...b, toolCalls: [...b.toolCalls, newTool] }
                                : b
                            );
                            const newBlocks = (last.blocks ?? []).map((b) =>
                              b.type === "subagent" && b.callId === activeCallId
                                ? { ...b, toolCalls: [...b.toolCalls, newTool] }
                                : b
                            );
                            updated[updated.length - 1] = { ...last, subAgentBlocks, blocks: newBlocks };
                          }
                          return updated;
                        });
                      } else {
                        // 通常のツール呼び出し
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
                              blocks: [
                                ...(last.blocks ?? []),
                                { type: "tool" as const, ...newBlock },
                              ],
                            };
                          }
                          return updated;
                        });
                      }
                    } else if (item.type === "function_call_output") {
                      const callId = item.call_id ?? "";
                      const result = item.output ?? "";
                      const activeCallId = activeSubagentCallIdRef.current;
                      setMessages((prev) => {
                        const updated = [...prev];
                        const last = updated[updated.length - 1];
                        if (last?.role === "assistant") {
                          // サブエージェント内のツール結果
                          if (activeCallId) {
                            const subAgentBlocks = (last.subAgentBlocks ?? []).map((b) =>
                              b.callId === activeCallId
                                ? {
                                    ...b,
                                    toolCalls: b.toolCalls.map((t) =>
                                      t.callId === callId
                                        ? { ...t, result, state: "output-available" as ToolCallState }
                                        : t
                                    ),
                                  }
                                : b
                            );
                            const newBlocks = (last.blocks ?? []).map((b) =>
                              b.type === "subagent" && b.callId === activeCallId
                                ? {
                                    ...b,
                                    toolCalls: b.toolCalls.map((t) =>
                                      t.callId === callId
                                        ? { ...t, result, state: "output-available" as ToolCallState }
                                        : t
                                    ),
                                  }
                                : b
                            );
                            updated[updated.length - 1] = { ...last, subAgentBlocks, blocks: newBlocks };
                          } else {
                            // task の完了結果か、通常ツールの結果かを判定
                            const isSubagentResult = (last.subAgentBlocks ?? []).some(
                              (b) => b.callId === callId
                            ) || (last.blocks ?? []).some(
                              (b) => b.type === "subagent" && b.callId === callId
                            );
                            if (isSubagentResult) {
                              // SubAgentBlock の result に保存
                              const subAgentBlocks = (last.subAgentBlocks ?? []).map((b) =>
                                b.callId === callId ? { ...b, result } : b
                              );
                              const newBlocks = (last.blocks ?? []).map((b) =>
                                b.type === "subagent" && b.callId === callId
                                  ? { ...b, result }
                                  : b
                              );
                              updated[updated.length - 1] = { ...last, subAgentBlocks, blocks: newBlocks };
                            } else {
                              // 通常ツールの結果
                              const toolCallBlocks = (last.toolCallBlocks ?? []).map((b) =>
                                b.callId === callId
                                  ? { ...b, result, state: "output-available" as const }
                                  : b
                              );
                              const newBlocks = (last.blocks ?? []).map((b) =>
                                b.type === "tool" && b.callId === callId
                                  ? { ...b, result, state: "output-available" as const }
                                  : b
                              );
                              updated[updated.length - 1] = { ...last, toolCallBlocks, blocks: newBlocks };
                            }
                          }
                        }
                        return updated;
                      });
                    }
                  } else if (resolvedType === "response.completed") {
                    streamCompleted = true;
                    const resp = data.response ?? {};
                    const usage = resp.usage;
                    const model = resp.model;
                    const rawMax = resp.metadata?.max_input_tokens;
                    const maxInputTokens = rawMax != null ? (Number.isFinite(Number(rawMax)) ? Number(rawMax) : undefined) : undefined;
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last?.role === "assistant") {
                        updated[updated.length - 1] = { ...last, usage, model, maxInputTokens };
                      }
                      return updated;
                    });
                  } else if (resolvedType === "error" && (data.error || data.message)) {
                    streamCompleted = true; // エラーもストリーム終了として扱う
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last?.role === "assistant") {
                        updated[updated.length - 1] = {
                          ...last,
                          content: `Error: ${data.error ?? data.message}`,
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
        } catch (e) {
          if (e instanceof Error && e.name === "AbortError") {
            if (ctrl.signal.aborted) break outerLoop; // ユーザーが停止
            continue outerLoop; // 115秒再接続
          }
          throw e;
        } finally {
          clearTimeout(reconnectTimer);
          ctrl.signal.removeEventListener("abort", onParentAbort);
        }
      }

      if (!streamCompleted && !ctrl.signal.aborted) {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant" && !last.isError) {
            updated[updated.length - 1] = {
              ...last,
              content: last.content || "接続が切れました。もう一度お試しください。",
              isError: true,
            };
          }
          return updated;
        });
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        // ユーザーが停止 - 空のアシスタントメッセージを削除
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant" && !last.content && !last.toolCallBlocks?.length && !last.subAgentBlocks?.length) {
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
        onVolumeSelect={handleVolumeSelect}
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
  availableModels: {id: string; display_name: string}[];
  onSubmit: (text: string) => void;
  onStop: () => void;
  onRetry: () => void;
  onVolumeSelect: (vp: string) => void;
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
  onVolumeSelect,
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
                  <PromptInputSelectItem key={m.id} value={m.id}>
                    {m.display_name}
                  </PromptInputSelectItem>
                ))}
              </PromptInputSelectContent>
            </PromptInputSelect>
          )}
          <VolumeExplorer value={volumePath} onSelect={onVolumeSelect} />
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
                {(msg.blocks?.length || msg.subAgentBlocks?.length || msg.toolCallBlocks?.length) ? (
                  <div className="space-y-2 w-full">
                    {msg.blocks
                      ? msg.blocks.map((block, bi) => {
                          if (block.type === "subagent") {
                            return (
                              <SubAgentBlock
                                key={`sa-${bi}`}
                                block={block}
                              />
                            );
                          }
                          let parsedArgs: Record<string, unknown> = {};
                          try {
                            parsedArgs = JSON.parse(block.arguments || "{}");
                          } catch {
                            parsedArgs = { raw: block.arguments };
                          }
                          return (
                            <Tool key={`t-${bi}`}>
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
                        })
                      : (
                        // 後方互換: blocks フィールドのない旧保存データ用フォールバック
                        <>
                          {msg.subAgentBlocks?.map((block, bi) => (
                            <SubAgentBlock
                              key={`sa-${bi}`}
                              block={block}
                            />
                          ))}
                          {msg.toolCallBlocks?.map((block, bi) => {
                            let parsedArgs: Record<string, unknown> = {};
                            try {
                              parsedArgs = JSON.parse(block.arguments || "{}");
                            } catch {
                              parsedArgs = { raw: block.arguments };
                            }
                            return (
                              <Tool key={`t-${bi}`}>
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
                        </>
                      )
                    }
                  </div>
                ) : null}
                <MessageContent>
                  {msg.isError ? (
                    <Alert variant="destructive" className="w-full">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>{msg.content}</AlertDescription>
                    </Alert>
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
                {msg.role === "assistant" && !streaming && (() => {
                  const files = extractWrittenFiles(msg);
                  return files.length > 0 ? (
                    <GeneratedFiles files={files} volumePath={volumePath} />
                  ) : null;
                })()}
                {msg.role === "assistant" && !streaming && msg.content && (
                  <div className="flex flex-col items-start gap-1">
                    <div className="flex items-center gap-2">
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
                      {msg.model && (
                        <span className="text-xs text-muted-foreground">
                          {availableModels.find((m) => m.id === msg.model)?.display_name ?? msg.model}
                        </span>
                      )}
                    </div>
                    {isLast && msg.usage && (
                      <Context
                        usedTokens={msg.usage.total_tokens}
                        maxTokens={msg.maxInputTokens ?? getModelMaxTokens(msg.model)}
                        usage={{
                          inputTokens: msg.usage.input_tokens,
                          outputTokens: msg.usage.output_tokens,
                          totalTokens: msg.usage.total_tokens,
                          inputTokenDetails: { noCacheTokens: undefined, cacheReadTokens: undefined, cacheWriteTokens: undefined },
                          outputTokenDetails: { textTokens: undefined, reasoningTokens: undefined },
                        }}
                        modelId={msg.model}
                      >
                        <ContextTrigger size="icon-sm" />
                        <ContextContent>
                          <ContextContentHeader />
                          <ContextContentBody>
                            <ContextInputUsage />
                            <ContextOutputUsage />
                          </ContextContentBody>
                          <ContextContentFooter />
                        </ContextContent>
                      </Context>
                    )}
                  </div>
                )}
              </Message>
            );
          })}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
      <div className="shrink-0 border-t p-4">
        <div className="max-w-2xl mx-auto">
          {promptInput}
        </div>
      </div>
    </div>
  );
}
