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
  onSave: (volumePath: string) => void;
};

export function SettingsDialog({
  volumePath,
  onSave,
}: SettingsDialogProps) {
  const [open, setOpen] = useState(false);
  const [localVolumePath, setLocalVolumePath] = useState(volumePath);

  useEffect(() => {
    setLocalVolumePath(volumePath);
  }, [volumePath]);

  const handleSave = () => {
    onSave(localVolumePath.trim());
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
          <Button className="w-full" onClick={handleSave}>
            保存
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
