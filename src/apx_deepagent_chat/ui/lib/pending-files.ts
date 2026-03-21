/**
 * ホーム画面からスレッド画面へのファイル受け渡し用一時ストア。
 * ナビゲーション直前に set し、スレッド画面マウント時に take する。
 */
let pendingFiles: File[] = [];

export function setPendingFiles(files: File[]): void {
  pendingFiles = files;
}

export function takePendingFiles(): File[] {
  const files = pendingFiles;
  pendingFiles = [];
  return files;
}
