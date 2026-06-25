"use client";

import { ReactNode } from "react";

type ModalProps = {
  title: string;
  description?: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

export function Modal({ title, description, open, onClose, children }: ModalProps) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="title-md">{title}</h2>
            {description ? <p className="muted">{description}</p> : null}
          </div>
          <button
            className="button ghost"
            type="button"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
        <div className="modal-body">
          {children}
        </div>
      </div>

      <style jsx>{`
        .modal-wide {
          width: min(900px, 100%);
          max-height: calc(100vh - 48px);
        }
      `}</style>
    </div>
  );
}
