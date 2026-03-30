/**
 * ホーム画面でナビゲーション前に開始したチャットジョブの受け渡し用一時ストア。
 * ナビゲーション直前に set し、スレッド画面マウント時に take する。
 */
type PendingChatJob = {
  threadId: string;
  jobId: string;
  userText: string;
};

let pendingChatJob: PendingChatJob | null = null;

export function setPendingChatJob(job: PendingChatJob): void {
  pendingChatJob = job;
}

export function takePendingChatJob(): PendingChatJob | null {
  const job = pendingChatJob;
  pendingChatJob = null;
  return job;
}
