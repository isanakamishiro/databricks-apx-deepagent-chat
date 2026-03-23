import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputProvider,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputController,
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
import {
  Suggestion,
  Suggestions,
} from "@/components/ai-elements/suggestion";
import { VolumeExplorer } from "@/components/chat/volume-explorer";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CheckIcon, Eye, Plus, Zap } from "lucide-react";
import { setPendingFiles } from "@/lib/pending-files";
import { getApprovalMode, setApprovalMode, type ApprovalMode } from "@/lib/approval-mode";

export const Route = createFileRoute("/_sidebar/chat/")({
  component: () => <ChatIndexPage />,
});

const STORAGE_KEY_VOLUME = "apx_volume_path";
const STORAGE_KEY_MODEL = "apx_selected_model";

const STARTER_SUGGESTIONS = [
  "Databricksについて調査して",
  "LLMの仕組みを説明して",
  "今週の大阪の天気を調べて",
];

function ChatIndexPage() {
  return (
    <PromptInputProvider>
      <ChatIndexContent />
    </PromptInputProvider>
  );
}

function ChatIndexContent() {
  const navigate = useNavigate();
  const { textInput } = usePromptInputController();
  const [volumePath, setVolumePath] = useState(
    () => localStorage.getItem(STORAGE_KEY_VOLUME) ?? ""
  );
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem(STORAGE_KEY_MODEL) ?? ""
  );
  const [availableModels, setAvailableModels] = useState<{id: string; display_name: string}[]>([]);
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false);
  const [approvalMode, setApprovalModeState] = useState<ApprovalMode>(getApprovalMode);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const ACCEPTED_EXTENSIONS = [
    ".txt",".md",".html",".htm",".css",".py",".yaml",".yml",".json",".xml",".csv",
    ".js",".ts",".tsx",".jsx",".sh",".sql",".toml",".ini",".conf",".log",".rst",
    ".tex",".r",".rb",".java",".c",".cpp",".h",".go",".rs",".scala",".kt",".swift",
    ".png",".jpg",".jpeg",".gif",".webp",
  ].join(",");

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

  const MAX_ATTACHMENTS = 20;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    e.target.value = "";
    const files = selected.slice(0, MAX_ATTACHMENTS);
    if (files.length === 0) return;

    // ファイルをストアに保存して即座にスレッド画面へ遷移
    setPendingFiles(files);
    const threadId = crypto.randomUUID();
    navigate({
      to: "/chat/$threadId",
      params: { threadId },
      search: { q: undefined, files: undefined },
    });
  };

  const goToChat = (text: string) => {
    if (!text.trim()) return;
    const threadId = crypto.randomUUID();
    navigate({
      to: "/chat/$threadId",
      params: { threadId },
      search: { q: text, files: undefined },
    });
  };

  const handleFormSubmit = ({ text }: { text: string; files: unknown[] }) => {
    goToChat(text);
  };

  const handleSuggestionClick = (suggestion: string) => {
    textInput.setInput(suggestion);
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

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 py-8 px-[20%] overflow-auto">
      {!volumePath && (
        <Alert variant="warning" className="w-full max-w-2xl">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Volume Path が未設定です。ツールバーの
            <span className="font-medium">「Volume」</span>
            ボタンから設定してください。
          </AlertDescription>
        </Alert>
      )}
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-bold">Databricks-apx DeepAgent Chat</h1>
        <p className="text-muted-foreground text-sm">Ask me anything.</p>
      </div>
      <div className="flex justify-center w-full max-w-2xl">
        <Suggestions>
          {STARTER_SUGGESTIONS.map((s) => (
            <Suggestion key={s} suggestion={s} onClick={handleSuggestionClick} />
          ))}
        </Suggestions>
      </div>
      <div className="w-full max-w-2xl">
        <PromptInput onSubmit={handleFormSubmit}>
          <PromptInputBody>
            <PromptInputTextarea
              placeholder="メッセージを入力... (Enter で送信、Shift+Enter で改行)"
            />
          </PromptInputBody>
          <PromptInputFooter className="items-end">
            <PromptInputTools className="flex-1 min-w-0 flex-wrap">
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
                              handleModelChange(m.id);
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
              <VolumeExplorer value={volumePath} onSelect={handleVolumeSelect} />
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs gap-1"
                type="button"
                title={approvalMode === "auto" ? "自動承認モード (クリックで確認モードに切替)" : "確認モード (クリックで自動承認に切替)"}
                onClick={() => {
                  const next: ApprovalMode = approvalMode === "auto" ? "ask" : "auto";
                  setApprovalModeState(next);
                  setApprovalMode(next);
                }}
              >
                {approvalMode === "auto" ? <Zap className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                {approvalMode === "auto" ? "Auto" : "Ask"}
              </Button>
            </PromptInputTools>
            <PromptInputSubmit />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
