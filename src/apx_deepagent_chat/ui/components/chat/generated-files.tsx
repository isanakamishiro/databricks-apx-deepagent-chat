import { Download, FileText, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";

const PAGE_SIZE = 10;

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
  const totalPages = Math.ceil(files.length / PAGE_SIZE);
  const [currentPage, setCurrentPage] = useState(totalPages);

  // 新規ファイル追加時は最終ページへ移動
  useEffect(() => {
    setCurrentPage(Math.ceil(files.length / PAGE_SIZE));
  }, [files.length]);

  if (files.length === 0) return null;

  const startIdx = (currentPage - 1) * PAGE_SIZE;
  const pageFiles = files.slice(startIdx, startIdx + PAGE_SIZE);
  const showPaging = files.length > PAGE_SIZE;

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
        <FileText className="size-3.5" />
        生成されたファイル
        {showPaging && (
          <span className="ml-auto text-xs font-normal">
            {currentPage} / {totalPages}
          </span>
        )}
      </div>
      <ul className="space-y-1">
        {pageFiles.map((file) => (
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
      {showPaging && (
        <div className="mt-2 flex items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => p - 1)}
          >
            <ChevronLeft className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            disabled={currentPage >= totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
          >
            <ChevronRight className="size-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}
