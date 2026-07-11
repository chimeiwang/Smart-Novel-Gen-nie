import Link from "next/link";

import { getSession } from "@/shared/lib/auth";
import { prisma } from "@/shared/db/prisma";
import { redirect } from "next/navigation";
import { formatCreditMicros } from "@/shared/lib/billing";

function ledgerTypeLabel(type: string): string {
  if (type === "signup_bonus") return "注册赠送";
  if (type === "manual_recharge") return "人工充值";
  if (type === "ai_charge") return "AI 扣费";
  if (type === "ai_refund") return "AI 退款";
  return type;
}

export default async function BillingPage() {
  const session = await getSession();
  if (!session) redirect("/login");

  const [user, entries] = await Promise.all([
    prisma.user.findUnique({
      where: { id: session.userId },
      select: { username: true, creditBalanceMicros: true },
    }),
    prisma.creditLedger.findMany({
      where: { userId: session.userId },
      orderBy: { createdAt: "desc" },
      take: 20,
      select: {
        id: true,
        type: true,
        amountMicros: true,
        balanceAfterMicros: true,
        note: true,
        createdAt: true,
      },
    }),
  ]);

  if (!user) redirect("/login");

  return (
    <main className="page stack">
      <div className="row row-between home-header">
        <div>
          <div className="home-kicker">Billing</div>
          <h1 className="title-xl">积分与充值</h1>
          <p className="home-subtitle">当前账号：{user.username}</p>
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
            <div className="billing-balance">{formatCreditMicros(user.creditBalanceMicros)} 积分</div>
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
                      {entry.createdAt.toLocaleString("zh-CN")}
                      {entry.note ? ` · ${entry.note}` : ""}
                    </div>
                  </div>
                  <div className="billing-ledger-amount">
                    <strong>
                      {entry.amountMicros > BigInt(0) ? "+" : ""}
                      {formatCreditMicros(entry.amountMicros)}
                    </strong>
                    <span>余额 {formatCreditMicros(entry.balanceAfterMicros)}</span>
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
