export type ApprovalMode = "auto" | "ask";

const STORAGE_KEY = "apx_approval_mode";

export const getApprovalMode = (): ApprovalMode =>
  (localStorage.getItem(STORAGE_KEY) as ApprovalMode) ?? "ask";

export const setApprovalMode = (mode: ApprovalMode): void =>
  localStorage.setItem(STORAGE_KEY, mode);
