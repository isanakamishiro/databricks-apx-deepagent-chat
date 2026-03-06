import { useEffect, useState } from "react";
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

type SettingsDialogProps = {
  volumePath: string;
  selectedModel: string;
  availableModels: string[];
  onSave: (volumePath: string, model: string) => void;
};

export function SettingsDialog({
  volumePath,
  selectedModel,
  availableModels,
  onSave,
}: SettingsDialogProps) {
  const [open, setOpen] = useState(false);
  const [localVolumePath, setLocalVolumePath] = useState(volumePath);
  const [localModel, setLocalModel] = useState(selectedModel);

  useEffect(() => {
    setLocalVolumePath(volumePath);
    setLocalModel(selectedModel);
  }, [volumePath, selectedModel]);

  const handleSave = () => {
    onSave(localVolumePath.trim(), localModel);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" title="設定">
          <Settings size={18} />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>チャット設定</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">UC Volume Path</label>
            <Input
              placeholder="/Volumes/catalog/schema/volume"
              value={localVolumePath}
              onChange={(e) => setLocalVolumePath(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              チャット履歴・ファイルの保存先 Volume パス
            </p>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">モデル</label>
            <select
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
              value={localModel}
              onChange={(e) => setLocalModel(e.target.value)}
            >
              {availableModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <Button className="w-full" onClick={handleSave}>
            保存
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
