import Link from "next/link";

import { redirect } from "next/navigation";
import { createServerApiClient } from "@/lib/api/server";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";

function ledgerTypeLabel(type: string): string {
  if (type === "signup_bonus") return "注册赠送";
  if (type === "manual_recharge") return "人工充值";
  if (type === "ai_charge") return "AI 扣费";
  if (type === "ai_refund") return "AI 退款";
  return type;
}

export default async function BillingPage() {
  let summary;
  try {
    const client = await createServerApiClient();
    summary = requireApiData(await client.GET("/api/v1/billing/summary"));
  } catch (error) {
    if (error instanceof CoreApiPageError && error.status === 401) redirect("/login");
    const message = error instanceof Error ? error.message : "加载积分信息失败";
    return <main className="page"><div className="empty">{message}</div></main>;
  }
  const entries = summary.recentLedger;

  return (
    <main className="page stack">
      <div className="row row-between home-header">
        <div>
          <div className="home-kicker">Billing</div>
          <h1 className="title-xl">积分与充值</h1>
          <p className="home-subtitle">当前账号：{summary.username}</p>
        </div>
        <div className="row">
          <Link href="/" className="button ghost">
            返回工作台
          </Link>
        </div>
      </div>

      <div className="grid-two">
        <section className="panel">
          <div className="panel-header">
            <h2 className="title-lg">当前余额</h2>
          </div>
          <div className="panel-body stack">
            <div className="billing-balance">{summary.balanceCredits} 积分</div>
            <p className="muted">
              AI 调用会按实际用量扣除积分。
            </p>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2 className="title-lg">充值</h2>
          </div>
          <div className="panel-body stack">
            <div className="notice">
              请联系管理员充值。当前版本暂不支持在线支付。
            </div>
            <p className="muted">
              到账后管理员会为你的账号人工增加积分。
            </p>
          </div>
        </section>
      </div>

      <section className="panel panel-flex">
        <div className="panel-header">
          <h2 className="title-lg">最近积分记录</h2>
        </div>
        <div className="panel-body">
          {entries.length === 0 ? (
            <div className="empty">暂无积分记录。</div>
          ) : (
            <div className="billing-ledger-list">
              {entries.map((entry) => (
                <div className="billing-ledger-row" key={entry.id}>
                  <div>
                    <div className="title-sm">{ledgerTypeLabel(entry.type)}</div>
                    <div className="muted small-text">
                      {new Date(entry.createdAt).toLocaleString("zh-CN")}
                      {entry.note ? ` · ${entry.note}` : ""}
                    </div>
                  </div>
                  <div className="billing-ledger-amount">
                    <strong>
                      {BigInt(entry.amountMicros) > BigInt(0) ? "+" : ""}
                      {(Number(entry.amountMicros) / 1_000_000).toString()}
                    </strong>
                    <span>余额 {(Number(entry.balanceAfterMicros) / 1_000_000).toString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
