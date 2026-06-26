import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const CREDIT_MICROS_PER_CREDIT = 1_000_000n;

function readArg(name) {
  const index = process.argv.indexOf(`--${name}`);
  if (index === -1) return null;
  return process.argv[index + 1] ?? null;
}

function usage() {
  console.error(
    "Usage: node scripts/grant-user-credits.mjs --username <name> --credits <amount> [--reason <text>]"
  );
}

async function main() {
  const username = readArg("username")?.trim().toLowerCase();
  const creditsText = readArg("credits")?.trim();
  const reason = readArg("reason")?.trim() || "人工充值";

  if (!username || !creditsText) {
    usage();
    process.exitCode = 1;
    return;
  }

  const credits = Number(creditsText);
  if (!Number.isFinite(credits) || credits <= 0) {
    throw new Error("--credits 必须是大于 0 的数字");
  }

  const amountMicros = BigInt(Math.round(credits * Number(CREDIT_MICROS_PER_CREDIT)));

  const result = await prisma.$transaction(async (tx) => {
    const user = await tx.user.update({
      where: { username },
      data: { creditBalanceMicros: { increment: amountMicros } },
      select: { id: true, username: true, creditBalanceMicros: true },
    });

    await tx.creditLedger.create({
      data: {
        userId: user.id,
        type: "manual_recharge",
        amountMicros,
        balanceAfterMicros: user.creditBalanceMicros,
        note: reason,
      },
    });

    return user;
  });

  console.log(
    `已为 ${result.username} 增加 ${credits} 积分，当前余额 ${Number(result.creditBalanceMicros) / Number(CREDIT_MICROS_PER_CREDIT)} 积分。`
  );
}

main()
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
