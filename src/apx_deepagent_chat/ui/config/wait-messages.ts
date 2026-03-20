// ストリーミング待機中に表示するメッセージパターン
export const WAIT_MESSAGES: string[] = [
  "考えています...",
  "分析中です...",
  "処理を実行しています...",
  "情報を整理しています...",
  "回答を準備しています...",
  "ツールを実行しています...",
  "データを確認しています...",
  "少々お待ちください...",
];

export function getRandomWaitMessage(): string {
  return WAIT_MESSAGES[Math.floor(Math.random() * WAIT_MESSAGES.length)];
}
