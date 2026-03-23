import {
  Confirmation,
  ConfirmationAccepted,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRejected,
  ConfirmationRequest,
  ConfirmationTitle,
} from "@/components/ai-elements/confirmation";
import { Check, X, Zap } from "lucide-react";

export type ToolApprovalState = "approval-requested" | "approval-responded";

export type ToolApprovalProps = {
  toolName: string;
  toolArgs: Record<string, unknown>;
  state: ToolApprovalState;
  approved?: boolean;
  onApprove: () => void;
  onReject: () => void;
  onAlwaysApprove: () => void;
};

export function ToolApproval({
  toolName,
  toolArgs,
  state,
  approved,
  onApprove,
  onReject,
  onAlwaysApprove,
}: ToolApprovalProps) {
  const firstArgEntry = Object.entries(toolArgs)[0];
  const argPreview = firstArgEntry
    ? (() => {
        const v =
          typeof firstArgEntry[1] === "string"
            ? firstArgEntry[1]
            : JSON.stringify(firstArgEntry[1]);
        return v.length > 120 ? v.slice(0, 120) + "…" : v;
      })()
    : undefined;

  return (
    <Confirmation
      approval={
        state === "approval-responded"
          ? { id: toolName, approved: approved ?? false }
          : { id: toolName }
      }
      state={state}
      className="w-full"
    >
      <ConfirmationRequest>
        <ConfirmationTitle>
          <span className="font-semibold">{toolName}</span>
          {argPreview && (
            <span className="ml-2 text-muted-foreground text-xs">{argPreview}</span>
          )}
        </ConfirmationTitle>
      </ConfirmationRequest>

      <ConfirmationAccepted>
        <ConfirmationTitle>
          <Check className="inline-block mr-1 h-3.5 w-3.5 text-green-500" />
          <span className="font-semibold">{toolName}</span> — 承認済み
        </ConfirmationTitle>
      </ConfirmationAccepted>

      <ConfirmationRejected>
        <ConfirmationTitle>
          <X className="inline-block mr-1 h-3.5 w-3.5 text-red-500" />
          <span className="font-semibold">{toolName}</span> — 拒否済み
        </ConfirmationTitle>
      </ConfirmationRejected>

      <ConfirmationActions>
        <ConfirmationAction variant="outline" onClick={onReject}>
          <X className="mr-1 h-3.5 w-3.5" />
          拒否
        </ConfirmationAction>
        <ConfirmationAction variant="outline" onClick={onAlwaysApprove}>
          <Zap className="mr-1 h-3.5 w-3.5" />
          常に承認
        </ConfirmationAction>
        <ConfirmationAction onClick={onApprove}>
          <Check className="mr-1 h-3.5 w-3.5" />
          承認
        </ConfirmationAction>
      </ConfirmationActions>
    </Confirmation>
  );
}
