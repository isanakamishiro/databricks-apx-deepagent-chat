import { X } from "lucide-react";
import {
  FileText,
  FileCode,
  FileJson,
  Image,
  Table,
  File,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type UploadedAttachment = {
  id: string;
  filename: string;
  virtualPath: string;
  extension: string; // 拡張子（ドットなし、小文字）例: "py", "png"
};

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp"]);
const SPREADSHEET_EXTS = new Set(["csv"]);
const DATA_EXTS = new Set(["json", "xml", "yaml", "yml", "toml", "ini", "conf"]);
const CODE_EXTS = new Set([
  "py", "js", "ts", "tsx", "jsx", "html", "htm", "css", "sh",
  "sql", "r", "rb", "java", "c", "cpp", "h", "go", "rs",
  "scala", "kt", "swift",
]);

function FileTypeIcon({ extension, className }: { extension: string; className?: string }) {
  const ext = extension.toLowerCase();
  const cls = cn("size-3.5 shrink-0", className);

  if (IMAGE_EXTS.has(ext)) return <Image className={cls} />;
  if (SPREADSHEET_EXTS.has(ext)) return <Table className={cls} />;
  if (DATA_EXTS.has(ext)) return <FileJson className={cls} />;
  if (CODE_EXTS.has(ext)) return <FileCode className={cls} />;
  if (["txt", "md", "rst", "tex", "log"].includes(ext)) return <FileText className={cls} />;
  return <File className={cls} />;
}

type AttachmentPanelProps = {
  attachments: UploadedAttachment[];
  onRemove: (id: string) => void;
  className?: string;
};

export function AttachmentPanel({ attachments, onRemove, className }: AttachmentPanelProps) {
  if (attachments.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap items-center gap-2 pb-2", className)}>
      {attachments.map((attachment) => (
        <div
          key={attachment.id}
          className="flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-1 text-xs font-medium text-foreground"
        >
          <FileTypeIcon extension={attachment.extension} className="text-muted-foreground" />
          <span className="max-w-[160px] truncate">{attachment.filename}</span>
          <button
            type="button"
            onClick={() => onRemove(attachment.id)}
            className="ml-0.5 text-muted-foreground hover:text-foreground transition-colors"
            aria-label={`${attachment.filename} を削除`}
          >
            <X className="size-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
