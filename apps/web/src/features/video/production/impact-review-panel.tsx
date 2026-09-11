"use client";

import { useEffect, useState } from "react";

import { ApiResponseError } from "@/lib/api/response";
import { commandResultIsUnknown, loadLocalDraft, saveLocalDraft } from "./episode-api";
import { registerEpisodeSave } from "./episode-save-navigation";
import { impactDecisionNotesComplete, rebaseImpactDecisions } from "./impact-review-state";
import {
  decideImpactReview,
  getImpactReview,
  listImpactReviews,
  loadPendingImpactDecision,
  type PendingImpactDecision,
} from "./production-api";
import type { ImpactDecision, ImpactReview, ImpactReviewList } from "./types";

type StoredDecisionDraft = {
  reviewId: string;
  basedOnRevision: number;
  decisions: ImpactDecision[];
  editedItemIds: string[];
};

const actionLabels: Record<ImpactDecision["action"], string> = {
  keep_existing: "沿用现有成果",
  revise_target: "安排修订受影响目标",
  not_applicable: "确认与本目标无关",
  defer: "暂缓决定",
};

const errorText = (failure: unknown) => failure instanceof Error ? failure.message : "影响复核操作失败";

export function ImpactReviewPanel({ episodeId, projectId, novelId, enabled }: { episodeId: string; projectId: string; novelId: string; enabled: boolean }) {
  const [status, setStatus] = useState<"pending" | "resolved">("pending");
  const [page, setPage] = useState<ImpactReviewList | null>(null);
  const [review, setReview] = useState<ImpactReview | null>(null);
  const [decisions, setDecisions] = useState<ImpactDecision[]>([]);
  const [editedItemIds, setEditedItemIds] = useState<Set<string>>(new Set());
  const [basedOnRevision, setBasedOnRevision] = useState<number | null>(null);
  const [conflictRemote, setConflictRemote] = useState<ImpactReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingStorage = `inkforge:episode-impact-command:${episodeId}`;
  const draftStorage = review ? `inkforge:episode-impact-draft:${review.id}` : null;
  const [pending, setPending] = useState<PendingImpactDecision | null>(() => loadPendingImpactDecision(pendingStorage));
  const dirty = editedItemIds.size > 0;

  useEffect(() => {
    let alive = true;
    void listImpactReviews(episodeId, status).then(async (result) => {
      if (!alive) return;
      setPage(result);
      const first = result.reviews[0];
      if (!first) { setReview(null); setDecisions([]); setEditedItemIds(new Set()); return; }
      const exact = await getImpactReview(episodeId, first.id);
      if (alive) applyRemote(exact);
    }).catch((failure) => { if (alive) setError(errorText(failure)); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [episodeId, status]);

  useEffect(() => registerEpisodeSave({
    novelId,
    episodeId: `${episodeId}:impact`,
    pending: () => dirty || Boolean(loadPendingImpactDecision(pendingStorage)),
    flush: async () => {
      if (loadPendingImpactDecision(pendingStorage)) throw new Error("影响决定结果尚未核对");
      if (dirty) throw new Error("影响复核有尚未保存的明确决定");
    },
  }), [dirty, episodeId, novelId, pendingStorage]);

  useEffect(() => {
    if (!draftStorage) return;
    if (!dirty || basedOnRevision === null || !review) { saveLocalDraft(draftStorage, null); return; }
    saveLocalDraft(draftStorage, { reviewId: review.id, basedOnRevision, decisions, editedItemIds: [...editedItemIds] } satisfies StoredDecisionDraft);
  }, [basedOnRevision, decisions, dirty, draftStorage, editedItemIds, review]);

  function applyRemote(value: ImpactReview) {
    const stored = loadLocalDraft<StoredDecisionDraft>(`inkforge:episode-impact-draft:${value.id}`);
    setReview(value);
    if (stored?.reviewId === value.id && Array.isArray(stored.decisions) && Array.isArray(stored.editedItemIds)) {
      setDecisions(stored.decisions);
      setEditedItemIds(new Set(stored.editedItemIds));
      setBasedOnRevision(stored.basedOnRevision);
      setConflictRemote(stored.basedOnRevision === value.revision ? null : value);
    } else {
      setDecisions(value.decisions);
      setEditedItemIds(new Set());
      setBasedOnRevision(value.revision);
      setConflictRemote(null);
    }
  }

  const selectReview = async (reviewId: string) => {
    if (reviewId === review?.id) return;
    if (dirty && !window.confirm("放弃当前报告尚未保存的决定，并查看另一份影响报告？")) return;
    if (draftStorage) saveLocalDraft(draftStorage, null);
    setLoading(true);
    setError(null);
    try { applyRemote(await getImpactReview(episodeId, reviewId)); }
    catch (failure) { setError(errorText(failure)); }
    finally { setLoading(false); }
  };

  const changeDecision = (itemId: string, patch: Partial<ImpactDecision>) => {
    const existing = decisions.find((decision) => decision.itemId === itemId);
    const next: ImpactDecision = { itemId, action: existing?.action ?? "defer", note: existing?.note ?? "", ...patch };
    setDecisions((current) => [...current.filter((decision) => decision.itemId !== itemId), next]);
    setEditedItemIds((current) => new Set(current).add(itemId));
  };

  const submit = async (recovering = false) => {
    if (busy || (!recovering && (!review || review.isStale || conflictRemote || !impactDecisionNotesComplete(decisions)))) return;
    const command = recovering ? pending : review ? { reviewId: review.id, body: { clientRequestId: crypto.randomUUID(), expectedRevision: basedOnRevision ?? review.revision, decisions } } : null;
    if (!command || !command.body.decisions.length) return;
    setBusy(true);
    setError(null);
    saveLocalDraft(pendingStorage, command);
    setPending(command);
    try {
      const result = await decideImpactReview(episodeId, projectId, command, recovering);
      saveLocalDraft(pendingStorage, null);
      saveLocalDraft(`inkforge:episode-impact-draft:${result.id}`, null);
      setPending(null);
      setReview(result);
      setDecisions(result.decisions);
      setEditedItemIds(new Set());
      setBasedOnRevision(result.revision);
      setPage((current) => current ? { ...current, reviews: current.reviews.map((item) => item.id === result.id ? result : item) } : current);
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) { saveLocalDraft(pendingStorage, null); setPending(null); }
      if (failure instanceof ApiResponseError && failure.status === 409) {
        try { setConflictRemote(await getImpactReview(episodeId, command.reviewId)); }
        catch { /* 本地决定和原 revision 继续保留。 */ }
      }
      setError(commandResultIsUnknown(failure) ? "决定结果尚未确认。原请求已经保留，请先核对。" : errorText(failure));
    } finally { setBusy(false); }
  };

  const rebase = () => {
    if (!conflictRemote) return;
    setReview(conflictRemote);
    setDecisions(rebaseImpactDecisions(conflictRemote.decisions, decisions, editedItemIds));
    setBasedOnRevision(conflictRemote.revision);
    setConflictRemote(null);
  };

  const loadMore = () => {
    if (!page?.nextBeforeReviewId || busy) return;
    setBusy(true);
    void listImpactReviews(episodeId, status, page.nextBeforeReviewId).then((next) => setPage((current) => current ? { reviews: [...current.reviews, ...next.reviews.filter((item) => !current.reviews.some((old) => old.id === item.id))], nextBeforeReviewId: next.nextBeforeReviewId } : next)).catch((failure) => setError(errorText(failure))).finally(() => setBusy(false));
  };

  return <section className="episode-production-side-card episode-impact-review">
    <header><strong>影响复核</strong><select className="select" value={status} disabled={loading || busy || dirty} onChange={(event) => { setLoading(true); setError(null); setStatus(event.target.value as typeof status); }}><option value="pending">待处理</option><option value="resolved">已处理</option></select></header>
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}
    {pending ? <div className="notice"><p>一条决定结果尚未核对。</p><button className="button sm" type="button" disabled={busy} onClick={() => void submit(true)}>按原请求核对</button></div> : null}
    {loading ? <p>正在读取影响报告…</p> : !page?.reviews.length ? <p>当前没有{status === "pending" ? "待处理" : "已处理"}的持久化报告。查不到直接引用不等于没有潜在影响。</p> : <>
      <label>报告<select className="select" value={review?.id ?? ""} disabled={busy} onChange={(event) => void selectReview(event.target.value)}>{page.reviews.map((item) => <option key={item.id} value={item.id}>{item.isStale ? "已过期 · " : ""}{item.decisionCount}/{item.itemCount} 项 · r{item.revision}</option>)}</select></label>
      {page.nextBeforeReviewId ? <button className="button ghost sm" type="button" disabled={busy} onClick={loadMore}>加载更早报告</button> : null}
    </>}
    {review ? <div className="episode-impact-detail">
      <p>生产集：{review.producerEpisodeId === episodeId ? "本集" : review.producerEpisodeId}<br />受影响集：{review.targetEpisodeId === episodeId ? "本集" : review.targetEpisodeId}</p>
      <p className="muted">依据剧本 {review.beforeScriptVersionId} → {review.afterScriptVersionId}；受影响剧本 {review.targetScriptVersionId}</p>
      {review.isStale ? <div className="notice notice-warning"><strong>报告依据已过期，只读保留</strong><p>{review.staleReasons.join("；")}</p></div> : null}
      {conflictRemote ? <div className="notice notice-warning"><p>报告或其他窗口的决定已经更新到 r{conflictRemote.revision}。你的本地选择仍保留。</p><button className="button sm" type="button" onClick={rebase}>保留我的修改并基于新版继续</button></div> : null}
      <div className="episode-impact-items">{review.report.items.map((item) => {
        const decision = decisions.find((value) => value.itemId === item.itemId);
        return <article key={item.itemId}><header><strong>{item.producerStateKey}</strong><span>{item.changeType === "removed" ? "来源状态已移除" : "来源状态已改变"}</span></header><p>{item.description}</p><div className="episode-impact-states"><span>原状态：{item.beforeState.description}</span><span>新状态：{item.afterState?.description ?? "已移除"}</span></div><label>作者决定<select className="select" disabled={!enabled || busy || review.isStale || Boolean(conflictRemote)} value={decision?.action ?? ""} onChange={(event) => changeDecision(item.itemId, { action: event.target.value as ImpactDecision["action"] })}><option value="">尚未决定</option>{Object.entries(actionLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>{decision ? <label>依据说明{decision.action === "defer" ? "（可选）" : "（必填）"}<textarea className="textarea" rows={2} maxLength={4000} disabled={!enabled || busy || review.isStale || Boolean(conflictRemote)} value={decision.note} onChange={(event) => changeDecision(item.itemId, { note: event.target.value })} /></label> : null}{decision && decision.action !== "defer" && !decision.note.trim() ? <p className="notice notice-warning">沿用、返工或不适用都必须写明可审计依据。</p> : null}</article>;
      })}</div>
      <button className="button" type="button" disabled={!enabled || busy || review.isStale || Boolean(conflictRemote) || !dirty || !decisions.length || !impactDecisionNotesComplete(decisions) || Boolean(pending)} onClick={() => void submit()}>{busy ? "正在保存…" : "保存本轮明确决定"}</button>
      <p className="muted">提醒不会自动触发返工。只有作者保存的逐项决定才会改变报告状态；选择暂缓时报告保持待处理。</p>
    </div> : null}
  </section>;
}
