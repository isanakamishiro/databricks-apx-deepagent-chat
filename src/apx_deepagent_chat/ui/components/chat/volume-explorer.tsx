import { useState } from 'react';
import { ChevronRight, ChevronDown, Database, Folder, FolderOpen, HardDrive } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Files,
  FilesHighlight,
  FolderItem,
  FolderHeader,
  FolderTrigger,
  FolderPanel,
  FolderIcon,
  FolderLabel,
  FileHighlight,
  File,
  FileLabel,
} from '@/components/animate-ui/primitives-base-files';
import { cn } from '@/lib/utils';

type LoadState = 'idle' | 'loading' | 'loaded' | 'error';

type Entry = { name: string };

type VolumeExplorerProps = {
  value: string;
  onSelect: (path: string) => void;
};

function parsePath(path: string): { catalog: string; schema: string; volume: string } | null {
  const m = path.match(/^\/Volumes\/([^/]+)\/([^/]+)\/([^/]+)$/);
  if (!m) return null;
  return { catalog: m[1], schema: m[2], volume: m[3] };
}

export function VolumeExplorer({ value, onSelect }: VolumeExplorerProps) {
  const [open, setOpen] = useState(false);
  const [openFolders, setOpenFolders] = useState<string[]>([]);

  const [selectedCatalog, setSelectedCatalog] = useState<string | null>(null);
  const [selectedSchema, setSelectedSchema] = useState<string | null>(null);
  const [volumeName, setVolumeName] = useState('');
  const [validateState, setValidateState] = useState<'idle' | 'validating' | 'error'>('idle');
  const [validateError, setValidateError] = useState('');

  const [catalogs, setCatalogs] = useState<Entry[]>([]);
  const [catalogState, setCatalogState] = useState<LoadState>('idle');
  const [schemas, setSchemas] = useState<Record<string, { state: LoadState; data: Entry[] }>>({});

  const pendingPath =
    selectedCatalog && selectedSchema && volumeName.trim()
      ? `/Volumes/${selectedCatalog}/${selectedSchema}/${volumeName.trim()}`
      : '';

  const loadCatalogs = async () => {
    if (catalogState !== 'idle') return;
    setCatalogState('loading');
    try {
      const res = await fetch('/api/volumes/catalogs');
      if (!res.ok) throw new Error('Failed');
      const data: Entry[] = await res.json();
      setCatalogs(data);
      setCatalogState('loaded');
    } catch {
      setCatalogState('error');
    }
  };

  const loadSchemas = async (catalog: string) => {
    if (schemas[catalog]?.state === 'loaded' || schemas[catalog]?.state === 'loading') return;
    setSchemas((p) => ({ ...p, [catalog]: { state: 'loading', data: [] } }));
    try {
      const res = await fetch(`/api/volumes/schemas?catalog=${encodeURIComponent(catalog)}`);
      if (!res.ok) throw new Error('Failed');
      const data: Entry[] = await res.json();
      setSchemas((p) => ({ ...p, [catalog]: { state: 'loaded', data } }));
    } catch {
      setSchemas((p) => ({ ...p, [catalog]: { state: 'error', data: [] } }));
    }
  };

  const handleDialogOpen = async (isOpen: boolean) => {
    setOpen(isOpen);
    if (isOpen) {
      const parsed = parsePath(value);
      setSelectedCatalog(parsed?.catalog ?? null);
      setSelectedSchema(parsed?.schema ?? null);
      setVolumeName(parsed?.volume ?? '');
      setValidateState('idle');
      setValidateError('');
      await loadCatalogs();
      if (parsed) {
        setOpenFolders([parsed.catalog, `${parsed.catalog}/${parsed.schema}`]);
        await loadSchemas(parsed.catalog);
      } else {
        setOpenFolders([]);
      }
    }
  };

  const handleSelect = async () => {
    if (!pendingPath) return;
    setValidateState('validating');
    try {
      const url = `/api/volumes/validate?catalog=${encodeURIComponent(selectedCatalog!)}&schema=${encodeURIComponent(selectedSchema!)}&volume=${encodeURIComponent(volumeName.trim())}`;
      const res = await fetch(url);
      if (res.status === 404) {
        setValidateState('error');
        setValidateError('ボリュームが見つかりません。名前を確認してください。');
        return;
      }
      if (res.status === 403) {
        setValidateState('error');
        setValidateError('このボリュームへのアクセス権限がありません。');
        return;
      }
      if (!res.ok) {
        setValidateState('error');
        setValidateError('ボリュームの確認中にエラーが発生しました。');
        return;
      }
      onSelect(pendingPath);
      setOpen(false);
    } catch {
      setValidateState('error');
      setValidateError('ネットワークエラーが発生しました。');
    }
  };

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className={cn(
          'h-7 text-xs gap-1 max-w-xs border-none bg-transparent font-medium text-muted-foreground shadow-none transition-colors hover:bg-accent hover:text-foreground',
          value && 'text-foreground'
        )}
        onClick={() => handleDialogOpen(true)}
      >
        <Database size={12} />
        <span className="truncate">{value || '未選択'}</span>
      </Button>
      <Dialog open={open} onOpenChange={handleDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>ボリュームを選択</DialogTitle>
          </DialogHeader>

          <div className="min-h-[200px] max-h-[350px] overflow-y-auto border rounded-md p-2 text-sm">
            {catalogState === 'loading' && (
              <div className="space-y-2 p-2">
                <Skeleton className="h-5 w-full" />
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-5 w-5/6" />
              </div>
            )}
            {catalogState === 'error' && (
              <p className="text-destructive p-2 text-xs">カタログの取得に失敗しました</p>
            )}
            {catalogState === 'loaded' && catalogs.length === 0 && (
              <p className="text-muted-foreground p-2 text-xs">アクセス可能なカタログがありません</p>
            )}
            {catalogState === 'loaded' && catalogs.length > 0 && (
              <FilesHighlight>
              <Files open={openFolders} onOpenChange={setOpenFolders}>
                {catalogs.map((cat) => (
                  <FolderItem key={cat.name} value={cat.name}>
                    <FolderHeader onClick={() => loadSchemas(cat.name)}>
                      <FolderTrigger
                        className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-accent"
                      >
                        <FolderIcon
                          closeIcon={<ChevronRight size={12} />}
                          openIcon={<ChevronDown size={12} />}
                        />
                        <FolderIcon
                          closeIcon={<Folder size={13} className="text-yellow-500" />}
                          openIcon={<FolderOpen size={13} className="text-yellow-500" />}
                        />
                        <FolderLabel>{cat.name}</FolderLabel>
                      </FolderTrigger>
                    </FolderHeader>
                    <FolderPanel className="ml-5 border-l pl-2">
                      {schemas[cat.name]?.state === 'loading' && (
                        <div className="space-y-1 py-1">
                          <Skeleton className="h-4 w-full" />
                          <Skeleton className="h-4 w-3/4" />
                        </div>
                      )}
                      {schemas[cat.name]?.state === 'error' && (
                        <p className="text-destructive py-1 text-xs">取得に失敗しました</p>
                      )}
                      {schemas[cat.name]?.state === 'loaded' && schemas[cat.name].data.length === 0 && (
                        <p className="text-muted-foreground py-1 text-xs">スキーマがありません</p>
                      )}
                      {schemas[cat.name]?.state === 'loaded' &&
                        schemas[cat.name].data.map((sc) => {
                          const isSelected = selectedCatalog === cat.name && selectedSchema === sc.name;
                          return (
                            <FileHighlight key={sc.name}>
                              <File
                                className={cn(
                                  'flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 hover:bg-accent',
                                  isSelected && 'bg-primary/10 font-medium text-primary'
                                )}
                                onClick={() => {
                                  setSelectedCatalog(cat.name);
                                  setSelectedSchema(sc.name);
                                  setVolumeName('');
                                  setValidateState('idle');
                                  setValidateError('');
                                }}
                              >
                                <Database size={13} />
                                <FileLabel>{sc.name}</FileLabel>
                                {isSelected && <span className="ml-auto text-xs">✓</span>}
                              </File>
                            </FileHighlight>
                          );
                        })}
                    </FolderPanel>
                  </FolderItem>
                ))}
              </Files>
              </FilesHighlight>
            )}
          </div>

          {selectedCatalog && selectedSchema && (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">
                ボリューム名
              </label>
              <div className="flex items-center gap-1.5">
                <HardDrive size={13} className="text-muted-foreground shrink-0" />
                <Input
                  className="h-7 text-xs"
                  placeholder="volume_name"
                  value={volumeName}
                  onChange={(e) => {
                    setVolumeName(e.target.value);
                    setValidateState('idle');
                    setValidateError('');
                  }}
                />
              </div>
              {validateState === 'error' && (
                <p className="text-destructive text-xs">{validateError}</p>
              )}
            </div>
          )}

          {pendingPath && (
            <p className="truncate text-xs text-foreground/70">📍 {pendingPath}</p>
          )}

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              {value && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => {
                    onSelect('');
                    setOpen(false);
                  }}
                >
                  選択を解除
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>
                キャンセル
              </Button>
              <Button
                onClick={handleSelect}
                disabled={!pendingPath || validateState === 'validating'}
              >
                {validateState === 'validating' ? '確認中...' : '選択'}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
