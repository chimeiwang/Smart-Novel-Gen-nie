import { prisma } from "@/shared/db/prisma";
import { getSession } from "@/shared/lib/auth";

import { NovelListClient } from "@/features/projects/novel-list-client";

export default async function HomePage() {
  const session = await getSession();
  const novels = await prisma.novel.findMany({
    where: { userId: session?.userId ?? undefined },
    orderBy: {
      updatedAt: "desc",
    },
    include: {
      chapters: true,
      appliedStyle: true,
    },
  });

  const novelList = novels.map((n) => ({
    id: n.id,
    name: n.name,
    summary: n.summary,
    chapters: n.chapters.map((c) => ({ id: c.id })),
    appliedStyle: n.appliedStyle ? { name: n.appliedStyle.name } : null,
  }));

  return <NovelListClient novels={novelList} />;
}