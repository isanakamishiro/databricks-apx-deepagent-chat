import { Download, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

type GeneratedFilesProps = {
  files: string[];
  volumePath: string;
};

async function downloadFile(path: string, volumePath: string) {
  const res = await fetch(
    `/api/files/download?path=${encodeURIComponent(path)}`,
    { headers: { "x-uc-volume-path": volumePath } }
  );
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = path.split("/").pop() ?? "file";
  a.click();
  URL.revokeObjectURL(url);
}

export function GeneratedFiles({ files, volumePath }: GeneratedFilesProps) {
  if (files.length === 0) return null;

  return (
    <div className="mt-3 rounded-lg border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
        <FileText className="size-3.5" />
        生成されたファイル
      </div>
      <ul className="space-y-1">
        {files.map((file) => (
          <li key={file} className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-xs text-foreground">
              {file}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              title="ダウンロード"
              onClick={() => downloadFile(file, volumePath)}
            >
              <Download className="size-3.5" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
