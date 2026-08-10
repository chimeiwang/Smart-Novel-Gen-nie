"use client";

import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

type WorkspaceDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  variant: "library" | "review" | "compact";
  closeDisabled?: boolean;
  onClose: () => void;
  children: ReactNode;
};

export function WorkspaceDialog({
  open,
  title,
  description,
  variant,
  closeDisabled = false,
  onClose,
  children,
}: WorkspaceDialogProps) {
  useEffect(() => {
    if (!open || closeDisabled) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeDisabled, onClose, open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="workspace-dialog-overlay"
      onMouseDown={() => {
        if (!closeDisabled) onClose();
      }}
    >
      <section
        className={`workspace-dialog-panel ${variant}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="workspace-dialog-header">
          <div>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button
            className="workspace-dialog-close"
            type="button"
            onClick={onClose}
            disabled={closeDisabled}
            aria-label={closeDisabled ? "操作进行中，暂不能关闭" : "关闭"}
          >
            ×
          </button>
        </header>
        <div className="workspace-dialog-body">{children}</div>
      </section>
    </div>,
    document.body,
  );
}
