import { useState } from 'react';
import { ChevronRight, ChevronDown, Database, Folder, FolderOpen, HardDrive } from 'lucide-react';
import { Button } from '@/components/ui/button';
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

export function VolumeExplorer({ value, onSelect }: VolumeExplorerProps) {
  const [open, setOpen] = useState(false);
  const [pendingPath, setPendingPath] = useState(value);

  const [catalogs, setCatalogs] = useState<Entry[]>([]);
  const [catalogState, setCatalogState] = useState<LoadState>('idle');
  const [schemas, setSchemas] = useState<Record<string, { state: LoadState; data: Entry[] }>>({});
  const [volumes, setVolumes] = useState<Record<string, { state: LoadState; data: Entry[] }>>({});

  const volumeName = value ? value.split('/').pop() : undefined;

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

  const loadVolumes = async (catalog: string, schema: string) => {
    const key = `${catalog}/${schema}`;
    if (volumes[key]?.state === 'loaded' || volumes[key]?.state === 'loading') return;
    setVolumes((p) => ({ ...p, [key]: { state: 'loading', data: [] } }));
    try {
      const res = await fetch(
        `/api/volumes/volumes?catalog=${encodeURIComponent(catalog)}&schema=${encodeURIComponent(schema)}`
      );
      if (!res.ok) throw new Error('Failed');
      const data: Entry[] = await res.json();
      setVolumes((p) => ({ ...p, [key]: { state: 'loaded', data } }));
    } catch {
      setVolumes((p) => ({ ...p, [key]: { state: 'error', data: [] } }));
    }
  };

  const handleDialogOpen = (isOpen: boolean) => {
    setOpen(isOpen);
    if (isOpen) {
      setPendingPath(value);
      loadCatalogs();
    }
  };

  return (
    <>
      <Button
        variant={volumeName ? 'outline' : 'ghost'}
        size="sm"
        className={cn('h-7 text-xs gap-1', volumeName && 'border-primary text-primary')}
        onClick={() => handleDialogOpen(true)}
      >
        <Database size={12} />
        {volumeName ?? 'Volume'}
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
              <Files>
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
                        schemas[cat.name].data.map((sc) => (
                          <FolderItem key={sc.name} value={`${cat.name}/${sc.name}`}>
                            <FolderHeader onClick={() => loadVolumes(cat.name, sc.name)}>
                              <FolderTrigger
                                className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-accent"
                              >
                                <FolderIcon
                                  closeIcon={<ChevronRight size={12} />}
                                  openIcon={<ChevronDown size={12} />}
                                />
                                <FolderLabel>{sc.name}</FolderLabel>
                              </FolderTrigger>
                            </FolderHeader>
                            <FolderPanel className="ml-5 border-l pl-2">
                              {(() => {
                                const key = `${cat.name}/${sc.name}`;
                                const vs = volumes[key];
                                if (vs?.state === 'loading')
                                  return (
                                    <div className="space-y-1 py-1">
                                      <Skeleton className="h-4 w-full" />
                                      <Skeleton className="h-4 w-3/4" />
                                    </div>
                                  );
                                if (vs?.state === 'error')
                                  return <p className="text-destructive py-1 text-xs">取得に失敗しました</p>;
                                if (vs?.state === 'loaded' && vs.data.length === 0)
                                  return (
                                    <p className="text-muted-foreground py-1 text-xs">ボリュームがありません</p>
                                  );
                                return vs?.data.map((vol) => {
                                  const path = `/Volumes/${cat.name}/${sc.name}/${vol.name}`;
                                  const isSelected = pendingPath === path;
                                  return (
                                    <FileHighlight key={vol.name}>
                                      <File
                                        className={cn(
                                          'flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 hover:bg-accent',
                                          isSelected && 'bg-primary/10 font-medium text-primary'
                                        )}
                                        onClick={() => setPendingPath(path)}
                                      >
                                        <HardDrive size={13} />
                                        <FileLabel>{vol.name}</FileLabel>
                                        {isSelected && <span className="ml-auto text-xs">✓</span>}
                                      </File>
                                    </FileHighlight>
                                  );
                                });
                              })()}
                            </FolderPanel>
                          </FolderItem>
                        ))}
                    </FolderPanel>
                  </FolderItem>
                ))}
              </Files>
            )}
          </div>

          {pendingPath && (
            <p className="truncate text-xs text-green-600">📍 {pendingPath}</p>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              キャンセル
            </Button>
            <Button
              onClick={() => {
                onSelect(pendingPath);
                setOpen(false);
              }}
              disabled={!pendingPath}
            >
              選択
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
