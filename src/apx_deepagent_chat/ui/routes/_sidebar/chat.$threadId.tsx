import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { SubAgentBlock, type SubAgentBlockData } from "@/components/chat/subagent-block";
import { AlertCircle, Copy, MessageSquare, RefreshCw, Plus } from "lucide-react";
import { type UploadedAttachment } from "@/components/chat/attachment-panel";
import { nanoid } from "nanoid";
import { takePendingFiles } from "@/lib/pending-files";
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
  ConversationEmptyState,
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
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorName,
  ModelSelectorTrigger,
} from "@/components/ai-elements/model-selector";
import { Button } from "@/components/ui/button";
import { CheckIcon } from "lucide-react";
import { VolumeExplorer } from "@/components/chat/volume-explorer";
import { InfoPanel } from "@/components/chat/info-panel";
import { type AgentTodoItem, type AgentTodosGroup } from "@/components/chat/todo-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Shimmer } from "@/components/ui/shimmer";
import { getRandomWaitMessage } from "@/config/wait-messages";

export const Route = createFileRoute("/_sidebar/chat/$threadId")({
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : undefined,
    files: typeof search.files === "string" ? search.files : undefined,
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
type TextBlock = {
  type: "text";
  content: string;
};

type ChatBlock =
  | (ToolCallBlock & { type: "tool" })
  | (SubAgentBlockData & { type: "subagent" })
  | TextBlock;

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

function parseTodos(args: string): AgentTodoItem[] {
  try {
    const parsed = JSON.parse(args);
    const arr: Array<{ content?: string; status?: string }> = parsed.todos ?? [];
    return arr
      .map((t, i) => ({
        id: String(i),
        content: String(t.content ?? ""),
        status: (t.status as AgentTodoItem["status"]) ?? "pending",
      }))
      .filter((t) => t.content.length > 0);
  } catch {
    return [];
  }
}

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
      } else if (block.type === "subagent") {
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
  const { q: initialQuery, files: initialFiles } = Route.useSearch();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeSubagentCallIdRef = useRef<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const prevStreamingRef = useRef(false);
  const initialQueryFiredRef = useRef(false);
  const initialFilesFiredRef = useRef(false);
  const persistedCountRef = useRef(0);
  const prevThreadIdRef = useRef<string | null>(null);
  messagesRef.current = messages;

  const [messageQueue, setMessageQueue] = useState<string[]>([]);
  const messageQueueRef = useRef<string[]>([]);
  messageQueueRef.current = messageQueue;
  const currentJobIdRef = useRef<string | null>(null);
  const [stopping, setStopping] = useState(false);

  const [volumePath, setVolumePath] = useState(
    () => localStorage.getItem(STORAGE_KEY_VOLUME) ?? ""
  );
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem(STORAGE_KEY_MODEL) ?? ""
  );
  const [availableModels, setAvailableModels] = useState<{id: string; display_name: string}[]>([]);

  const userId = getOrCreateUserId();

  const [uploadedAttachments, setUploadedAttachments] = useState<UploadedAttachment[]>([]);

  const handleAttachmentAdd = (attachment: UploadedAttachment) => {
    setUploadedAttachments((prev) => [...prev, attachment]);
  };

  const handleAttachmentRemove = (id: string) => {
    setUploadedAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const handleAttachmentUpdate = (id: string, updates: Partial<UploadedAttachment>) => {
    setUploadedAttachments((prev) =>
      prev.map((a) => (a.id === id ? { ...a, ...updates } : a))
    );
  };

  // threadId 変更時に履歴をロード
  useEffect(() => {
    // 本物のthreadId変更時のみリセット（StrictModeの二重実行を無視）
    const isNewThread = prevThreadIdRef.current !== threadId;
    prevThreadIdRef.current = threadId;

    if (isNewThread) {
      // currentJobIdRef をクリアする前に interrupt を呼ぶ（スレッド切り替え時）
      const jobId = currentJobIdRef.current;
      if (jobId) {
        fetch(`/api/chat/interrupt/${jobId}?deep=true`, {
          method: "POST",
          keepalive: true,
        }).catch(() => {});
      }
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      setStreaming(false);
      setStopping(false);
      setMessages([]);
      initialQueryFiredRef.current = false;
      persistedCountRef.current = 0;
      setMessageQueue([]);
      messageQueueRef.current = [];
      currentJobIdRef.current = null;
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

  // コンポーネント unmount 時のクリーンアップ（ルート離脱時）
  // NOTE: abort() は呼ばない。React 18 Strict Mode はマウント後すぐにクリーンアップを
  //       実行するため、initialQuery で開始したストリームの AbortController を誤って
  //       abort してしまう。interrupt API (keepalive) だけ呼ぶことで、
  //       Strict Mode フェイクアンマウント時は currentJobIdRef.current が null なので安全。
  useEffect(() => {
    return () => {
      const jobId = currentJobIdRef.current;
      if (jobId) {
        fetch(`/api/chat/interrupt/${jobId}?deep=true`, {
          method: "POST",
          keepalive: true,
        }).catch(() => {});
      }
    };
  }, []); // 空依存配列 = unmount 時のみ実行

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
    if (messageQueue.length > 0) {
      const confirmed = window.confirm(
        `待機中のメッセージが ${messageQueue.length} 件あります。キャンセルすると待機中のメッセージも破棄されます。続行しますか？`
      );
      if (!confirmed) return;
      setMessageQueue([]);
      messageQueueRef.current = [];
    }
    if (currentJobIdRef.current) {
      fetch(`/api/chat/interrupt/${currentJobIdRef.current}?deep=true`, { method: "POST" }).catch(() => {});
    }
    setStopping(true);
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

  const handleSubmit = async (text: string, extraFilePaths?: string[]) => {
    if (!text.trim() && uploadedAttachments.length === 0 && !extraFilePaths?.length) return;
    if (isLoadingHistory) return;

    // ストリーミング中は queue に追加して割り込みをリクエスト
    if (streaming) {
      const isFirstQueued = messageQueueRef.current.length === 0;
      setMessageQueue(prev => [...prev, text]);
      messageQueueRef.current = [...messageQueueRef.current, text];
      if (isFirstQueued && currentJobIdRef.current) {
        fetch(`/api/chat/interrupt/${currentJobIdRef.current}`, { method: "POST" }).catch(() => {});
      }
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

    // APIに送信するテキスト（<files>ブロック付き）を構築
    let apiText = text;
    const allPaths = [
      ...uploadedAttachments
        .filter((a) => !a.uploading && !a.error && a.virtualPath)
        .map((a) => a.virtualPath),
      ...(extraFilePaths ?? []),
    ];
    if (allPaths.length > 0) {
      const pathLines = allPaths.map((p) => `  <path>${p}</path>`).join("\n");
      apiText = `${text}\n\n<files>\n${pathLines}\n</files>`;
    }

    setUploadedAttachments([]);

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
          input: [{ role: "user", content: apiText }],
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

      const { job_id: initialJobId } = await startRes.json() as { job_id: string };
      let jobId = initialJobId;
      currentJobIdRef.current = jobId;

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
          let shouldBreakReader = false;

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              // SSEクローズ = Checkpoint保存完了（mark_done後にクローズされる）
              if (!streamCompleted) {
                const queue = [...messageQueueRef.current];
                if (queue.length > 0) {
                  // メッセージキュー割り込みによる終了 → 新ジョブを開始
                  setMessageQueue([]);
                  messageQueueRef.current = [];
                  const combinedText = queue.join("\n");
                  setMessages(prev => [
                    ...prev,
                    { role: "user" as const, content: combinedText },
                    { role: "assistant" as const, content: "", blocks: [], toolCallBlocks: [] },
                  ]);
                  activeSubagentCallIdRef.current = null;
                  if (!ctrl.signal.aborted) {
                    try {
                      const newStartRes = await fetch("/api/chat/start", {
                        method: "POST",
                        signal: ctrl.signal,
                        headers: {
                          "Content-Type": "application/json",
                          ...(volumePath ? { "x-uc-volume-path": volumePath } : {}),
                        },
                        body: JSON.stringify({
                          input: [{ role: "user", content: combinedText }],
                          stream: true,
                          custom_inputs: {
                            volume_path: volumePath,
                            llm_model: selectedModel,
                            thread_id: threadId,
                          },
                        }),
                      });
                      if (newStartRes.ok) {
                        const { job_id: newJobId } = await newStartRes.json() as { job_id: string };
                        jobId = newJobId;
                        currentJobIdRef.current = newJobId;
                        lastEventId = -1;
                      } else {
                        streamCompleted = true;
                      }
                    } catch {
                      streamCompleted = true;
                    }
                  } else {
                    streamCompleted = true;
                  }
                } else {
                  // 停止ボタンまたは予期しないクローズ → 終了
                  streamCompleted = true;
                }
              }
              break;
            }

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
                        // blocks 配列を更新: 末尾の text ブロックに追記するか、新規作成
                        const currentBlocks = last.blocks ?? [];
                        const lastBlock = currentBlocks[currentBlocks.length - 1];
                        let newBlocks: ChatBlock[];
                        if (lastBlock?.type === "text") {
                          // 末尾が text ブロックなら追記（ブロック数の爆発を防ぐ）
                          newBlocks = [
                            ...currentBlocks.slice(0, -1),
                            { type: "text" as const, content: lastBlock.content + data.delta },
                          ];
                        } else {
                          // 新しい text ブロックを追加
                          newBlocks = [
                            ...currentBlocks,
                            { type: "text" as const, content: data.delta },
                          ];
                        }
                        updated[updated.length - 1] = {
                          ...last,
                          content: (last.content ?? "") + data.delta,  // コピー機能・後方互換のため維持
                          blocks: newBlocks,
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
                  } else if (resolvedType === "stream.timeout") {
                    // バックエンドが 100 秒制限でクローズ → outerLoop が即座に再接続する
                    shouldBreakReader = true;
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
            if (shouldBreakReader) break;
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
          if (last?.role === "assistant" && !last.content && !last.blocks?.length && !last.toolCallBlocks?.length && !last.subAgentBlocks?.length) {
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
      setStopping(false);
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
    // URLから q, files を除去（ブラウザ履歴に残さない）
    navigate({
      to: "/chat/$threadId",
      params: { threadId },
      search: { q: undefined, files: undefined },
      replace: true,
    });
    const filePaths = initialFiles ? initialFiles.split(",").filter(Boolean) : [];
    handleSubmit(initialQuery, filePaths);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  // search.files による添付ファイルの事前設定（q なしで files のみの場合）
  useEffect(() => {
    if (!initialFiles || initialFilesFiredRef.current || initialQueryFiredRef.current) return;
    initialFilesFiredRef.current = true;
    navigate({
      to: "/chat/$threadId",
      params: { threadId },
      search: { q: undefined, files: undefined },
      replace: true,
    });
    const filePaths = initialFiles.split(",").filter(Boolean);
    const attachments: UploadedAttachment[] = filePaths.map((p) => {
      const filename = p.split("/").pop() ?? p;
      const ext = filename.includes(".") ? (filename.split(".").pop()?.toLowerCase() ?? "") : "";
      return { id: nanoid(), filename, virtualPath: p, extension: ext };
    });
    setUploadedAttachments(attachments);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialFiles]);

  // ホーム画面から渡された File オブジェクトをマウント後にアップロード
  useEffect(() => {
    const files = takePendingFiles();
    if (files.length === 0) return;

    // プロビジョナルエントリを即座に追加
    const provisionals: UploadedAttachment[] = files.map((file) => ({
      id: nanoid(),
      filename: file.name,
      virtualPath: "",
      extension: file.name.split(".").pop()?.toLowerCase() ?? "",
      uploading: true,
    }));
    provisionals.forEach((p) => handleAttachmentAdd(p));

    // 並列アップロード
    const currentVolumePath = localStorage.getItem(STORAGE_KEY_VOLUME) ?? "";
    Promise.all(
      files.map(async (file, i) => {
        const provisional = provisionals[i];
        const formData = new FormData();
        formData.append("file", file);
        try {
          const res = await fetch("/api/files/upload-attachment", {
            method: "POST",
            headers: currentVolumePath ? { "x-uc-volume-path": currentVolumePath } : {},
            body: formData,
          });
          if (!res.ok) {
            handleAttachmentUpdate(provisional.id, { uploading: false, error: true });
            return;
          }
          const { path } = (await res.json()) as { path: string };
          handleAttachmentUpdate(provisional.id, { uploading: false, virtualPath: path });
        } catch {
          handleAttachmentUpdate(provisional.id, { uploading: false, error: true });
        }
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <PromptInputProvider>
      <ChatContent
        messages={messages}
        streaming={streaming}
        stopping={stopping}
        isLoadingHistory={isLoadingHistory}
        volumePath={volumePath}
        selectedModel={selectedModel}
        availableModels={availableModels}
        messageQueue={messageQueue}
        onSubmit={handleSubmit}
        onStop={handleStop}
        onRetry={handleRetry}
        onVolumeSelect={handleVolumeSelect}
        onModelChange={handleModelChange}
        onRemoveQueueItem={(index) => {
          setMessageQueue(prev => prev.filter((_, i) => i !== index));
        }}
        uploadedAttachments={uploadedAttachments}
        onAttachmentAdd={handleAttachmentAdd}
        onAttachmentRemove={handleAttachmentRemove}
        onAttachmentUpdate={handleAttachmentUpdate}
      />
    </PromptInputProvider>
  );
}

// ─── Chat Content ─────────────────────────────────────────────────────────────

type ChatContentProps = {
  messages: ChatMessage[];
  streaming: boolean;
  stopping: boolean;
  isLoadingHistory: boolean;
  volumePath: string;
  selectedModel: string;
  availableModels: {id: string; display_name: string}[];
  messageQueue: string[];
  onSubmit: (text: string) => void;
  onStop: () => void;
  onRetry: () => void;
  onVolumeSelect: (vp: string) => void;
  onModelChange: (model: string) => void;
  onRemoveQueueItem: (index: number) => void;
  uploadedAttachments: UploadedAttachment[];
  onAttachmentAdd: (attachment: UploadedAttachment) => void;
  onAttachmentRemove: (id: string) => void;
  onAttachmentUpdate: (id: string, updates: Partial<UploadedAttachment>) => void;
};

function ChatContent({
  messages,
  streaming,
  stopping,
  isLoadingHistory,
  volumePath,
  selectedModel,
  availableModels,
  messageQueue,
  onSubmit,
  onStop,
  onRetry,
  onVolumeSelect,
  onModelChange,
  onRemoveQueueItem,
  uploadedAttachments,
  onAttachmentAdd,
  onAttachmentRemove,
  onAttachmentUpdate,
}: ChatContentProps) {
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false);
  const waitMessageRef = useRef<string>(getRandomWaitMessage());
  const prevStreamingRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const ACCEPTED_EXTENSIONS = [
    ".txt",".md",".html",".htm",".css",".py",".yaml",".yml",".json",".xml",".csv",
    ".js",".ts",".tsx",".jsx",".sh",".sql",".toml",".ini",".conf",".log",".rst",
    ".tex",".r",".rb",".java",".c",".cpp",".h",".go",".rs",".scala",".kt",".swift",
    ".png",".jpg",".jpeg",".gif",".webp",
  ].join(",");

  const MAX_ATTACHMENTS = 20;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (selected.length === 0) return;

    // 20件制限: 追加できる残り枠を計算
    const remaining = MAX_ATTACHMENTS - uploadedAttachments.length;
    if (remaining <= 0) return;
    const files = selected.slice(0, remaining);

    // プロビジョナルエントリを即座に追加
    const provisionals: UploadedAttachment[] = files.map((file) => ({
      id: nanoid(),
      filename: file.name,
      virtualPath: "",
      extension: file.name.split(".").pop()?.toLowerCase() ?? "",
      uploading: true,
    }));
    provisionals.forEach((p) => onAttachmentAdd(p));

    // 並列アップロード
    await Promise.all(
      files.map(async (file, i) => {
        const provisional = provisionals[i];
        const formData = new FormData();
        formData.append("file", file);
        try {
          const res = await fetch("/api/files/upload-attachment", {
            method: "POST",
            headers: volumePath ? { "x-uc-volume-path": volumePath } : {},
            body: formData,
          });
          if (!res.ok) {
            onAttachmentUpdate(provisional.id, { uploading: false, error: true });
            return;
          }
          const { path } = (await res.json()) as { path: string };
          onAttachmentUpdate(provisional.id, { uploading: false, virtualPath: path });
        } catch {
          onAttachmentUpdate(provisional.id, { uploading: false, error: true });
        }
      })
    );
  };

  useEffect(() => {
    if (streaming && !prevStreamingRef.current) {
      waitMessageRef.current = getRandomWaitMessage();
    }
    prevStreamingRef.current = streaming;
  }, [streaming]);

  const allGeneratedFiles = useMemo(() => {
    const seen = new Set<string>();
    for (const msg of messages) {
      if (msg.role === "assistant") {
        for (const f of extractWrittenFiles(msg)) seen.add(f);
      }
    }
    return Array.from(seen);
  }, [messages]);

  const agentTodosGroups = useMemo<AgentTodosGroup[]>(() => {
    const groupMap = new Map<string, AgentTodosGroup>();

    for (const msg of messages) {
      if (!msg.blocks) continue;

      for (const block of msg.blocks) {
        if (block.type === "tool" && block.name === "write_todos") {
          const todos = parseTodos(block.arguments);
          if (todos.length > 0) {
            groupMap.set("main", { agentId: "main", agentType: "Main Agent", todos });
          }
        }

        if (block.type === "subagent") {
          for (const tc of block.toolCalls) {
            if (tc.name === "write_todos") {
              const todos = parseTodos(tc.arguments);
              if (todos.length > 0) {
                groupMap.set(block.agentType, {
                  agentId: block.callId,
                  agentType: block.agentType,
                  todos,
                });
              }
            }
          }
        }
      }
    }

    return Array.from(groupMap.values());
  }, [messages]);

  const handleFormSubmit = ({ text }: { text: string; files: unknown[] }) => {
    onSubmit(text);
  };

  const promptInput = (
    <PromptInput onSubmit={handleFormSubmit}>
      <PromptInputBody>
        <PromptInputTextarea
          placeholder={streaming
            ? "メッセージをキューに追加... (Enter で送信)"
            : "メッセージを入力... (Enter で送信、Shift+Enter で改行)"}
          disabled={isLoadingHistory}
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            type="button"
            title="ファイルを添付"
            onClick={() => fileInputRef.current?.click()}
          >
            <Plus className="size-4" />
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept={ACCEPTED_EXTENSIONS}
            multiple
            onChange={handleFileChange}
          />
          {availableModels.length > 0 && (
            <ModelSelector open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
              <ModelSelectorTrigger asChild>
                <Button variant="outline" className="h-7 text-xs px-2 max-w-[180px] justify-between">
                  <ModelSelectorName>
                    {availableModels.find((m) => m.id === selectedModel)?.display_name ?? "モデル選択"}
                  </ModelSelectorName>
                </Button>
              </ModelSelectorTrigger>
              <ModelSelectorContent>
                <ModelSelectorInput placeholder="モデルを検索..." />
                <ModelSelectorList>
                  <ModelSelectorEmpty>モデルが見つかりません</ModelSelectorEmpty>
                  <ModelSelectorGroup heading="利用可能なモデル">
                    {availableModels.map((m) => (
                      <ModelSelectorItem
                        key={m.id}
                        value={m.id}
                        onSelect={() => {
                          onModelChange(m.id);
                          setModelSelectorOpen(false);
                        }}
                      >
                        <ModelSelectorName>{m.display_name}</ModelSelectorName>
                        {selectedModel === m.id ? (
                          <CheckIcon className="ml-auto size-4" />
                        ) : (
                          <div className="ml-auto size-4" />
                        )}
                      </ModelSelectorItem>
                    ))}
                  </ModelSelectorGroup>
                </ModelSelectorList>
              </ModelSelectorContent>
            </ModelSelector>
          )}
          <VolumeExplorer value={volumePath} onSelect={onVolumeSelect} />
        </PromptInputTools>
        <PromptInputSubmit
          status={stopping ? "submitted" : streaming ? "streaming" : undefined}
          onClick={streaming && !stopping ? onStop : undefined}
        />
      </PromptInputFooter>
    </PromptInput>
  );

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
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
          ) : messages.length === 0 ? (
            <ConversationEmptyState
              title="会話を始めましょう"
              description="メッセージを入力して会話を開始してください。"
              icon={<MessageSquare className="size-6" />}
            />
          ) : messages.map((msg, i) => {
            const isLast = i === messages.length - 1;
            return (
              <Message key={i} from={msg.role}>
                {msg.thinking && (
                  <Reasoning
                    isStreaming={streaming && isLast}
                    defaultOpen={false}
                  >
                    <ReasoningTrigger />
                    <ReasoningContent>{msg.thinking}</ReasoningContent>
                  </Reasoning>
                )}
                {msg.blocks && msg.blocks.length > 0 ? (
                  <div className="space-y-2 w-full">
                    {msg.blocks.map((block, bi) => {
                      if (block.type === "text") {
                        return (
                          <MessageContent key={`text-${bi}`}>
                            <MessageResponse>{block.content}</MessageResponse>
                          </MessageContent>
                        );
                      }
                      if (block.type === "subagent") {
                        return (
                          <SubAgentBlock
                            key={`sa-${bi}`}
                            block={block}
                          />
                        );
                      }
                      // type === "tool"
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
                    {/* ストリーミング中: blocks があるが末尾が text でない場合にスケルトン表示 */}
                    {streaming && isLast && msg.role === "assistant" &&
                      msg.blocks[msg.blocks.length - 1]?.type !== "text" && (
                      <MessageContent>
                        <div className="py-1">
                          <Shimmer className="text-sm" duration={1.5}>
                            {waitMessageRef.current}
                          </Shimmer>
                        </div>
                      </MessageContent>
                    )}
                    {/* blocks 内に text ブロックがない場合は msg.content をフォールバック表示（移行期の旧データ対応） */}
                    {!msg.blocks.some(b => b.type === "text") && msg.content && (
                      <MessageContent>
                        <MessageResponse>{msg.content}</MessageResponse>
                      </MessageContent>
                    )}
                    {/* エラー表示 */}
                    {msg.isError && (
                      <MessageContent>
                        <Alert variant="destructive" className="w-full">
                          <AlertCircle className="h-4 w-4" />
                          <AlertDescription>{msg.content}</AlertDescription>
                        </Alert>
                      </MessageContent>
                    )}
                  </div>
                ) : (
                  // 後方互換: blocks フィールドのない旧保存データ用フォールバック
                  <>
                    {(msg.subAgentBlocks?.length || msg.toolCallBlocks?.length) ? (
                      <div className="space-y-2 w-full">
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
                      </div>
                    ) : null}
                    <MessageContent>
                      {msg.isError ? (
                        <Alert variant="destructive" className="w-full">
                          <AlertCircle className="h-4 w-4" />
                          <AlertDescription>{msg.content}</AlertDescription>
                        </Alert>
                      ) : msg.role === "assistant" && !msg.content && streaming && isLast ? (
                        <div className="py-1">
                          <Shimmer className="text-sm" duration={1.5}>
                            {waitMessageRef.current}
                          </Shimmer>
                        </div>
                      ) : (
                        <MessageResponse>{msg.content}</MessageResponse>
                      )}
                    </MessageContent>
                  </>
                )}
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
      <InfoPanel
        files={allGeneratedFiles}
        volumePath={volumePath}
        todoGroups={agentTodosGroups}
        messageQueue={messageQueue}
        onRemoveQueueItem={onRemoveQueueItem}
        uploadedAttachments={uploadedAttachments}
        onAttachmentRemove={onAttachmentRemove}
      />
      <div className="shrink-0 border-t p-4">
        <div className="max-w-2xl mx-auto">
          {promptInput}
        </div>
      </div>
      </div>

    </div>
  );
}
