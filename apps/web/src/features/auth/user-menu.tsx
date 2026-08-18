"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useRef, useCallback, useEffect } from "react";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";

import "./user-menu.css";

interface UserInfoBarProps {
  username: string;
  creditBalance: string;
}

/**
 * 可拖动的用户信息栏（姓名 + 积分余额）
 * 退出按钮在各页面的 header 中独立显示
 */
export function UserInfoBar({ username, creditBalance }: UserInfoBarProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef({ isDragging: false, startX: 0, startY: 0, left: 0, top: 0 });
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let frameId: number | null = null;
    try {
      const saved = localStorage.getItem("user-menu-position");
      if (saved) {
        frameId = window.requestAnimationFrame(() => {
          setPosition(JSON.parse(saved));
        });
      }
    } catch { /* ignore */ }
    return () => {
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("[data-no-drag]")) return;
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    dragRef.current = { isDragging: true, startX: e.clientX, startY: e.clientY, left: rect.left, top: rect.top };
    el.setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current.isDragging) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPosition({
      x: Math.max(0, Math.min(window.innerWidth - 220, dragRef.current.left + dx)),
      y: Math.max(0, Math.min(window.innerHeight - 40, dragRef.current.top + dy)),
    });
  }, []);

  const handlePointerUp = useCallback(() => {
    if (!dragRef.current.isDragging) return;
    dragRef.current.isDragging = false;
    if (position) localStorage.setItem("user-menu-position", JSON.stringify(position));
  }, [position]);

  const style: React.CSSProperties = position
    ? { position: "fixed", left: position.x, top: position.y, zIndex: 49 }
    : { position: "fixed", top: 16, right: 16, zIndex: 49 };

  return (
    <div
      ref={menuRef}
      className={`user-info-bar${expanded ? " expanded" : ""}`}
      style={style}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <div className="user-info-bar-row">
        <span className="user-info-drag" aria-hidden="true">⠿</span>
        <span className="user-info-name">{username}</span>
        <button
          className="user-info-cost"
          type="button"
          data-no-drag
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          余额 {creditBalance} 积分
        </button>
      </div>
      {expanded && (
        <div className="user-info-credit-details" data-no-drag>
          <span>AI 调用会按 DeepSeek v4 flash 实际用量扣除积分。</span>
          <Link href="/billing" className="user-info-link">
            充值
          </Link>
        </div>
      )}
    </div>
  );
}

/** 退出按钮（放在页面 header 中） */
export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  const handleLogout = async () => {
    setPending(true);
    try {
      requireApiData(await browserApi.POST("/api/v1/auth/logout"));
      router.push("/login");
      router.refresh();
    } finally {
      setPending(false);
    }
  };

  return (
    <button className="button ghost sm" type="button" onClick={handleLogout} disabled={pending}>
      {pending ? "退出中..." : "退出"}
    </button>
  );
}

// 兼容旧引用
export function UserMenu(props: UserInfoBarProps) {
  return <UserInfoBar {...props} />;
}
