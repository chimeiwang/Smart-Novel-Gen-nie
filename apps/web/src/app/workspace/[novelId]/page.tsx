import Link from "next/link";
import { notFound } from "next/navigation";

import { ChapterEditor } from "@/features/editor/chapter-editor";
import { SmartWritingPanel } from "@/features/workspace/smart-writing-panel";
import { SidebarTabs } from "@/features/workspace/sidebar-tabs";
import { countTextLength } from "@/shared/lib/word-count";
import { prisma } from "@/shared/db/prisma";
import { getSession } from "@/shared/lib/auth";
import { LogoutButton } from "@/features/auth/user-menu";

// 角色状态枚举
type CharacterStatus = "active" | "missing" | "dead" | "imprisoned" | "unknown";

// 关系类型枚举
type RelationType = "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";

type WorkspacePageProps = {
  params: Promise<{ novelId: string }>;
  searchParams: Promise<{ chapterId?: string }>;
};

export default async function WorkspacePage({
  params,
  searchParams,
}: WorkspacePageProps) {
  const { novelId } = await params;
  const { chapterId } = await searchParams;
  const session = await getSession();

  const novel = await prisma.novel.findUnique({
    where: { id: novelId, userId: session?.userId ?? undefined },
    include: {
      chapters: {
        orderBy: { order: "asc" },
        include: {
          chapterProgress: true,
          qualityChecks: {
            orderBy: { createdAt: "asc" },
          },
          beatPlans: {
            where: { status: "approved" },
            orderBy: { updatedAt: "desc" },
            take: 1,
            include: {
              sceneBeats: {
                orderBy: { order: "asc" },
              },
            },
          },
        },
      },
      characters: {
        orderBy: { updatedAt: "desc" },
        include: {
          faction: true,
          experiences: {
            orderBy: { order: "asc" },
          },
          outgoingRelations: {
            include: {
              target: { select: { id: true, name: true } },
            },
          },
          incomingRelations: {
            include: {
              character: { select: { id: true, name: true } },
            },
          },
        },
      },
      items: {
        orderBy: { updatedAt: "desc" },
        include: {
          owner: true,
        },
      },
      locations: {
        orderBy: { updatedAt: "desc" },
      },
      factions: {
        orderBy: { updatedAt: "desc" },
      },
      glossaries: {
        orderBy: { updatedAt: "desc" },
      },
      storyBackground: true,
      worldSetting: true,
      writingBible: true,
      outline: true,
      outlineNodes: {
        orderBy: [
          { order: "asc" },
          { title: "asc" },
        ],
      },
      plotProgress: true,
      references: {
        orderBy: { updatedAt: "desc" },
      },
      appliedStyle: true,
    },
  });

  if (!novel) {
    notFound();
  }

  const styles = await prisma.writingStyle.findMany({
    orderBy: {
      updatedAt: "desc",
    },
  });

  const chapters = novel.chapters as Array<{
    id: string;
    title: string;
    content: string;
    order: number;
    updatedAt: Date;
    status: string;
    completedAt: Date | null;
    chapterProgress: { content: string } | null;
    qualityChecks: Array<{
      id: string; type: string; status: string; title: string; summary: string | null;
      result: string | null;
      scoreHook: number | null; scoreTension: number | null; scorePayoff: number | null;
      scorePacing: number | null; scoreEndingHook: number | null; scoreReaderPromise: number | null;
      scoreOverall: number | null; qualityGate: string | null; rewriteBrief: string | null;
    }>;
    beatPlans: Array<{
      id: string;
      status: string;
      chapterGoal: string;
      totalEstimatedWords: number;
      sceneBeats: Array<{ id: string }>;
    }>;
  }>;
  const writingBible = novel.writingBible as {
    storyLengthProfile: string;
    targetTotalWordCount: number | null;
    genre: string | null;
    targetReaders: string | null;
    coreSellingPoint: string | null;
    readerPromise: string | null;
    appealModel: string | null;
    taboo: string | null;
    comparableTitles: string | null;
    notes: string | null;
  } | null;
  const characters = novel.characters as Array<{
    id: string;
    name: string;
    aliases: string | null;
    gender: string | null;
    age: string | null;
    appearance: string | null;
    personality: string | null;
    identity: string | null;
    background: string | null;
    coreDesire: string | null;
    behaviorBoundaries: string | null;
    speechStyle: string | null;
    relationshipPrinciples: string | null;
    shortTermGoal: string | null;
    factionId: string | null;
    faction: { id: string; name: string } | null;
    // 新增：实力相关
    powerLevel: string | null;
    combatAbility: string | null;
    specialSkills: string | null;
    // 新增：当前状态
    currentStatus: CharacterStatus;
    statusNote: string | null;
    // 角色关系
    outgoingRelations: Array<{
      id: string;
      targetId: string;
      target: { id: string; name: string };
      relationType: RelationType;
      intimacy: number;
      description: string | null;
      startDate: string | null;
      endDate: string | null;
    }>;
    incomingRelations: Array<{
      id: string;
      characterId: string;
      character: { id: string; name: string };
      relationType: RelationType;
      intimacy: number;
      description: string | null;
    }>;
    experiences: Array<{
      id: string;
      chapterId: string | null;
      content: string;
      order: number;
    }>;
  }>;
  const items = novel.items as Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    rarity: string | null;
    effect: string | null;
    origin: string | null;
    description: string | null;
    ownerId: string | null;
    owner: { id: string; name: string } | null;
  }>;
  const locations = novel.locations as Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    parentId: string | null;
    climate: string | null;
    culture: string | null;
    description: string | null;
  }>;
  const factions = novel.factions as Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    baseId: string | null;
    description: string | null;
  }>;
  const glossaries = novel.glossaries as Array<{
    id: string;
    term: string;
    definition: string;
    category: string | null;
  }>;
  const storyBackground = novel.storyBackground as {
    content: string;
  } | null;
  const worldSetting = novel.worldSetting as {
    content: string;
  } | null;
  const outline = novel.outline as {
    content: string;
  } | null;
  const outlineNodes = novel.outlineNodes as Array<{
    id: string;
    title: string;
    content: string | null;
    kind: "stage" | "plot_unit" | "chapter_group";
    status: "planned" | "in_progress" | "completed" | "skipped";
    order: number;
    parentId: string | null;
    estimatedWordCount: number | null;
    actualWordCount: number | null;
  }>;
  const references = novel.references as Array<{
    id: string;
    title: string;
    type: string;
    content: string;
    sourceUrl: string | null;
  }>;
  const writingStyles = styles as Array<{
    id: string;
    name: string;
    portraitMarkdown: string | null;
    sourceType: string;
  }>;

  const currentChapter =
    chapters.find((item) => item.id === chapterId) ??
    [...chapters].reverse().find((item) => item.status === "drafting") ??
    chapters[chapters.length - 1];

  if (!currentChapter) {
    return (
      <main className="page">
        <div className="empty">当前小说还没有章节，请先添加章节。</div>
      </main>
    );
  }

  const totalCount = chapters.reduce(
    (sum, item) => sum + countTextLength(item.content),
    0,
  );

  return (
    <main className="page stack">
      <div className="panel header-panel">
        <div className="panel-header">
          <Link href="/" className="muted">
            ← 返回
          </Link>
          <span style={{ marginLeft: "auto" }}>
            <LogoutButton />
          </span>
          <h1 className="title-lg">{novel.name}</h1>
          <div className="meta">
            <span className="badge">{totalCount} 字</span>
            <span className="badge">{chapters.length} 章</span>
            {novel.appliedStyle ? <span className="badge">{novel.appliedStyle.name}</span> : null}
          </div>
        </div>
      </div>

      <div className="workspace">
        <SidebarTabs
          novelId={novel.id}
          activeChapterId={currentChapter.id}
          chapters={chapters.map((item) => ({
            id: item.id,
            title: item.title,
            order: item.order,
            updatedAt: item.updatedAt.toISOString(),
            status: item.status,
            wordCount: countTextLength(item.content),
            approvedBeatPlan: item.beatPlans[0]
              ? {
                  sceneCount: item.beatPlans[0].sceneBeats.length,
                  totalEstimatedWords: item.beatPlans[0].totalEstimatedWords,
                }
              : null,
          }))}
          characters={characters.map((c) => ({
            id: c.id,
            name: c.name,
            aliases: c.aliases,
            gender: c.gender,
            age: c.age,
            appearance: c.appearance,
            personality: c.personality,
            identity: c.identity,
            background: c.background,
            coreDesire: c.coreDesire,
            behaviorBoundaries: c.behaviorBoundaries,
            speechStyle: c.speechStyle,
            relationshipPrinciples: c.relationshipPrinciples,
            shortTermGoal: c.shortTermGoal,
            factionId: c.factionId,
            faction: c.faction,
            // 新增字段
            powerLevel: c.powerLevel,
            combatAbility: c.combatAbility,
            specialSkills: c.specialSkills,
            currentStatus: c.currentStatus,
            statusNote: c.statusNote,
            // 角色关系
            outgoingRelations: c.outgoingRelations ?? [],
            incomingRelations: c.incomingRelations ?? [],
            experiences: c.experiences,
          }))}
          items={items.map((i) => ({
            id: i.id,
            name: i.name,
            aliases: i.aliases,
            type: i.type,
            rarity: i.rarity,
            effect: i.effect,
            origin: i.origin,
            description: i.description,
            ownerId: i.ownerId,
            owner: i.owner,
          }))}
          locations={locations.map((l) => ({
            id: l.id,
            name: l.name,
            aliases: l.aliases,
            type: l.type,
            parentId: l.parentId,
            climate: l.climate,
            culture: l.culture,
            description: l.description,
          }))}
          factions={factions.map((f) => ({
            id: f.id,
            name: f.name,
            aliases: f.aliases,
            type: f.type,
            baseId: f.baseId,
            description: f.description,
          }))}
          glossaries={glossaries.map((g) => ({
            id: g.id,
            term: g.term,
            definition: g.definition,
            category: g.category,
          }))}
          appliedStyleId={novel.appliedStyleId}
          styles={writingStyles.map((style) => ({
            id: style.id,
            name: style.name,
            portraitMarkdown: style.portraitMarkdown,
            sourceType: style.sourceType,
          }))}
          progress={
            novel.plotProgress
              ? {
                  currentStage: novel.plotProgress.currentStage,
                  currentGoal: novel.plotProgress.currentGoal,
                  currentConflict: novel.plotProgress.currentConflict,
                  nextMilestone: novel.plotProgress.nextMilestone,
                }
              : null
          }
          storyProgress={novel.storyProgress}
          storyBackground={storyBackground?.content ?? null}
          worldSetting={worldSetting?.content ?? null}
          writingBible={writingBible}
          outline={
            outline
              ? {
                  content: outline.content,
                }
              : null
          }
          outlineNodes={outlineNodes.map((node) => ({
            id: node.id,
            title: node.title,
            content: node.content,
            kind: node.kind,
            status: node.status,
            order: node.order,
            parentId: node.parentId,
            estimatedWordCount: node.estimatedWordCount,
            actualWordCount: node.actualWordCount,
          }))}
          references={references.map((reference) => ({
            id: reference.id,
            title: reference.title,
            type: reference.type,
            content: reference.content,
            sourceUrl: reference.sourceUrl,
          }))}
        />

        <ChapterEditor
          key={currentChapter.id}
          chapter={{
            id: currentChapter.id,
            title: currentChapter.title,
            content: currentChapter.content,
            status: currentChapter.status,
            completedAt: currentChapter.completedAt?.toISOString() ?? null,
          }}
          chapterProgress={currentChapter.chapterProgress?.content ?? null}
          qualityChecks={currentChapter.qualityChecks
            .filter((check) => check.type === "consistency")
            .map((check) => ({
              id: check.id,
              chapterId: currentChapter.id,
              type: check.type,
              status: check.status,
              title: check.title,
              summary: check.summary,
              result: check.result,
              scoreHook: check.scoreHook,
              scoreTension: check.scoreTension,
              scorePayoff: check.scorePayoff,
              scorePacing: check.scorePacing,
              scoreEndingHook: check.scoreEndingHook,
              scoreReaderPromise: check.scoreReaderPromise,
              scoreOverall: check.scoreOverall,
              qualityGate: check.qualityGate,
              rewriteBrief: check.rewriteBrief,
            }) as import("@/shared/contracts/quality-check").QualityCheckDto)}
          styleName={novel.appliedStyle?.name}
        />

        <SmartWritingPanel
          novelId={novel.id}
          currentChapter={{
            id: currentChapter.id,
            title: currentChapter.title,
            status: currentChapter.status,
            wordCount: countTextLength(currentChapter.content),
            openConsistencyCheckCount: currentChapter.qualityChecks.filter(
              (check) => check.type === "consistency" && (check.status === "pending" || check.status === "failed")
            ).length,
            approvedBeatPlan: currentChapter.beatPlans[0]
              ? {
                  id: currentChapter.beatPlans[0].id,
                  chapterGoal: currentChapter.beatPlans[0].chapterGoal,
                  sceneCount: currentChapter.beatPlans[0].sceneBeats.length,
                  totalEstimatedWords: currentChapter.beatPlans[0].totalEstimatedWords,
                }
              : null,
          }}
        />
      </div>
    </main>
  );
}
