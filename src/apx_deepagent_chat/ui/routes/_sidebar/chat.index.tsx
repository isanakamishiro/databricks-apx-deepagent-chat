import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
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
import { VolumeExplorer } from "@/components/chat/volume-explorer";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertTriangle } from "lucide-react";

export const Route = createFileRoute("/_sidebar/chat/")({
  component: () => <ChatIndexPage />,
});

const STORAGE_KEY_VOLUME = "apx_volume_path";
const STORAGE_KEY_MODEL = "apx_selected_model";

const STARTER_SUGGESTIONS = [
  "Databricksについて調査して",
  "LLMの仕組みを説明して",
  "大阪の今週の天気予報を報告して",
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

  const goToChat = (text: string) => {
    if (!text.trim()) return;
    const threadId = crypto.randomUUID();
    navigate({
      to: "/chat/$threadId",
      params: { threadId },
      search: { q: text },
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
        <h1 className="text-2xl font-bold">APX DeepAgent Chat</h1>
        <p className="text-muted-foreground text-sm">何でも聞いてください</p>
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
          <PromptInputFooter>
            <PromptInputTools>
              {availableModels.length > 0 && (
                <PromptInputSelect
                  value={selectedModel}
                  onValueChange={handleModelChange}
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
              <VolumeExplorer value={volumePath} onSelect={handleVolumeSelect} />
            </PromptInputTools>
            <PromptInputSubmit />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
