--
-- PostgreSQL database dump
--

-- Dumped from database version 14.23 (Ubuntu 14.23-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.24 (Debian 14.24-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: BeatPlanStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."BeatPlanStatus" AS ENUM (
    'draft',
    'reviewing',
    'approved',
    'rejected',
    'superseded'
);


--
-- Name: ChapterStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ChapterStatus" AS ENUM (
    'drafting',
    'review',
    'completed'
);


--
-- Name: CharacterStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."CharacterStatus" AS ENUM (
    'active',
    'missing',
    'dead',
    'imprisoned',
    'unknown'
);


--
-- Name: ForeshadowingStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ForeshadowingStatus" AS ENUM (
    'active',
    'paid_off',
    'abandoned'
);


--
-- Name: OutlineNodeKind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."OutlineNodeKind" AS ENUM (
    'stage',
    'plot_unit',
    'chapter_group'
);


--
-- Name: OutlineNodeStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."OutlineNodeStatus" AS ENUM (
    'planned',
    'in_progress',
    'completed',
    'skipped'
);


--
-- Name: QualityCheckStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."QualityCheckStatus" AS ENUM (
    'pending',
    'running',
    'completed',
    'skipped',
    'failed'
);


--
-- Name: QualityCheckType; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."QualityCheckType" AS ENUM (
    'consistency',
    'lore_sync',
    'editorial',
    'craft'
);


--
-- Name: RagDocumentStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."RagDocumentStatus" AS ENUM (
    'disabled',
    'ready',
    'failed'
);


--
-- Name: RagSourceType; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."RagSourceType" AS ENUM (
    'reference_material'
);


--
-- Name: ReferenceMaterialType; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ReferenceMaterialType" AS ENUM (
    'note',
    'web',
    'book',
    'image',
    'custom'
);


--
-- Name: RelationType; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."RelationType" AS ENUM (
    'family',
    'master_student',
    'friend',
    'enemy',
    'ally',
    'lover',
    'rival',
    'subordinate',
    'acquaintance',
    'other'
);


--
-- Name: ReviewArtifactEvaluationVerdict; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ReviewArtifactEvaluationVerdict" AS ENUM (
    'pass',
    'revise',
    'block'
);


--
-- Name: ReviewArtifactKind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ReviewArtifactKind" AS ENUM (
    'agent_updates',
    'outline_draft',
    'chapter_draft',
    'lore_draft',
    'revision_brief',
    'beat_plan_draft',
    'chapter_content',
    'beat_plan',
    'freeform_markdown',
    'video_scene_plan',
    'video_adaptation_plan'
);


--
-- Name: ReviewArtifactStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."ReviewArtifactStatus" AS ENUM (
    'draft',
    'under_review',
    'awaiting_user',
    'applying',
    'applied'
);


--
-- Name: StoryLengthProfile; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."StoryLengthProfile" AS ENUM (
    'short_medium',
    'long_serial'
);


--
-- Name: StyleSourceType; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."StyleSourceType" AS ENUM (
    'manual',
    'agent'
);


--
-- Name: WorkflowRunKind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."WorkflowRunKind" AS ENUM (
    'chat',
    'chapter_generation',
    'quality_check',
    'lore_sync',
    'beat_plan'
);


--
-- Name: WorkflowRunStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."WorkflowRunStatus" AS ENUM (
    'pending',
    'running',
    'waiting_user',
    'completed',
    'failed',
    'cancelled'
);


--
-- Name: WorkflowStepStatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."WorkflowStepStatus" AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'skipped'
);


--
-- Name: WorkflowStepType; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."WorkflowStepType" AS ENUM (
    'agent',
    'tool',
    'user_confirmation',
    'persistence'
);


--
-- Name: WritingTaskPhase; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public."WritingTaskPhase" AS ENUM (
    'idle',
    'active',
    'waiting_call',
    'awaiting_user_review',
    'completed',
    'error'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: Chapter; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Chapter" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    title text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    "order" integer NOT NULL,
    status public."ChapterStatus" DEFAULT 'drafting'::public."ChapterStatus" NOT NULL,
    "completedAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ChapterBeatPlan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ChapterBeatPlan" (
    id text NOT NULL,
    "chapterId" text NOT NULL,
    "goalId" text,
    status public."BeatPlanStatus" DEFAULT 'draft'::public."BeatPlanStatus" NOT NULL,
    "chapterGoal" text NOT NULL,
    "mainPlotConnection" text,
    "chapterAcceptanceCriteria" text,
    "totalEstimatedWords" integer DEFAULT 0 NOT NULL,
    "generatedBy" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ChapterProgress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ChapterProgress" (
    id text NOT NULL,
    "chapterId" text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ChapterQualityCheck; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ChapterQualityCheck" (
    id text NOT NULL,
    "chapterId" text NOT NULL,
    type public."QualityCheckType" NOT NULL,
    status public."QualityCheckStatus" DEFAULT 'pending'::public."QualityCheckStatus" NOT NULL,
    title text NOT NULL,
    summary text,
    result text,
    "scoreHook" integer,
    "scoreTension" integer,
    "scorePayoff" integer,
    "scorePacing" integer,
    "scoreEndingHook" integer,
    "scoreReaderPromise" integer,
    "scoreOverall" integer,
    "qualityGate" text,
    "rewriteBrief" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ChapterWritingGoal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ChapterWritingGoal" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "chapterId" text NOT NULL,
    "narrativeGoal" text NOT NULL,
    "desiredEmotion" text,
    "requiredForeshadowing" text,
    "requiredCharacters" text,
    "wordCountMin" integer,
    "wordCountMax" integer,
    "specialNotes" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Character; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Character" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    name text NOT NULL,
    aliases text,
    gender text,
    age text,
    appearance text,
    personality text,
    identity text,
    background text,
    "factionId" text,
    "coreDesire" text,
    "behaviorBoundaries" text,
    "speechStyle" text,
    "relationshipPrinciples" text,
    "shortTermGoal" text,
    "powerLevel" text,
    "combatAbility" text,
    "specialSkills" text,
    "currentStatus" public."CharacterStatus" DEFAULT 'active'::public."CharacterStatus" NOT NULL,
    "statusNote" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: CharacterExperience; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CharacterExperience" (
    id text NOT NULL,
    "characterId" text NOT NULL,
    "chapterId" text,
    content text NOT NULL,
    "order" integer DEFAULT 0 NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: CharacterRelation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CharacterRelation" (
    id text NOT NULL,
    "characterId" text NOT NULL,
    "targetId" text NOT NULL,
    "relationType" public."RelationType" NOT NULL,
    intimacy integer DEFAULT 0 NOT NULL,
    description text,
    "startDate" text,
    "endDate" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: CharacterStateChange; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CharacterStateChange" (
    id text NOT NULL,
    "characterId" text NOT NULL,
    "chapterId" text,
    "changeType" text NOT NULL,
    description text NOT NULL,
    "beforeState" text,
    "afterState" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: CreditLedger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."CreditLedger" (
    id text NOT NULL,
    "userId" text NOT NULL,
    type text NOT NULL,
    "amountMicros" bigint NOT NULL,
    "balanceAfterMicros" bigint NOT NULL,
    model text,
    "promptTokens" integer DEFAULT 0 NOT NULL,
    "completionTokens" integer DEFAULT 0 NOT NULL,
    "cachedTokens" integer DEFAULT 0 NOT NULL,
    "totalTokens" integer DEFAULT 0 NOT NULL,
    "agentId" text,
    "novelId" text,
    "requestId" text,
    note text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: Faction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Faction" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    name text NOT NULL,
    aliases text,
    type text,
    "baseId" text,
    description text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Foreshadowing; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Foreshadowing" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    name text NOT NULL,
    "plantedAt" text,
    "plantedContent" text,
    "expectedPayoff" text,
    "payoffAt" text,
    status public."ForeshadowingStatus" DEFAULT 'active'::public."ForeshadowingStatus" NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Glossary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Glossary" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    term text NOT NULL,
    definition text NOT NULL,
    category text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Item" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    name text NOT NULL,
    aliases text,
    type text,
    rarity text,
    effect text,
    origin text,
    description text,
    "ownerId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Location; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Location" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    name text NOT NULL,
    aliases text,
    type text,
    "parentId" text,
    climate text,
    culture text,
    description text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Novel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Novel" (
    id text NOT NULL,
    name text NOT NULL,
    summary text,
    "storyProgress" text,
    "appliedStyleId" text,
    "userId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: Outline; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."Outline" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: OutlineNode; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."OutlineNode" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "parentId" text,
    title text NOT NULL,
    content text,
    "order" integer DEFAULT 0 NOT NULL,
    status public."OutlineNodeStatus" DEFAULT 'planned'::public."OutlineNodeStatus" NOT NULL,
    "estimatedWordCount" integer,
    "actualWordCount" integer,
    "linkedChapterId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    kind public."OutlineNodeKind" DEFAULT 'stage'::public."OutlineNodeKind" NOT NULL,
    "chapterStartOrder" integer,
    "chapterEndOrder" integer,
    CONSTRAINT "OutlineNode_chapter_range_check" CHECK (((("chapterStartOrder" IS NULL) AND ("chapterEndOrder" IS NULL)) OR (("chapterStartOrder" IS NOT NULL) AND ("chapterEndOrder" IS NOT NULL) AND ("chapterStartOrder" > 0) AND ("chapterEndOrder" >= "chapterStartOrder"))))
);


--
-- Name: PlotProgress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."PlotProgress" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "currentStage" text NOT NULL,
    "currentGoal" text,
    "currentConflict" text,
    "nextMilestone" text,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: RagChunk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."RagChunk" (
    id text NOT NULL,
    "documentId" text NOT NULL,
    "novelId" text NOT NULL,
    "chunkIndex" integer NOT NULL,
    text text NOT NULL,
    "charCount" integer NOT NULL,
    "embeddingDimension" integer NOT NULL,
    embedding public.vector NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: RagDocument; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."RagDocument" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "sourceType" public."RagSourceType" NOT NULL,
    "sourceId" text NOT NULL,
    title text NOT NULL,
    "contentHash" text NOT NULL,
    status public."RagDocumentStatus" DEFAULT 'disabled'::public."RagDocumentStatus" NOT NULL,
    "errorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ReferenceMaterial; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ReferenceMaterial" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    title text NOT NULL,
    type public."ReferenceMaterialType" NOT NULL,
    content text NOT NULL,
    "sourceUrl" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: ReviewArtifact; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ReviewArtifact" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "chapterId" text,
    "taskId" text,
    "workflowRunId" text,
    "artifactKey" text,
    kind public."ReviewArtifactKind" NOT NULL,
    status public."ReviewArtifactStatus" DEFAULT 'draft'::public."ReviewArtifactStatus" NOT NULL,
    title text,
    summary text,
    "payloadJson" text NOT NULL,
    "diffJson" text,
    "createdByAgent" text,
    "updatedByAgent" text,
    "reviewerAgent" text,
    revision integer DEFAULT 1 NOT NULL,
    "appliedAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "videoSceneId" text,
    "videoAdaptationId" text,
    "videoAdaptationTaskId" text,
    CONSTRAINT "ReviewArtifact_video_adaptation_kind_check" CHECK ((((kind)::text <> 'video_adaptation_plan'::text) OR (("videoAdaptationId" IS NOT NULL) AND ("videoAdaptationTaskId" IS NOT NULL) AND ("videoSceneId" IS NULL) AND ("taskId" IS NULL)))),
    CONSTRAINT "ReviewArtifact_video_target_exclusive_check" CHECK ((NOT (("videoSceneId" IS NOT NULL) AND ("videoAdaptationId" IS NOT NULL))))
);


--
-- Name: COLUMN "ReviewArtifact"."videoSceneId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."ReviewArtifact"."videoSceneId" IS '视频场景方案草案的审核目标';


--
-- Name: COLUMN "ReviewArtifact"."videoAdaptationId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."ReviewArtifact"."videoAdaptationId" IS '章节影视化镜头方案候选的明确审核目标';


--
-- Name: COLUMN "ReviewArtifact"."videoAdaptationTaskId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."ReviewArtifact"."videoAdaptationTaskId" IS '产生章节影视化候选的耐久来源任务';


--
-- Name: ReviewArtifactEvaluation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ReviewArtifactEvaluation" (
    id text NOT NULL,
    "artifactId" text NOT NULL,
    revision integer NOT NULL,
    "evaluatorAgent" text NOT NULL,
    verdict public."ReviewArtifactEvaluationVerdict" NOT NULL,
    summary text NOT NULL,
    "requiredChanges" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ReviewArtifactRevision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."ReviewArtifactRevision" (
    id text NOT NULL,
    "artifactId" text NOT NULL,
    revision integer NOT NULL,
    summary text,
    "payloadJson" text NOT NULL,
    "diffJson" text,
    "createdByAgent" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: SceneBeat; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."SceneBeat" (
    id text NOT NULL,
    "beatPlanId" text NOT NULL,
    "order" integer NOT NULL,
    goal text NOT NULL,
    conflict text,
    characters text NOT NULL,
    "foreshadowingRefs" text,
    "estimatedWords" integer DEFAULT 0 NOT NULL,
    "acceptanceCriteria" text NOT NULL
);


--
-- Name: StoryBackground; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."StoryBackground" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: StylePortraitTask; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."StylePortraitTask" (
    id text NOT NULL,
    "styleId" text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "errorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    section text,
    CONSTRAINT "StylePortraitTask_section_check" CHECK (((section IS NULL) OR (section = ANY (ARRAY['creativeMethodology'::text, 'uniqueMarkers'::text, 'generationStyle'::text, 'expressionFeatures'::text, 'styleTraits'::text]))))
);


--
-- Name: StyleReference; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."StyleReference" (
    id text NOT NULL,
    "styleId" text NOT NULL,
    filename text NOT NULL,
    filepath text NOT NULL,
    "charCount" integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'ready'::text NOT NULL,
    "errorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: TokenUsage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."TokenUsage" (
    id text NOT NULL,
    "userId" text NOT NULL,
    model text DEFAULT ''::text NOT NULL,
    "promptTokens" integer DEFAULT 0 NOT NULL,
    "completionTokens" integer DEFAULT 0 NOT NULL,
    "cachedTokens" integer DEFAULT 0 NOT NULL,
    "totalTokens" integer DEFAULT 0 NOT NULL,
    "agentId" text,
    "novelId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "requestId" text,
    "taskId" text,
    "runId" text,
    "promptCacheMissTokens" integer,
    "reasoningTokens" integer,
    CONSTRAINT "TokenUsage_prompt_cache_details_check" CHECK ((("promptCacheMissTokens" IS NULL) OR (("cachedTokens" + "promptCacheMissTokens") = "promptTokens"))),
    CONSTRAINT "TokenUsage_reasoning_details_check" CHECK ((("reasoningTokens" IS NULL) OR ("reasoningTokens" <= "completionTokens"))),
    CONSTRAINT "TokenUsage_requestId_check" CHECK ((("requestId" IS NULL) OR (btrim("requestId") <> ''::text))),
    CONSTRAINT "TokenUsage_token_details_nonnegative_check" CHECK (((("promptCacheMissTokens" IS NULL) OR ("promptCacheMissTokens" >= 0)) AND (("reasoningTokens" IS NULL) OR ("reasoningTokens" >= 0))))
);


--
-- Name: User; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."User" (
    id text NOT NULL,
    username text NOT NULL,
    "passwordHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "creditBalanceMicros" bigint DEFAULT 0 NOT NULL
);


--
-- Name: VideoAdaptationDecisionCommand; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoAdaptationDecisionCommand" (
    id text NOT NULL,
    "requestedByUserId" text NOT NULL,
    "novelId" text NOT NULL,
    "projectId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "artifactId" text NOT NULL,
    "sourceTaskId" text NOT NULL,
    "clientRequestId" text NOT NULL,
    "expectedArtifactRevision" integer NOT NULL,
    "expectedAdaptationRevision" integer NOT NULL,
    "requestHash" text NOT NULL,
    decision text DEFAULT 'approve'::text NOT NULL,
    status text DEFAULT 'succeeded'::text NOT NULL,
    "resultJson" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "completedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoAdaptationDecisionCommand_client_request_check" CHECK ((btrim("clientRequestId") <> ''::text)),
    CONSTRAINT "VideoAdaptationDecisionCommand_decision_check" CHECK ((decision = 'approve'::text)),
    CONSTRAINT "VideoAdaptationDecisionCommand_request_hash_check" CHECK (("requestHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoAdaptationDecisionCommand_result_json_check" CHECK (COALESCE((jsonb_typeof(("resultJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoAdaptationDecisionCommand_revision_check" CHECK ((("expectedArtifactRevision" > 0) AND ("expectedAdaptationRevision" > 0))),
    CONSTRAINT "VideoAdaptationDecisionCommand_status_check" CHECK ((status = 'succeeded'::text))
);


--
-- Name: VideoAdaptationTask; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoAdaptationTask" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "baseShotPlanVersionId" text,
    "jobId" text NOT NULL,
    kind text NOT NULL,
    workflow text NOT NULL,
    provider text DEFAULT 'deepseek'::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "idempotencyKey" text NOT NULL,
    "requestJson" text NOT NULL,
    "resultJson" text,
    "checkpointStage" text DEFAULT 'none'::text NOT NULL,
    "checkpointJson" text,
    "attemptCount" integer DEFAULT 0 NOT NULL,
    "nextAttemptAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastErrorCode" text,
    "lastErrorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "submittedAt" timestamp(3) without time zone,
    "completedAt" timestamp(3) without time zone,
    CONSTRAINT "VideoAdaptationTask_attempt_check" CHECK (("attemptCount" >= 0)),
    CONSTRAINT "VideoAdaptationTask_checkpoint_check" CHECK (((("checkpointStage" = 'none'::text) AND ("checkpointJson" IS NULL)) OR (("checkpointStage" = 'dramatic_structure'::text) AND COALESCE((jsonb_typeof(("checkpointJson")::jsonb) = 'object'::text), false)))),
    CONSTRAINT "VideoAdaptationTask_kind_workflow_check" CHECK ((((kind = 'shot_plan'::text) AND (workflow = 'chapter_cinematic_adaptation_v2'::text)) OR ((kind = 'shot_prompt'::text) AND (workflow = 'chapter_shot_prompt_v2'::text) AND ("baseShotPlanVersionId" IS NOT NULL)))),
    CONSTRAINT "VideoAdaptationTask_request_json_check" CHECK (COALESCE((jsonb_typeof(("requestJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoAdaptationTask_result_json_check" CHECK ((("resultJson" IS NULL) OR COALESCE((jsonb_typeof(("resultJson")::jsonb) = 'object'::text), false))),
    CONSTRAINT "VideoAdaptationTask_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'submitted'::text, 'processing'::text, 'completed'::text, 'failed'::text, 'cancelled'::text])))
);


--
-- Name: TABLE "VideoAdaptationTask"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoAdaptationTask" IS '章节拆镜与逐镜提示词的 PostgreSQL 耐久任务事实';


--
-- Name: VideoAsset; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoAsset" (
    id text NOT NULL,
    "projectId" text NOT NULL,
    name text NOT NULL,
    modality text NOT NULL,
    duty text NOT NULL,
    "storageKey" text NOT NULL,
    "mimeType" text NOT NULL,
    "byteSize" bigint NOT NULL,
    "durationMs" integer,
    sha256 text NOT NULL,
    "sourceKind" text DEFAULT 'user_upload'::text NOT NULL,
    "rightsStatus" text DEFAULT 'unconfirmed'::text NOT NULL,
    "lockedAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoAsset_byte_size_check" CHECK (("byteSize" > 0)),
    CONSTRAINT "VideoAsset_duration_check" CHECK ((("durationMs" IS NULL) OR ("durationMs" > 0))),
    CONSTRAINT "VideoAsset_duty_check" CHECK ((duty = ANY (ARRAY['identity'::text, 'costume'::text, 'scene'::text, 'prop'::text, 'style'::text, 'storyboard'::text, 'keyframe'::text, 'motion'::text, 'camera'::text, 'voice'::text, 'ambience'::text, 'sfx'::text, 'music'::text, 'episode_export'::text]))),
    CONSTRAINT "VideoAsset_modality_check" CHECK ((modality = ANY (ARRAY['image'::text, 'video'::text, 'audio'::text]))),
    CONSTRAINT "VideoAsset_rights_status_check" CHECK (("rightsStatus" = ANY (ARRAY['unconfirmed'::text, 'confirmed'::text, 'restricted'::text, 'rejected'::text]))),
    CONSTRAINT "VideoAsset_sha256_check" CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoAsset_source_kind_check" CHECK (("sourceKind" = ANY (ARRAY['user_upload'::text, 'authorized_real'::text, 'virtual'::text, 'model_generated'::text])))
);


--
-- Name: TABLE "VideoAsset"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoAsset" IS '视频项目中具有哈希、权利状态和锁定状态的媒体素材';


--
-- Name: COLUMN "VideoAsset"."lockedAt"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoAsset"."lockedAt" IS '素材权利已确认并由用户锁定的时间';


--
-- Name: VideoAssetBinding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoAssetBinding" (
    id text NOT NULL,
    "sceneId" text NOT NULL,
    "assetId" text NOT NULL,
    "targetEntity" text NOT NULL,
    "includeFeaturesJson" text NOT NULL,
    "excludeFeaturesJson" text DEFAULT '[]'::text NOT NULL,
    priority integer DEFAULT 50 NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "projectId" text NOT NULL,
    CONSTRAINT "VideoAssetBinding_exclude_json_check" CHECK (COALESCE((jsonb_typeof(("excludeFeaturesJson")::jsonb) = 'array'::text), false)),
    CONSTRAINT "VideoAssetBinding_include_json_check" CHECK (COALESCE((jsonb_typeof(("includeFeaturesJson")::jsonb) = 'array'::text), false)),
    CONSTRAINT "VideoAssetBinding_priority_check" CHECK (((priority >= 0) AND (priority <= 100)))
);


--
-- Name: TABLE "VideoAssetBinding"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoAssetBinding" IS '场景对真实素材及其参考职责的显式绑定';


--
-- Name: COLUMN "VideoAssetBinding"."projectId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoAssetBinding"."projectId" IS '由 VideoScene 冗余并同时约束场景与素材的项目归属';


--
-- Name: VideoChapterAdaptation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoChapterAdaptation" (
    id text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "chapterId" text,
    "chapterTitle" text NOT NULL,
    "chapterUpdatedAt" timestamp(3) without time zone NOT NULL,
    "sourceText" text NOT NULL,
    "sourceHash" text NOT NULL,
    "lifecycleStatus" text DEFAULT 'active'::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoChapterAdaptation_lifecycle_check" CHECK (("lifecycleStatus" = ANY (ARRAY['active'::text, 'archived'::text]))),
    CONSTRAINT "VideoChapterAdaptation_source_check" CHECK ((btrim("sourceText") <> ''::text)),
    CONSTRAINT "VideoChapterAdaptation_source_hash_check" CHECK (("sourceHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoChapterAdaptation_title_check" CHECK ((btrim("chapterTitle") <> ''::text))
);


--
-- Name: TABLE "VideoChapterAdaptation"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoChapterAdaptation" IS '长篇章节不可变来源快照及影视化工作台根对象';


--
-- Name: VideoChapterAdaptationHead; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoChapterAdaptationHead" (
    "adaptationId" text NOT NULL,
    "currentShotPlanVersionId" text,
    "currentEpisodePlanVersionId" text,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoChapterAdaptationHead_revision_check" CHECK ((revision > 0))
);


--
-- Name: VideoCinematicScene; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoCinematicScene" (
    id text NOT NULL,
    "planVersionId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "sceneKey" text NOT NULL,
    ordinal integer NOT NULL,
    title text NOT NULL,
    "locationLabel" text NOT NULL,
    "timeLabel" text NOT NULL,
    objective text NOT NULL,
    "changeSummary" text NOT NULL,
    CONSTRAINT "VideoCinematicScene_key_check" CHECK (("sceneKey" ~ '^SC[0-9]{2,3}$'::text)),
    CONSTRAINT "VideoCinematicScene_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoCinematicScene_text_check" CHECK (((btrim(title) <> ''::text) AND (btrim("locationLabel") <> ''::text) AND (btrim("timeLabel") <> ''::text) AND (btrim(objective) <> ''::text) AND (btrim("changeSummary") <> ''::text)))
);


--
-- Name: TABLE "VideoCinematicScene"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoCinematicScene" IS '正式镜头方案中的真实时间地点连续场景';


--
-- Name: VideoDramaticBeat; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoDramaticBeat" (
    id text NOT NULL,
    "planVersionId" text NOT NULL,
    "sceneId" text NOT NULL,
    "beatKey" text NOT NULL,
    ordinal integer NOT NULL,
    title text NOT NULL,
    "dramaticTurn" text NOT NULL,
    "visualStrategy" text NOT NULL,
    "coverageGoalsJson" text,
    CONSTRAINT "VideoDramaticBeat_coverage_goals_check" CHECK ((("coverageGoalsJson" IS NULL) OR (COALESCE((jsonb_typeof(("coverageGoalsJson")::jsonb) = 'array'::text), false) AND (jsonb_array_length(("coverageGoalsJson")::jsonb) > 0)))),
    CONSTRAINT "VideoDramaticBeat_key_check" CHECK (("beatKey" ~ '^B[0-9]{2,3}$'::text)),
    CONSTRAINT "VideoDramaticBeat_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoDramaticBeat_text_check" CHECK (((btrim(title) <> ''::text) AND (btrim("dramaticTurn") <> ''::text) AND (btrim("visualStrategy") <> ''::text)))
);


--
-- Name: TABLE "VideoDramaticBeat"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoDramaticBeat" IS '正式场景中由目标、信息、情绪或行动变化定义的戏剧节拍';


--
-- Name: VideoDramaticBeatSourceAnchor; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoDramaticBeatSourceAnchor" (
    "beatId" text NOT NULL,
    "planVersionId" text NOT NULL,
    ordinal integer NOT NULL,
    "startCodePoint" integer NOT NULL,
    "endCodePoint" integer NOT NULL,
    CONSTRAINT "VideoDramaticBeatSourceAnchor_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoDramaticBeatSourceAnchor_range_check" CHECK ((("startCodePoint" >= 0) AND ("endCodePoint" > "startCodePoint")))
);


--
-- Name: VideoEpisodeAudioClip; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeAudioClip" (
    "mixVersionId" text NOT NULL,
    "projectId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    ordinal integer NOT NULL,
    "trackKind" text NOT NULL,
    "assetId" text NOT NULL,
    "shotId" text,
    "timelineStartMs" integer NOT NULL,
    "sourceInMs" integer NOT NULL,
    "sourceOutMs" integer NOT NULL,
    "gainMillibels" integer DEFAULT 0 NOT NULL,
    "fadeInMs" integer DEFAULT 0 NOT NULL,
    "fadeOutMs" integer DEFAULT 0 NOT NULL,
    CONSTRAINT "VideoEpisodeAudioClip_fade_check" CHECK ((("fadeInMs" >= 0) AND ("fadeOutMs" >= 0) AND (("fadeInMs" + "fadeOutMs") <= ("sourceOutMs" - "sourceInMs")))),
    CONSTRAINT "VideoEpisodeAudioClip_gain_check" CHECK ((("gainMillibels" >= '-6000'::integer) AND ("gainMillibels" <= 1200))),
    CONSTRAINT "VideoEpisodeAudioClip_range_check" CHECK (((ordinal > 0) AND ("timelineStartMs" >= 0) AND ("sourceInMs" >= 0) AND ("sourceOutMs" > "sourceInMs"))),
    CONSTRAINT "VideoEpisodeAudioClip_track_check" CHECK (("trackKind" = ANY (ARRAY['dialogue'::text, 'narration'::text, 'ambience'::text, 'sfx'::text, 'music'::text])))
);


--
-- Name: VideoEpisodeBoundary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeBoundary" (
    "episodePlanVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "afterShotId" text NOT NULL,
    ordinal integer NOT NULL,
    CONSTRAINT "VideoEpisodeBoundary_ordinal_check" CHECK ((ordinal > 0))
);


--
-- Name: VideoEpisodeEditClip; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeEditClip" (
    "editVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "shotId" text NOT NULL,
    "takeId" text,
    ordinal integer NOT NULL,
    "sourceInMs" integer,
    "sourceOutMs" integer,
    "timelineStartMs" integer NOT NULL,
    "outputDurationMs" integer NOT NULL,
    "transitionAfter" text DEFAULT 'cut'::text NOT NULL,
    "transitionDurationMs" integer DEFAULT 0 NOT NULL,
    CONSTRAINT "VideoEpisodeEditClip_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoEpisodeEditClip_source_check" CHECK (((("takeId" IS NULL) AND ("sourceInMs" IS NULL) AND ("sourceOutMs" IS NULL)) OR (("takeId" IS NOT NULL) AND ("sourceInMs" >= 0) AND ("sourceOutMs" > "sourceInMs") AND ("outputDurationMs" = ("sourceOutMs" - "sourceInMs"))))),
    CONSTRAINT "VideoEpisodeEditClip_timeline_check" CHECK ((("timelineStartMs" >= 0) AND ("outputDurationMs" >= 500))),
    CONSTRAINT "VideoEpisodeEditClip_transition_check" CHECK (((("transitionAfter" = 'cut'::text) AND ("transitionDurationMs" = 0)) OR (("transitionAfter" = 'fade_black'::text) AND ("transitionDurationMs" > 0) AND (("transitionDurationMs" * 2) <= "outputDurationMs"))))
);


--
-- Name: VideoEpisodeEditHead; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeEditHead" (
    "episodePlanVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "episodeNo" integer NOT NULL,
    "currentVersionId" text,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoEpisodeEditHead_numbers_check" CHECK ((("episodeNo" > 0) AND (revision > 0)))
);


--
-- Name: VideoEpisodeEditVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeEditVersion" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "episodePlanVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "episodeNo" integer NOT NULL,
    "versionNo" integer NOT NULL,
    "basedOnVersionId" text,
    "totalDurationMs" integer NOT NULL,
    "clientRequestId" text NOT NULL,
    "requestHash" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdByUserId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoEpisodeEditVersion_hash_check" CHECK ((("requestHash" ~ '^[0-9a-f]{64}$'::text) AND ("contentHash" ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT "VideoEpisodeEditVersion_numbers_check" CHECK ((("episodeNo" > 0) AND ("versionNo" > 0) AND ("totalDurationMs" > 0))),
    CONSTRAINT "VideoEpisodeEditVersion_request_check" CHECK ((btrim("clientRequestId") <> ''::text))
);


--
-- Name: VideoEpisodeExport; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeExport" (
    id text NOT NULL,
    "taskId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "episodePlanVersionId" text NOT NULL,
    "episodeNo" integer NOT NULL,
    "editVersionId" text NOT NULL,
    "mixVersionId" text NOT NULL,
    "assetId" text NOT NULL,
    "versionNo" integer NOT NULL,
    "inputHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoEpisodeExport_hash_check" CHECK (("inputHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoEpisodeExport_numbers_check" CHECK ((("episodeNo" > 0) AND ("versionNo" > 0)))
);


--
-- Name: VideoEpisodeExportTask; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeExportTask" (
    id text NOT NULL,
    "requestedByUserId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "episodePlanVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "episodeNo" integer NOT NULL,
    "editVersionId" text NOT NULL,
    "mixVersionId" text NOT NULL,
    "retryOfTaskId" text,
    "clientRequestId" text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "inputHash" text NOT NULL,
    "requestManifestJson" text NOT NULL,
    resolution text NOT NULL,
    "framesPerSecond" integer NOT NULL,
    "burnSubtitles" boolean DEFAULT true NOT NULL,
    "attemptCount" integer DEFAULT 0 NOT NULL,
    "nextAttemptAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastErrorCode" text,
    "lastErrorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "startedAt" timestamp(3) without time zone,
    "completedAt" timestamp(3) without time zone,
    CONSTRAINT "VideoEpisodeExportTask_hash_check" CHECK (("inputHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoEpisodeExportTask_manifest_check" CHECK (COALESCE((jsonb_typeof(("requestManifestJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoEpisodeExportTask_numbers_check" CHECK ((("episodeNo" > 0) AND ("attemptCount" >= 0))),
    CONSTRAINT "VideoEpisodeExportTask_output_check" CHECK (((resolution = ANY (ARRAY['720p'::text, '1080p'::text])) AND ("framesPerSecond" = ANY (ARRAY[24, 25, 30])))),
    CONSTRAINT "VideoEpisodeExportTask_request_check" CHECK ((btrim("clientRequestId") <> ''::text)),
    CONSTRAINT "VideoEpisodeExportTask_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'rendering'::text, 'succeeded'::text, 'failed'::text])))
);


--
-- Name: VideoEpisodeMixHead; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeMixHead" (
    "episodePlanVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "episodeNo" integer NOT NULL,
    "currentVersionId" text,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoEpisodeMixHead_numbers_check" CHECK ((("episodeNo" > 0) AND (revision > 0)))
);


--
-- Name: VideoEpisodeMixVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeMixVersion" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "episodePlanVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "episodeNo" integer NOT NULL,
    "editVersionId" text NOT NULL,
    "versionNo" integer NOT NULL,
    "basedOnVersionId" text,
    "clientRequestId" text NOT NULL,
    "requestHash" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdByUserId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoEpisodeMixVersion_hash_check" CHECK ((("requestHash" ~ '^[0-9a-f]{64}$'::text) AND ("contentHash" ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT "VideoEpisodeMixVersion_numbers_check" CHECK ((("episodeNo" > 0) AND ("versionNo" > 0))),
    CONSTRAINT "VideoEpisodeMixVersion_request_check" CHECK ((btrim("clientRequestId") <> ''::text))
);


--
-- Name: VideoEpisodePlanVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodePlanVersion" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "versionNo" integer NOT NULL,
    "basedOnVersionId" text,
    "createdByUserId" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoEpisodePlanVersion_content_hash_check" CHECK (("contentHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoEpisodePlanVersion_version_check" CHECK (("versionNo" > 0))
);


--
-- Name: TABLE "VideoEpisodePlanVersion"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoEpisodePlanVersion" IS '固定引用一个镜头方案版本的不可变分集边界版本';


--
-- Name: VideoEpisodeSubtitleCue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoEpisodeSubtitleCue" (
    "mixVersionId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    ordinal integer NOT NULL,
    "shotId" text,
    "startMs" integer NOT NULL,
    "endMs" integer NOT NULL,
    speaker text,
    text text NOT NULL,
    CONSTRAINT "VideoEpisodeSubtitleCue_range_check" CHECK (((ordinal > 0) AND ("startMs" >= 0) AND ("endMs" > "startMs"))),
    CONSTRAINT "VideoEpisodeSubtitleCue_text_check" CHECK (((btrim(text) <> ''::text) AND ((speaker IS NULL) OR (char_length(speaker) <= 120))))
);


--
-- Name: VideoGenerationTask; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoGenerationTask" (
    id text NOT NULL,
    "projectId" text NOT NULL,
    "sceneId" text NOT NULL,
    "jobId" text NOT NULL,
    kind text NOT NULL,
    provider text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "idempotencyKey" text NOT NULL,
    "providerTaskId" text,
    "requestJson" text NOT NULL,
    "resultJson" text,
    "attemptCount" integer DEFAULT 0 NOT NULL,
    "nextAttemptAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastErrorCode" text,
    "lastErrorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "submittedAt" timestamp(3) without time zone,
    "completedAt" timestamp(3) without time zone,
    CONSTRAINT "VideoGenerationTask_attempt_count_check" CHECK (("attemptCount" >= 0)),
    CONSTRAINT "VideoGenerationTask_kind_check" CHECK ((kind = ANY (ARRAY['plan'::text, 'render'::text, 'poll'::text, 'archive'::text]))),
    CONSTRAINT "VideoGenerationTask_request_json_check" CHECK (COALESCE((jsonb_typeof(("requestJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoGenerationTask_result_json_check" CHECK ((("resultJson" IS NULL) OR COALESCE((jsonb_typeof(("resultJson")::jsonb) = 'object'::text), false))),
    CONSTRAINT "VideoGenerationTask_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'submitted'::text, 'processing'::text, 'awaiting_review'::text, 'completed'::text, 'failed'::text, 'cancelled'::text])))
);


--
-- Name: TABLE "VideoGenerationTask"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoGenerationTask" IS '视频规划、渲染、轮询和归档的耐久任务事实';


--
-- Name: VideoProject; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoProject" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    title text NOT NULL,
    mode text DEFAULT 'highlight'::text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    "targetAspectRatio" text DEFAULT '16:9'::text NOT NULL,
    "targetLanguage" text DEFAULT 'zh-CN'::text NOT NULL,
    provider text DEFAULT 'seedance_2_5'::text NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "deletedAt" timestamp(3) without time zone,
    CONSTRAINT "VideoProject_aspect_ratio_check" CHECK (("targetAspectRatio" = ANY (ARRAY['16:9'::text, '4:3'::text, '1:1'::text, '3:4'::text, '9:16'::text, '21:9'::text, 'adaptive'::text]))),
    CONSTRAINT "VideoProject_mode_check" CHECK ((mode = ANY (ARRAY['concept'::text, 'trailer'::text, 'highlight'::text, 'short_film'::text, 'episode'::text, 'series'::text]))),
    CONSTRAINT "VideoProject_revision_check" CHECK ((revision > 0)),
    CONSTRAINT "VideoProject_status_check" CHECK ((status = ANY (ARRAY['draft'::text, 'active'::text, 'archived'::text]))),
    CONSTRAINT "VideoProject_title_check" CHECK ((btrim(title) <> ''::text))
);


--
-- Name: TABLE "VideoProject"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoProject" IS '小说级视频制作项目';


--
-- Name: VideoReviewDecisionCommand; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoReviewDecisionCommand" (
    id text NOT NULL,
    "requestedByUserId" text NOT NULL,
    "sceneId" text NOT NULL,
    "artifactId" text NOT NULL,
    "sourceTaskId" text NOT NULL,
    decision text DEFAULT 'approve'::text NOT NULL,
    "expectedArtifactRevision" integer NOT NULL,
    "clientRequestId" text NOT NULL,
    "requestHash" text NOT NULL,
    status text DEFAULT 'succeeded'::text NOT NULL,
    "resultJson" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "completedAt" timestamp(3) without time zone NOT NULL,
    "novelId" text NOT NULL,
    "projectId" text NOT NULL,
    CONSTRAINT "VideoReviewDecisionCommand_client_request_check" CHECK ((((char_length("clientRequestId") >= 16) AND (char_length("clientRequestId") <= 128)) AND (btrim("clientRequestId") = "clientRequestId"))),
    CONSTRAINT "VideoReviewDecisionCommand_decision_check" CHECK ((decision = 'approve'::text)),
    CONSTRAINT "VideoReviewDecisionCommand_request_hash_check" CHECK (("requestHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoReviewDecisionCommand_result_json_check" CHECK (COALESCE((jsonb_typeof(("resultJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoReviewDecisionCommand_revision_check" CHECK (("expectedArtifactRevision" > 0)),
    CONSTRAINT "VideoReviewDecisionCommand_status_check" CHECK ((status = 'succeeded'::text))
);


--
-- Name: TABLE "VideoReviewDecisionCommand"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoReviewDecisionCommand" IS '服务器 dev 库中视频候选同步批准的开发预览耐久幂等命令；不代表完整视频 v2 审核命令';


--
-- Name: COLUMN "VideoReviewDecisionCommand"."requestHash"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoReviewDecisionCommand"."requestHash" IS '由动作、场景和预期候选 revision 计算的规范请求 SHA-256';


--
-- Name: COLUMN "VideoReviewDecisionCommand"."resultJson"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoReviewDecisionCommand"."resultJson" IS '首次成功批准返回给浏览器的完整响应，用于网络结果不确定时原样重放';


--
-- Name: COLUMN "VideoReviewDecisionCommand"."novelId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoReviewDecisionCommand"."novelId" IS '与请求用户、视频项目共同受组合外键保护的小说归属';


--
-- Name: COLUMN "VideoReviewDecisionCommand"."projectId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoReviewDecisionCommand"."projectId" IS '与场景、来源任务共同受组合外键保护的视频项目归属';


--
-- Name: VideoScene; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoScene" (
    id text NOT NULL,
    "projectId" text NOT NULL,
    "chapterId" text,
    ordinal integer NOT NULL,
    title text NOT NULL,
    "sourceText" text NOT NULL,
    "sourceHash" text NOT NULL,
    "durationSeconds" integer DEFAULT 15 NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    "planJson" text,
    "promptText" text,
    "promptCharacterCount" integer,
    "lastErrorCode" text,
    "lastErrorMessage" text,
    revision integer DEFAULT 1 NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "novelId" text NOT NULL,
    CONSTRAINT "VideoScene_duration_check" CHECK ((("durationSeconds" >= 4) AND ("durationSeconds" <= 30))),
    CONSTRAINT "VideoScene_plan_json_check" CHECK ((("planJson" IS NULL) OR COALESCE((jsonb_typeof(("planJson")::jsonb) = 'object'::text), false))),
    CONSTRAINT "VideoScene_prompt_count_check" CHECK ((("promptCharacterCount" IS NULL) OR (("promptCharacterCount" >= 1) AND ("promptCharacterCount" <= 2000)))),
    CONSTRAINT "VideoScene_revision_check" CHECK ((revision > 0)),
    CONSTRAINT "VideoScene_source_hash_check" CHECK (("sourceHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoScene_source_text_check" CHECK ((btrim("sourceText") <> ''::text)),
    CONSTRAINT "VideoScene_status_check" CHECK ((status = ANY (ARRAY['draft'::text, 'generating'::text, 'awaiting_review'::text, 'approved'::text, 'rendering'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: TABLE "VideoScene"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoScene" IS '绑定不可变原文快照的可审核视频场景';


--
-- Name: COLUMN "VideoScene"."sourceText"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoScene"."sourceText" IS '用户选定原文的不可变快照，不随章节后续编辑改变';


--
-- Name: COLUMN "VideoScene"."planJson"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoScene"."planJson" IS '用户批准后应用的正式结构化场景方案';


--
-- Name: COLUMN "VideoScene"."novelId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."VideoScene"."novelId" IS '由 VideoProject 冗余并受组合外键保护的小说归属，用于约束章节和审核候选';


--
-- Name: VideoShot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShot" (
    id text NOT NULL,
    "planVersionId" text NOT NULL,
    "sceneId" text NOT NULL,
    "beatId" text NOT NULL,
    "shotKey" text NOT NULL,
    ordinal integer NOT NULL,
    title text NOT NULL,
    "narrativePurpose" text NOT NULL,
    "adaptationType" text NOT NULL,
    "shotScale" text NOT NULL,
    "cameraAngle" text NOT NULL,
    "cameraMovement" text NOT NULL,
    "visualIntent" text NOT NULL,
    "audioMode" text NOT NULL,
    "audioIntent" text NOT NULL,
    "cutReason" text NOT NULL,
    "timelineDurationMs" integer NOT NULL,
    "sourceRelation" text,
    "storyFunction" text,
    "audienceGain" text,
    "coveredGoalKeysJson" text,
    "speechMode" text,
    "spokenText" text,
    CONSTRAINT "VideoShot_adaptation_type_check" CHECK (("adaptationType" = ANY (ARRAY['direct'::text, 'visualized'::text, 'voiceover'::text, 'supplemental'::text]))),
    CONSTRAINT "VideoShot_angle_check" CHECK (("cameraAngle" = ANY (ARRAY['eye_level'::text, 'high_angle'::text, 'low_angle'::text, 'overhead'::text, 'dutch_angle'::text]))),
    CONSTRAINT "VideoShot_audio_mode_check" CHECK (("audioMode" = ANY (ARRAY['sync_dialogue'::text, 'offscreen_dialogue'::text, 'voiceover'::text, 'ambient'::text, 'music'::text, 'silence'::text]))),
    CONSTRAINT "VideoShot_duration_check" CHECK (((("timelineDurationMs" >= 500) AND ("timelineDurationMs" <= 15000)) AND (mod("timelineDurationMs", 500) = 0))),
    CONSTRAINT "VideoShot_goal_driven_fields_check" CHECK (((("sourceRelation" IS NULL) AND ("storyFunction" IS NULL) AND ("audienceGain" IS NULL) AND ("coveredGoalKeysJson" IS NULL) AND ("speechMode" IS NULL) AND ("spokenText" IS NULL)) OR (("sourceRelation" = ANY (ARRAY['direct'::text, 'derived'::text, 'supplemental'::text])) AND COALESCE((btrim("storyFunction") <> ''::text), false) AND COALESCE((btrim("audienceGain") <> ''::text), false) AND COALESCE((jsonb_typeof(("coveredGoalKeysJson")::jsonb) = 'array'::text), false) AND ("speechMode" = ANY (ARRAY['none'::text, 'sync'::text, 'offscreen'::text, 'voiceover'::text])) AND ((("speechMode" = 'none'::text) AND ("spokenText" IS NULL)) OR (("speechMode" <> 'none'::text) AND COALESCE((btrim("spokenText") <> ''::text), false)))))),
    CONSTRAINT "VideoShot_key_check" CHECK (("shotKey" ~ '^S[0-9]{2,3}$'::text)),
    CONSTRAINT "VideoShot_movement_check" CHECK (("cameraMovement" = ANY (ARRAY['locked'::text, 'pan'::text, 'tilt'::text, 'push_in'::text, 'pull_out'::text, 'tracking'::text, 'arc'::text, 'handheld'::text, 'focus_shift'::text]))),
    CONSTRAINT "VideoShot_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoShot_purpose_check" CHECK (("narrativePurpose" = ANY (ARRAY['establishing'::text, 'action'::text, 'dialogue'::text, 'reaction'::text, 'reveal'::text, 'insert'::text, 'transition'::text, 'atmosphere'::text]))),
    CONSTRAINT "VideoShot_scale_check" CHECK (("shotScale" = ANY (ARRAY['extreme_long'::text, 'long'::text, 'medium'::text, 'medium_close'::text, 'close'::text, 'extreme_close'::text, 'over_shoulder'::text, 'two_shot'::text, 'pov'::text]))),
    CONSTRAINT "VideoShot_text_check" CHECK (((btrim(title) <> ''::text) AND (btrim("visualIntent") <> ''::text) AND (btrim("audioIntent") <> ''::text) AND (btrim("cutReason") <> ''::text)))
);


--
-- Name: TABLE "VideoShot"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoShot" IS '正式戏剧节拍中的最终剪辑镜头，不等同于供应商生成片段';


--
-- Name: VideoShotKeyframeHead; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotKeyframeHead" (
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    role text NOT NULL,
    "currentVersionId" text,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoShotKeyframeHead_revision_check" CHECK ((revision > 0)),
    CONSTRAINT "VideoShotKeyframeHead_role_check" CHECK ((role = ANY (ARRAY['initial_state'::text, 'transition_anchor'::text, 'end_state'::text])))
);


--
-- Name: VideoShotKeyframeVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotKeyframeVersion" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    role text NOT NULL,
    "versionNo" integer NOT NULL,
    "basedOnVersionId" text,
    "assetId" text,
    "sourceKind" text NOT NULL,
    "sourceTakeId" text,
    "sourceTimeMs" integer,
    "clientRequestId" text NOT NULL,
    "requestHash" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdByUserId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoShotKeyframeVersion_hash_check" CHECK ((("requestHash" ~ '^[0-9a-f]{64}$'::text) AND ("contentHash" ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT "VideoShotKeyframeVersion_request_check" CHECK ((btrim("clientRequestId") <> ''::text)),
    CONSTRAINT "VideoShotKeyframeVersion_role_check" CHECK ((role = ANY (ARRAY['initial_state'::text, 'transition_anchor'::text, 'end_state'::text]))),
    CONSTRAINT "VideoShotKeyframeVersion_source_check" CHECK (((("sourceKind" = 'cleared'::text) AND ("assetId" IS NULL) AND ("sourceTakeId" IS NULL) AND ("sourceTimeMs" IS NULL)) OR (("sourceKind" = 'asset'::text) AND ("assetId" IS NOT NULL) AND ("sourceTakeId" IS NULL) AND ("sourceTimeMs" IS NULL)) OR (("sourceKind" = 'take_frame'::text) AND ("assetId" IS NOT NULL) AND ("sourceTakeId" IS NOT NULL) AND ("sourceTimeMs" >= 0)))),
    CONSTRAINT "VideoShotKeyframeVersion_source_kind_check" CHECK (("sourceKind" = ANY (ARRAY['asset'::text, 'take_frame'::text, 'cleared'::text]))),
    CONSTRAINT "VideoShotKeyframeVersion_version_check" CHECK (("versionNo" > 0))
);


--
-- Name: VideoShotPlanVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotPlanVersion" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "versionNo" integer NOT NULL,
    "basedOnVersionId" text,
    "sourceTaskId" text NOT NULL,
    "reviewArtifactId" text NOT NULL,
    "createdByUserId" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoShotPlanVersion_content_hash_check" CHECK (("contentHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoShotPlanVersion_version_check" CHECK (("versionNo" > 0))
);


--
-- Name: TABLE "VideoShotPlanVersion"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoShotPlanVersion" IS '用户批准后的不可变章节电影化镜头方案版本';


--
-- Name: VideoShotPromptHead; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotPromptHead" (
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "currentVersionId" text,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoShotPromptHead_revision_check" CHECK ((revision > 0))
);


--
-- Name: VideoShotPromptVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotPromptVersion" (
    id text NOT NULL,
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "versionNo" integer NOT NULL,
    "basedOnVersionId" text,
    "generatedText" text,
    "currentText" text NOT NULL,
    "sourceTaskId" text,
    "createdByUserId" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoShotPromptVersion_content_hash_check" CHECK (("contentHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoShotPromptVersion_text_check" CHECK ((((char_length("currentText") >= 1) AND (char_length("currentText") <= 2000)) AND (("generatedText" IS NULL) OR ((char_length("generatedText") >= 1) AND (char_length("generatedText") <= 2000))))),
    CONSTRAINT "VideoShotPromptVersion_version_check" CHECK (("versionNo" > 0))
);


--
-- Name: TABLE "VideoShotPromptVersion"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoShotPromptVersion" IS '用户明确保存的逐镜即梦提示词不可变版本';


--
-- Name: VideoShotPromptVisualReference; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotPromptVisualReference" (
    "promptVersionId" text NOT NULL,
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    ordinal integer NOT NULL,
    "canonVersionId" text NOT NULL,
    strength integer NOT NULL,
    CONSTRAINT "VideoShotPromptVisualReference_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoShotPromptVisualReference_strength_check" CHECK (((strength >= 1) AND (strength <= 100)))
);


--
-- Name: TABLE "VideoShotPromptVisualReference"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoShotPromptVisualReference" IS '正式提示词版本冻结的视觉参考版本';


--
-- Name: VideoShotRenderTask; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotRenderTask" (
    id text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "promptVersionId" text NOT NULL,
    "retryOfTaskId" text,
    provider text DEFAULT 'seedance'::text NOT NULL,
    model text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "clientRequestId" text NOT NULL,
    "inputHash" text NOT NULL,
    "requestManifestJson" text NOT NULL,
    "providerTaskId" text,
    "pollCount" integer DEFAULT 0 NOT NULL,
    "attemptCount" integer DEFAULT 0 NOT NULL,
    "nextAttemptAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastErrorCode" text,
    "lastErrorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "submittedAt" timestamp(3) without time zone,
    "completedAt" timestamp(3) without time zone,
    CONSTRAINT "VideoShotRenderTask_counts_check" CHECK ((("pollCount" >= 0) AND ("attemptCount" >= 0))),
    CONSTRAINT "VideoShotRenderTask_input_hash_check" CHECK (("inputHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoShotRenderTask_manifest_check" CHECK (COALESCE((jsonb_typeof(("requestManifestJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoShotRenderTask_provider_check" CHECK ((provider = 'seedance'::text)),
    CONSTRAINT "VideoShotRenderTask_provider_task_check" CHECK ((((status = ANY (ARRAY['queued'::text, 'running'::text, 'archiving'::text, 'succeeded'::text])) AND ("providerTaskId" IS NOT NULL)) OR (status <> ALL (ARRAY['queued'::text, 'running'::text, 'archiving'::text, 'succeeded'::text])))),
    CONSTRAINT "VideoShotRenderTask_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'submitting'::text, 'submission_unknown'::text, 'queued'::text, 'running'::text, 'archiving'::text, 'succeeded'::text, 'failed'::text, 'expired'::text, 'cancelled'::text]))),
    CONSTRAINT "VideoShotRenderTask_text_check" CHECK (((btrim(model) <> ''::text) AND (btrim("clientRequestId") <> ''::text)))
);


--
-- Name: VideoShotSourceAnchor; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotSourceAnchor" (
    "shotId" text NOT NULL,
    "planVersionId" text NOT NULL,
    ordinal integer NOT NULL,
    "startCodePoint" integer NOT NULL,
    "endCodePoint" integer NOT NULL,
    CONSTRAINT "VideoShotSourceAnchor_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoShotSourceAnchor_range_check" CHECK ((("startCodePoint" >= 0) AND ("endCodePoint" > "startCodePoint")))
);


--
-- Name: VideoShotTake; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotTake" (
    id text NOT NULL,
    "taskId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "promptVersionId" text NOT NULL,
    "assetId" text NOT NULL,
    "takeNo" integer NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    "providerTaskId" text NOT NULL,
    "inputHash" text NOT NULL,
    "providerMetadataJson" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoShotTake_input_hash_check" CHECK (("inputHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoShotTake_metadata_check" CHECK (COALESCE((jsonb_typeof(("providerMetadataJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "VideoShotTake_provider_check" CHECK ((provider = 'seedance'::text)),
    CONSTRAINT "VideoShotTake_take_no_check" CHECK (("takeNo" > 0)),
    CONSTRAINT "VideoShotTake_text_check" CHECK (((btrim(model) <> ''::text) AND (btrim("providerTaskId") <> ''::text)))
);


--
-- Name: VideoShotTakeDecisionCommand; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotTakeDecisionCommand" (
    id text NOT NULL,
    "requestedByUserId" text NOT NULL,
    "novelId" text NOT NULL,
    "projectId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "shotId" text NOT NULL,
    "takeId" text NOT NULL,
    "clientRequestId" text NOT NULL,
    "expectedRevision" integer NOT NULL,
    "requestHash" text NOT NULL,
    status text NOT NULL,
    "observedCurrentTakeId" text,
    "resultingRevision" integer,
    "errorCode" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoShotTakeDecisionCommand_request_hash_check" CHECK (("requestHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoShotTakeDecisionCommand_result_check" CHECK ((((status = 'succeeded'::text) AND ("observedCurrentTakeId" = "takeId") AND ("resultingRevision" IS NOT NULL) AND ("errorCode" IS NULL)) OR ((status <> 'succeeded'::text) AND ("resultingRevision" IS NULL) AND ("errorCode" IS NOT NULL)))),
    CONSTRAINT "VideoShotTakeDecisionCommand_revision_check" CHECK ((("expectedRevision" > 0) AND (("resultingRevision" IS NULL) OR ("resultingRevision" > 0)))),
    CONSTRAINT "VideoShotTakeDecisionCommand_status_check" CHECK ((status = ANY (ARRAY['succeeded'::text, 'conflict'::text, 'rejected'::text]))),
    CONSTRAINT "VideoShotTakeDecisionCommand_text_check" CHECK ((btrim("clientRequestId") <> ''::text))
);


--
-- Name: VideoShotTakeHead; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotTakeHead" (
    "shotId" text NOT NULL,
    "shotPlanVersionId" text NOT NULL,
    "currentTakeId" text,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoShotTakeHead_revision_check" CHECK ((revision > 0))
);


--
-- Name: VideoShotVisualReferenceBinding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotVisualReferenceBinding" (
    "shotId" text NOT NULL,
    ordinal integer NOT NULL,
    "planVersionId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "canonVersionId" text NOT NULL,
    strength integer NOT NULL,
    CONSTRAINT "VideoShotVisualReferenceBinding_ordinal_check" CHECK ((ordinal > 0)),
    CONSTRAINT "VideoShotVisualReferenceBinding_strength_check" CHECK (((strength >= 1) AND (strength <= 100)))
);


--
-- Name: TABLE "VideoShotVisualReferenceBinding"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoShotVisualReferenceBinding" IS '镜头参考集合中的有序视觉版本与参考强度';


--
-- Name: VideoShotVisualReferenceSet; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoShotVisualReferenceSet" (
    "shotId" text NOT NULL,
    "planVersionId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoShotVisualReferenceSet_revision_check" CHECK ((revision > 0))
);


--
-- Name: TABLE "VideoShotVisualReferenceSet"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoShotVisualReferenceSet" IS '正式镜头当前视觉参考集合的 CAS Head';


--
-- Name: VideoTakeFrameExtraction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoTakeFrameExtraction" (
    "assetId" text NOT NULL,
    "takeId" text NOT NULL,
    "shotId" text NOT NULL,
    "adaptationId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "timestampMs" integer NOT NULL,
    "clientRequestId" text NOT NULL,
    "requestHash" text NOT NULL,
    "requestedByUserId" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "VideoTakeFrameExtraction_hash_check" CHECK (("requestHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoTakeFrameExtraction_request_check" CHECK ((btrim("clientRequestId") <> ''::text)),
    CONSTRAINT "VideoTakeFrameExtraction_time_check" CHECK (("timestampMs" >= 0))
);


--
-- Name: VideoVisualCanon; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoVisualCanon" (
    id text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "settingKind" text NOT NULL,
    "settingId" text NOT NULL,
    "settingName" text NOT NULL,
    duty text NOT NULL,
    "variantKey" text NOT NULL,
    label text NOT NULL,
    "candidateAssetId" text,
    "candidateIncludeFeaturesJson" text,
    "candidateExcludeFeaturesJson" text,
    "candidateDefaultStrength" integer,
    "currentVersionId" text,
    revision integer DEFAULT 1 NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "VideoVisualCanon_candidate_check" CHECK (((("candidateAssetId" IS NULL) AND ("candidateIncludeFeaturesJson" IS NULL) AND ("candidateExcludeFeaturesJson" IS NULL) AND ("candidateDefaultStrength" IS NULL)) OR (("candidateAssetId" IS NOT NULL) AND COALESCE((jsonb_typeof(("candidateIncludeFeaturesJson")::jsonb) = 'array'::text), false) AND COALESCE((jsonb_typeof(("candidateExcludeFeaturesJson")::jsonb) = 'array'::text), false) AND (("candidateDefaultStrength" >= 1) AND ("candidateDefaultStrength" <= 100))))),
    CONSTRAINT "VideoVisualCanon_kind_duty_check" CHECK (((("settingKind" = 'character'::text) AND (duty = ANY (ARRAY['identity'::text, 'costume'::text]))) OR (("settingKind" = 'location'::text) AND (duty = 'scene'::text)) OR (("settingKind" = 'item'::text) AND (duty = 'prop'::text)))),
    CONSTRAINT "VideoVisualCanon_revision_check" CHECK ((revision > 0)),
    CONSTRAINT "VideoVisualCanon_text_check" CHECK (((btrim("settingId") <> ''::text) AND (btrim("settingName") <> ''::text) AND (btrim(label) <> ''::text) AND ("variantKey" ~ '^[a-z0-9][a-z0-9_-]{0,63}$'::text)))
);


--
-- Name: TABLE "VideoVisualCanon"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoVisualCanon" IS '项目内文字设定对应的候选和当前视觉设定槽';


--
-- Name: VideoVisualCanonVersion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."VideoVisualCanonVersion" (
    id text NOT NULL,
    "canonId" text NOT NULL,
    "projectId" text NOT NULL,
    "novelId" text NOT NULL,
    "versionNo" integer NOT NULL,
    "assetId" text NOT NULL,
    "includeFeaturesJson" text NOT NULL,
    "excludeFeaturesJson" text NOT NULL,
    "defaultStrength" integer NOT NULL,
    "approvedByUserId" text NOT NULL,
    "contentHash" text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "settingName" text NOT NULL,
    label text NOT NULL,
    CONSTRAINT "VideoVisualCanonVersion_features_check" CHECK ((COALESCE((jsonb_typeof(("includeFeaturesJson")::jsonb) = 'array'::text), false) AND COALESCE((jsonb_typeof(("excludeFeaturesJson")::jsonb) = 'array'::text), false))),
    CONSTRAINT "VideoVisualCanonVersion_hash_check" CHECK (("contentHash" ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT "VideoVisualCanonVersion_strength_check" CHECK ((("defaultStrength" >= 1) AND ("defaultStrength" <= 100))),
    CONSTRAINT "VideoVisualCanonVersion_text_check" CHECK (((btrim("settingName") <> ''::text) AND (btrim(label) <> ''::text))),
    CONSTRAINT "VideoVisualCanonVersion_version_check" CHECK (("versionNo" > 0))
);


--
-- Name: TABLE "VideoVisualCanonVersion"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."VideoVisualCanonVersion" IS '用户批准后引用已锁定图片的不可变视觉设定版本';


--
-- Name: WorkflowRun; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WorkflowRun" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "chapterId" text NOT NULL,
    "userId" text,
    kind public."WorkflowRunKind" NOT NULL,
    status public."WorkflowRunStatus" DEFAULT 'pending'::public."WorkflowRunStatus" NOT NULL,
    "sourceType" text,
    "sourceId" text,
    "currentAgentId" text,
    input text,
    output text,
    "errorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: WorkflowStep; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WorkflowStep" (
    id text NOT NULL,
    "runId" text NOT NULL,
    "agentId" text,
    "stepType" public."WorkflowStepType" NOT NULL,
    status public."WorkflowStepStatus" DEFAULT 'pending'::public."WorkflowStepStatus" NOT NULL,
    input text,
    output text,
    "durationMs" integer,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: WorldSetting; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WorldSetting" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: WritingBible; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingBible" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    genre text,
    "targetReaders" text,
    "coreSellingPoint" text,
    "readerPromise" text,
    "appealModel" text,
    taboo text,
    "comparableTitles" text,
    notes text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "storyLengthProfile" public."StoryLengthProfile" DEFAULT 'long_serial'::public."StoryLengthProfile" NOT NULL,
    "targetTotalWordCount" integer
);


--
-- Name: WritingConfig; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingConfig" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "defaultWordCount" integer DEFAULT 4000 NOT NULL,
    "enabledAgents" text DEFAULT '设定,剧情,写作,校验,编辑'::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: WritingEventOutbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingEventOutbox" (
    id text NOT NULL,
    "taskId" text NOT NULL,
    "commandId" text,
    "sourceEventId" text NOT NULL,
    "sourceSequence" integer NOT NULL,
    "durableBaseline" integer NOT NULL,
    "dedupeKey" text NOT NULL,
    "eventType" text NOT NULL,
    "payloadJson" text NOT NULL,
    "deliveryState" text DEFAULT 'pending'::text NOT NULL,
    "attemptCount" integer DEFAULT 0 NOT NULL,
    "nextAttemptAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "leaseToken" text,
    "leaseExpiresAt" timestamp(3) without time zone,
    "lastErrorCode" text,
    "redisEventId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "publishedAt" timestamp(3) without time zone,
    CONSTRAINT "WritingEventOutbox_attemptCount_check" CHECK (("attemptCount" >= 0)),
    CONSTRAINT "WritingEventOutbox_dedupeKey_check" CHECK ((btrim("dedupeKey") <> ''::text)),
    CONSTRAINT "WritingEventOutbox_deliveryState_check" CHECK (("deliveryState" = ANY (ARRAY['pending'::text, 'delivering'::text, 'published'::text, 'blocked'::text, 'superseded'::text]))),
    CONSTRAINT "WritingEventOutbox_durableBaseline_check" CHECK ((("durableBaseline" >= 0) AND ("durableBaseline" < "sourceSequence"))),
    CONSTRAINT "WritingEventOutbox_eventType_check" CHECK (("eventType" = ANY (ARRAY['completed'::text, 'error'::text, 'artifact_awaiting_user_approval'::text]))),
    CONSTRAINT "WritingEventOutbox_lease_check" CHECK (((("deliveryState" = 'delivering'::text) AND ("leaseToken" IS NOT NULL) AND ("leaseExpiresAt" IS NOT NULL)) OR (("deliveryState" <> 'delivering'::text) AND ("leaseToken" IS NULL) AND ("leaseExpiresAt" IS NULL)))),
    CONSTRAINT "WritingEventOutbox_payloadJson_check" CHECK (COALESCE((jsonb_typeof(("payloadJson")::jsonb) = 'object'::text), false)),
    CONSTRAINT "WritingEventOutbox_published_check" CHECK (((("deliveryState" = 'published'::text) AND ("redisEventId" IS NOT NULL) AND ("publishedAt" IS NOT NULL)) OR (("deliveryState" <> 'published'::text) AND ("redisEventId" IS NULL) AND ("publishedAt" IS NULL)))),
    CONSTRAINT "WritingEventOutbox_sourceEventId_check" CHECK ((btrim("sourceEventId") <> ''::text)),
    CONSTRAINT "WritingEventOutbox_sourceSequence_check" CHECK (("sourceSequence" > 0))
);


--
-- Name: TABLE "WritingEventOutbox"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public."WritingEventOutbox" IS '写作边界事件事务发件箱';


--
-- Name: COLUMN "WritingEventOutbox"."taskId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."taskId" IS '产生业务事实的写作任务';


--
-- Name: COLUMN "WritingEventOutbox"."commandId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."commandId" IS '产生边界事实的运行命令，命令删除后保留事件';


--
-- Name: COLUMN "WritingEventOutbox"."sourceEventId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."sourceEventId" IS 'Agent 回调提供的稳定来源事件标识';


--
-- Name: COLUMN "WritingEventOutbox"."sourceSequence"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."sourceSequence" IS '任务内严格递增的来源序号';


--
-- Name: COLUMN "WritingEventOutbox"."durableBaseline"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."durableBaseline" IS '业务事务提交前已持久化的事件序号基线';


--
-- Name: COLUMN "WritingEventOutbox"."dedupeKey"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."dedupeKey" IS '同一业务边界的唯一幂等键';


--
-- Name: COLUMN "WritingEventOutbox"."eventType"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."eventType" IS '允许通知的持久化业务边界类型';


--
-- Name: COLUMN "WritingEventOutbox"."payloadJson"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."payloadJson" IS 'Redis Stream 通知所需的最小 JSON 对象';


--
-- Name: COLUMN "WritingEventOutbox"."deliveryState"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."deliveryState" IS '通知投递状态，不代表业务执行结果';


--
-- Name: COLUMN "WritingEventOutbox"."attemptCount"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."attemptCount" IS '已获得投递租约的累计次数';


--
-- Name: COLUMN "WritingEventOutbox"."nextAttemptAt"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."nextAttemptAt" IS 'pending 状态的下一次可领取时间';


--
-- Name: COLUMN "WritingEventOutbox"."leaseToken"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."leaseToken" IS '当前投递租约的所有权令牌';


--
-- Name: COLUMN "WritingEventOutbox"."leaseExpiresAt"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."leaseExpiresAt" IS '当前投递租约的到期时间';


--
-- Name: COLUMN "WritingEventOutbox"."lastErrorCode"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."lastErrorCode" IS '最近一次可诊断的稳定错误码';


--
-- Name: COLUMN "WritingEventOutbox"."redisEventId"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."redisEventId" IS '成功写入 Redis Stream 后返回的游标';


--
-- Name: COLUMN "WritingEventOutbox"."publishedAt"; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public."WritingEventOutbox"."publishedAt" IS 'Redis Stream 已确认接收的时间';


--
-- Name: WritingMessage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingMessage" (
    id text NOT NULL,
    "sessionId" text NOT NULL,
    role text NOT NULL,
    "agentId" text,
    content text NOT NULL,
    intent text,
    metadata text,
    "parentId" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: WritingRunCommand; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingRunCommand" (
    id text NOT NULL,
    "taskId" text NOT NULL,
    kind text NOT NULL,
    "artifactId" text,
    decision text,
    "payloadJson" text NOT NULL,
    "resultJson" text,
    "idempotencyKey" text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    "attemptCount" integer DEFAULT 0 NOT NULL,
    "nextAttemptAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lastError" text,
    "submittedAt" timestamp(3) without time zone,
    "completedAt" timestamp(3) without time zone,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    CONSTRAINT "WritingRunCommand_decision_check" CHECK (((decision IS NULL) OR (decision = ANY (ARRAY['approve'::text, 'discard'::text, 'revise'::text])))),
    CONSTRAINT "WritingRunCommand_kind_check" CHECK ((kind = ANY (ARRAY['start'::text, 'resume'::text, 'artifact_decision'::text]))),
    CONSTRAINT "WritingRunCommand_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'submitted'::text, 'processing'::text, 'succeeded'::text, 'failed'::text])))
);


--
-- Name: WritingSession; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingSession" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "chapterId" text NOT NULL,
    title text,
    phase text DEFAULT 'idle'::text NOT NULL,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);


--
-- Name: WritingStyle; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingStyle" (
    id text NOT NULL,
    name text NOT NULL,
    "sourceType" public."StyleSourceType" DEFAULT 'manual'::public."StyleSourceType" NOT NULL,
    "creativeMethodology" text,
    "uniqueMarkers" text,
    "generationStyle" text,
    "expressionFeatures" text,
    "styleTraits" text,
    "portraitMarkdown" text,
    "originalCharCount" integer DEFAULT 0 NOT NULL,
    "usedCharCount" integer DEFAULT 0 NOT NULL,
    truncated boolean DEFAULT false NOT NULL,
    "errorMessage" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "userId" text NOT NULL
);


--
-- Name: WritingTask; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."WritingTask" (
    id text NOT NULL,
    "novelId" text NOT NULL,
    "chapterId" text NOT NULL,
    "targetWordCount" integer NOT NULL,
    "selectedAgents" text NOT NULL,
    phase public."WritingTaskPhase" DEFAULT 'idle'::public."WritingTaskPhase" NOT NULL,
    "agentOutputs" text,
    "generatedContent" text,
    "finalContent" text,
    "conversationHistory" text,
    "foreshadowingUpdates" text,
    "outlineUpdates" text,
    "characterChanges" text,
    "createdAt" timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "graphStateJson" text,
    "writingSessionId" text
);


--
-- Name: _FactionTerritories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."_FactionTerritories" (
    "A" text NOT NULL,
    "B" text NOT NULL
);


--
-- Name: _prisma_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public._prisma_migrations (
    id character varying(36) NOT NULL,
    checksum character varying(64) NOT NULL,
    finished_at timestamp with time zone,
    migration_name character varying(255) NOT NULL,
    logs text,
    rolled_back_at timestamp with time zone,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_steps_count integer DEFAULT 0 NOT NULL
);


--
-- Name: ChapterBeatPlan ChapterBeatPlan_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterBeatPlan"
    ADD CONSTRAINT "ChapterBeatPlan_pkey" PRIMARY KEY (id);


--
-- Name: ChapterProgress ChapterProgress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterProgress"
    ADD CONSTRAINT "ChapterProgress_pkey" PRIMARY KEY (id);


--
-- Name: ChapterQualityCheck ChapterQualityCheck_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterQualityCheck"
    ADD CONSTRAINT "ChapterQualityCheck_pkey" PRIMARY KEY (id);


--
-- Name: ChapterWritingGoal ChapterWritingGoal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterWritingGoal"
    ADD CONSTRAINT "ChapterWritingGoal_pkey" PRIMARY KEY (id);


--
-- Name: Chapter Chapter_id_novelId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Chapter"
    ADD CONSTRAINT "Chapter_id_novelId_key" UNIQUE (id, "novelId");


--
-- Name: Chapter Chapter_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Chapter"
    ADD CONSTRAINT "Chapter_pkey" PRIMARY KEY (id);


--
-- Name: CharacterExperience CharacterExperience_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterExperience"
    ADD CONSTRAINT "CharacterExperience_pkey" PRIMARY KEY (id);


--
-- Name: CharacterRelation CharacterRelation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterRelation"
    ADD CONSTRAINT "CharacterRelation_pkey" PRIMARY KEY (id);


--
-- Name: CharacterStateChange CharacterStateChange_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterStateChange"
    ADD CONSTRAINT "CharacterStateChange_pkey" PRIMARY KEY (id);


--
-- Name: Character Character_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Character"
    ADD CONSTRAINT "Character_pkey" PRIMARY KEY (id);


--
-- Name: CreditLedger CreditLedger_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CreditLedger"
    ADD CONSTRAINT "CreditLedger_pkey" PRIMARY KEY (id);


--
-- Name: Faction Faction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Faction"
    ADD CONSTRAINT "Faction_pkey" PRIMARY KEY (id);


--
-- Name: Foreshadowing Foreshadowing_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Foreshadowing"
    ADD CONSTRAINT "Foreshadowing_pkey" PRIMARY KEY (id);


--
-- Name: Glossary Glossary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Glossary"
    ADD CONSTRAINT "Glossary_pkey" PRIMARY KEY (id);


--
-- Name: Item Item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Item"
    ADD CONSTRAINT "Item_pkey" PRIMARY KEY (id);


--
-- Name: Location Location_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Location"
    ADD CONSTRAINT "Location_pkey" PRIMARY KEY (id);


--
-- Name: Novel Novel_id_userId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Novel"
    ADD CONSTRAINT "Novel_id_userId_key" UNIQUE (id, "userId");


--
-- Name: Novel Novel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Novel"
    ADD CONSTRAINT "Novel_pkey" PRIMARY KEY (id);


--
-- Name: OutlineNode OutlineNode_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OutlineNode"
    ADD CONSTRAINT "OutlineNode_pkey" PRIMARY KEY (id);


--
-- Name: Outline Outline_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Outline"
    ADD CONSTRAINT "Outline_pkey" PRIMARY KEY (id);


--
-- Name: PlotProgress PlotProgress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PlotProgress"
    ADD CONSTRAINT "PlotProgress_pkey" PRIMARY KEY (id);


--
-- Name: RagChunk RagChunk_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RagChunk"
    ADD CONSTRAINT "RagChunk_pkey" PRIMARY KEY (id);


--
-- Name: RagDocument RagDocument_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RagDocument"
    ADD CONSTRAINT "RagDocument_pkey" PRIMARY KEY (id);


--
-- Name: ReferenceMaterial ReferenceMaterial_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReferenceMaterial"
    ADD CONSTRAINT "ReferenceMaterial_pkey" PRIMARY KEY (id);


--
-- Name: ReviewArtifactEvaluation ReviewArtifactEvaluation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifactEvaluation"
    ADD CONSTRAINT "ReviewArtifactEvaluation_pkey" PRIMARY KEY (id);


--
-- Name: ReviewArtifactRevision ReviewArtifactRevision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifactRevision"
    ADD CONSTRAINT "ReviewArtifactRevision_pkey" PRIMARY KEY (id);


--
-- Name: ReviewArtifact ReviewArtifact_id_videoSceneId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_id_videoSceneId_key" UNIQUE (id, "videoSceneId");


--
-- Name: ReviewArtifact ReviewArtifact_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_pkey" PRIMARY KEY (id);


--
-- Name: SceneBeat SceneBeat_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SceneBeat"
    ADD CONSTRAINT "SceneBeat_pkey" PRIMARY KEY (id);


--
-- Name: StoryBackground StoryBackground_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."StoryBackground"
    ADD CONSTRAINT "StoryBackground_pkey" PRIMARY KEY (id);


--
-- Name: StylePortraitTask StylePortraitTask_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."StylePortraitTask"
    ADD CONSTRAINT "StylePortraitTask_pkey" PRIMARY KEY (id);


--
-- Name: StyleReference StyleReference_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."StyleReference"
    ADD CONSTRAINT "StyleReference_pkey" PRIMARY KEY (id);


--
-- Name: TokenUsage TokenUsage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."TokenUsage"
    ADD CONSTRAINT "TokenUsage_pkey" PRIMARY KEY (id);


--
-- Name: User User_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_pkey" PRIMARY KEY (id);


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_pkey" PRIMARY KEY (id);


--
-- Name: VideoAdaptationTask VideoAdaptationTask_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationTask"
    ADD CONSTRAINT "VideoAdaptationTask_pkey" PRIMARY KEY (id);


--
-- Name: VideoAssetBinding VideoAssetBinding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_pkey" PRIMARY KEY (id);


--
-- Name: VideoAssetBinding VideoAssetBinding_scene_asset_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_scene_asset_key" UNIQUE ("sceneId", "assetId");


--
-- Name: VideoAsset VideoAsset_id_projectId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAsset"
    ADD CONSTRAINT "VideoAsset_id_projectId_key" UNIQUE (id, "projectId");


--
-- Name: VideoAsset VideoAsset_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAsset"
    ADD CONSTRAINT "VideoAsset_pkey" PRIMARY KEY (id);


--
-- Name: VideoAsset VideoAsset_project_storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAsset"
    ADD CONSTRAINT "VideoAsset_project_storage_key" UNIQUE ("projectId", "storageKey");


--
-- Name: VideoChapterAdaptationHead VideoChapterAdaptationHead_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_pkey" PRIMARY KEY ("adaptationId");


--
-- Name: VideoChapterAdaptation VideoChapterAdaptation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptation"
    ADD CONSTRAINT "VideoChapterAdaptation_pkey" PRIMARY KEY (id);


--
-- Name: VideoCinematicScene VideoCinematicScene_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoCinematicScene"
    ADD CONSTRAINT "VideoCinematicScene_pkey" PRIMARY KEY (id);


--
-- Name: VideoCinematicScene VideoCinematicScene_plan_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoCinematicScene"
    ADD CONSTRAINT "VideoCinematicScene_plan_key_key" UNIQUE ("planVersionId", "sceneKey");


--
-- Name: VideoCinematicScene VideoCinematicScene_plan_ordinal_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoCinematicScene"
    ADD CONSTRAINT "VideoCinematicScene_plan_ordinal_key" UNIQUE ("planVersionId", ordinal);


--
-- Name: VideoDramaticBeatSourceAnchor VideoDramaticBeatSourceAnchor_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoDramaticBeatSourceAnchor"
    ADD CONSTRAINT "VideoDramaticBeatSourceAnchor_pkey" PRIMARY KEY ("beatId", ordinal);


--
-- Name: VideoDramaticBeat VideoDramaticBeat_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoDramaticBeat"
    ADD CONSTRAINT "VideoDramaticBeat_pkey" PRIMARY KEY (id);


--
-- Name: VideoDramaticBeat VideoDramaticBeat_plan_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoDramaticBeat"
    ADD CONSTRAINT "VideoDramaticBeat_plan_key_key" UNIQUE ("planVersionId", "beatKey");


--
-- Name: VideoDramaticBeat VideoDramaticBeat_plan_ordinal_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoDramaticBeat"
    ADD CONSTRAINT "VideoDramaticBeat_plan_ordinal_key" UNIQUE ("planVersionId", ordinal);


--
-- Name: VideoEpisodeAudioClip VideoEpisodeAudioClip_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeAudioClip"
    ADD CONSTRAINT "VideoEpisodeAudioClip_pkey" PRIMARY KEY ("mixVersionId", ordinal);


--
-- Name: VideoEpisodeBoundary VideoEpisodeBoundary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeBoundary"
    ADD CONSTRAINT "VideoEpisodeBoundary_pkey" PRIMARY KEY ("episodePlanVersionId", ordinal);


--
-- Name: VideoEpisodeBoundary VideoEpisodeBoundary_version_shot_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeBoundary"
    ADD CONSTRAINT "VideoEpisodeBoundary_version_shot_key" UNIQUE ("episodePlanVersionId", "afterShotId");


--
-- Name: VideoEpisodeEditClip VideoEpisodeEditClip_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditClip"
    ADD CONSTRAINT "VideoEpisodeEditClip_pkey" PRIMARY KEY ("editVersionId", ordinal);


--
-- Name: VideoEpisodeEditHead VideoEpisodeEditHead_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditHead"
    ADD CONSTRAINT "VideoEpisodeEditHead_pkey" PRIMARY KEY ("episodePlanVersionId", "episodeNo");


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_id_episode_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_id_episode_key" UNIQUE (id, "episodePlanVersionId", "episodeNo");


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_id_scope_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_id_scope_key" UNIQUE (id, "adaptationId", "episodeNo");


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_pkey" PRIMARY KEY (id);


--
-- Name: VideoEpisodeExport VideoEpisodeExport_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExport"
    ADD CONSTRAINT "VideoEpisodeExport_pkey" PRIMARY KEY (id);


--
-- Name: VideoEpisodeMixHead VideoEpisodeMixHead_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixHead"
    ADD CONSTRAINT "VideoEpisodeMixHead_pkey" PRIMARY KEY ("episodePlanVersionId", "episodeNo");


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_id_episode_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_id_episode_key" UNIQUE (id, "episodePlanVersionId", "episodeNo");


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoEpisodePlanVersion VideoEpisodePlanVersion_adaptation_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodePlanVersion"
    ADD CONSTRAINT "VideoEpisodePlanVersion_adaptation_version_key" UNIQUE ("adaptationId", "versionNo");


--
-- Name: VideoEpisodePlanVersion VideoEpisodePlanVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodePlanVersion"
    ADD CONSTRAINT "VideoEpisodePlanVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoEpisodeSubtitleCue VideoEpisodeSubtitleCue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeSubtitleCue"
    ADD CONSTRAINT "VideoEpisodeSubtitleCue_pkey" PRIMARY KEY ("mixVersionId", ordinal);


--
-- Name: VideoGenerationTask VideoGenerationTask_id_sceneId_projectId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_id_sceneId_projectId_key" UNIQUE (id, "sceneId", "projectId");


--
-- Name: VideoGenerationTask VideoGenerationTask_idempotencyKey_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_idempotencyKey_key" UNIQUE ("idempotencyKey");


--
-- Name: VideoGenerationTask VideoGenerationTask_jobId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_jobId_key" UNIQUE ("jobId");


--
-- Name: VideoGenerationTask VideoGenerationTask_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_pkey" PRIMARY KEY (id);


--
-- Name: VideoProject VideoProject_id_novelId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoProject"
    ADD CONSTRAINT "VideoProject_id_novelId_key" UNIQUE (id, "novelId");


--
-- Name: VideoProject VideoProject_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoProject"
    ADD CONSTRAINT "VideoProject_pkey" PRIMARY KEY (id);


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_pkey" PRIMARY KEY (id);


--
-- Name: VideoScene VideoScene_id_novelId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_id_novelId_key" UNIQUE (id, "novelId");


--
-- Name: VideoScene VideoScene_id_projectId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_id_projectId_key" UNIQUE (id, "projectId");


--
-- Name: VideoScene VideoScene_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_pkey" PRIMARY KEY (id);


--
-- Name: VideoScene VideoScene_project_ordinal_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_project_ordinal_key" UNIQUE ("projectId", ordinal);


--
-- Name: VideoShotKeyframeHead VideoShotKeyframeHead_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeHead"
    ADD CONSTRAINT "VideoShotKeyframeHead_pkey" PRIMARY KEY ("shotId", role);


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_id_shot_role_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_id_shot_role_key" UNIQUE (id, "shotId", role);


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_adaptation_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_adaptation_version_key" UNIQUE ("adaptationId", "versionNo");


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_reviewArtifactId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_reviewArtifactId_key" UNIQUE ("reviewArtifactId");


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_sourceTaskId_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_sourceTaskId_key" UNIQUE ("sourceTaskId");


--
-- Name: VideoShotPromptHead VideoShotPromptHead_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptHead"
    ADD CONSTRAINT "VideoShotPromptHead_pkey" PRIMARY KEY ("shotId");


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_shot_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_shot_version_key" UNIQUE ("shotId", "versionNo");


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_pkey" PRIMARY KEY ("promptVersionId", ordinal);


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_prompt_canon_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_prompt_canon_key" UNIQUE ("promptVersionId", "canonVersionId");


--
-- Name: VideoShotRenderTask VideoShotRenderTask_id_shot_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_id_shot_key" UNIQUE (id, "shotId");


--
-- Name: VideoShotRenderTask VideoShotRenderTask_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_pkey" PRIMARY KEY (id);


--
-- Name: VideoShotSourceAnchor VideoShotSourceAnchor_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotSourceAnchor"
    ADD CONSTRAINT "VideoShotSourceAnchor_pkey" PRIMARY KEY ("shotId", ordinal);


--
-- Name: VideoShotTakeDecisionCommand VideoShotTakeDecisionCommand_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeDecisionCommand"
    ADD CONSTRAINT "VideoShotTakeDecisionCommand_pkey" PRIMARY KEY (id);


--
-- Name: VideoShotTakeHead VideoShotTakeHead_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeHead"
    ADD CONSTRAINT "VideoShotTakeHead_pkey" PRIMARY KEY ("shotId");


--
-- Name: VideoShotTake VideoShotTake_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTake"
    ADD CONSTRAINT "VideoShotTake_pkey" PRIMARY KEY (id);


--
-- Name: VideoShotVisualReferenceBinding VideoShotVisualReferenceBinding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceBinding"
    ADD CONSTRAINT "VideoShotVisualReferenceBinding_pkey" PRIMARY KEY ("shotId", ordinal);


--
-- Name: VideoShotVisualReferenceBinding VideoShotVisualReferenceBinding_shot_canon_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceBinding"
    ADD CONSTRAINT "VideoShotVisualReferenceBinding_shot_canon_key" UNIQUE ("shotId", "canonVersionId");


--
-- Name: VideoShotVisualReferenceSet VideoShotVisualReferenceSet_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceSet"
    ADD CONSTRAINT "VideoShotVisualReferenceSet_pkey" PRIMARY KEY ("shotId");


--
-- Name: VideoShot VideoShot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShot"
    ADD CONSTRAINT "VideoShot_pkey" PRIMARY KEY (id);


--
-- Name: VideoShot VideoShot_plan_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShot"
    ADD CONSTRAINT "VideoShot_plan_key_key" UNIQUE ("planVersionId", "shotKey");


--
-- Name: VideoShot VideoShot_plan_ordinal_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShot"
    ADD CONSTRAINT "VideoShot_plan_ordinal_key" UNIQUE ("planVersionId", ordinal);


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_asset_take_time_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_asset_take_time_key" UNIQUE ("assetId", "takeId", "timestampMs");


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_pkey" PRIMARY KEY ("assetId");


--
-- Name: VideoVisualCanonVersion VideoVisualCanonVersion_canon_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanonVersion"
    ADD CONSTRAINT "VideoVisualCanonVersion_canon_version_key" UNIQUE ("canonId", "versionNo");


--
-- Name: VideoVisualCanonVersion VideoVisualCanonVersion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanonVersion"
    ADD CONSTRAINT "VideoVisualCanonVersion_pkey" PRIMARY KEY (id);


--
-- Name: VideoVisualCanon VideoVisualCanon_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanon"
    ADD CONSTRAINT "VideoVisualCanon_pkey" PRIMARY KEY (id);


--
-- Name: WorkflowRun WorkflowRun_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WorkflowRun"
    ADD CONSTRAINT "WorkflowRun_pkey" PRIMARY KEY (id);


--
-- Name: WorkflowStep WorkflowStep_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WorkflowStep"
    ADD CONSTRAINT "WorkflowStep_pkey" PRIMARY KEY (id);


--
-- Name: WorldSetting WorldSetting_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WorldSetting"
    ADD CONSTRAINT "WorldSetting_pkey" PRIMARY KEY (id);


--
-- Name: WritingBible WritingBible_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingBible"
    ADD CONSTRAINT "WritingBible_pkey" PRIMARY KEY (id);


--
-- Name: WritingConfig WritingConfig_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingConfig"
    ADD CONSTRAINT "WritingConfig_pkey" PRIMARY KEY (id);


--
-- Name: WritingEventOutbox WritingEventOutbox_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingEventOutbox"
    ADD CONSTRAINT "WritingEventOutbox_pkey" PRIMARY KEY (id);


--
-- Name: WritingMessage WritingMessage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingMessage"
    ADD CONSTRAINT "WritingMessage_pkey" PRIMARY KEY (id);


--
-- Name: WritingRunCommand WritingRunCommand_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingRunCommand"
    ADD CONSTRAINT "WritingRunCommand_pkey" PRIMARY KEY (id);


--
-- Name: WritingSession WritingSession_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingSession"
    ADD CONSTRAINT "WritingSession_pkey" PRIMARY KEY (id);


--
-- Name: WritingStyle WritingStyle_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingStyle"
    ADD CONSTRAINT "WritingStyle_pkey" PRIMARY KEY (id);


--
-- Name: WritingTask WritingTask_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingTask"
    ADD CONSTRAINT "WritingTask_pkey" PRIMARY KEY (id);


--
-- Name: _FactionTerritories _FactionTerritories_AB_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."_FactionTerritories"
    ADD CONSTRAINT "_FactionTerritories_AB_pkey" PRIMARY KEY ("A", "B");


--
-- Name: _prisma_migrations _prisma_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public._prisma_migrations
    ADD CONSTRAINT _prisma_migrations_pkey PRIMARY KEY (id);


--
-- Name: ChapterBeatPlan_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ChapterBeatPlan_chapterId_idx" ON public."ChapterBeatPlan" USING btree ("chapterId");


--
-- Name: ChapterBeatPlan_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ChapterBeatPlan_status_idx" ON public."ChapterBeatPlan" USING btree (status);


--
-- Name: ChapterProgress_chapterId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ChapterProgress_chapterId_key" ON public."ChapterProgress" USING btree ("chapterId");


--
-- Name: ChapterQualityCheck_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ChapterQualityCheck_chapterId_idx" ON public."ChapterQualityCheck" USING btree ("chapterId");


--
-- Name: ChapterQualityCheck_chapterId_type_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ChapterQualityCheck_chapterId_type_key" ON public."ChapterQualityCheck" USING btree ("chapterId", type);


--
-- Name: ChapterQualityCheck_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ChapterQualityCheck_status_idx" ON public."ChapterQualityCheck" USING btree (status);


--
-- Name: ChapterWritingGoal_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ChapterWritingGoal_chapterId_idx" ON public."ChapterWritingGoal" USING btree ("chapterId");


--
-- Name: ChapterWritingGoal_novelId_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ChapterWritingGoal_novelId_chapterId_idx" ON public."ChapterWritingGoal" USING btree ("novelId", "chapterId");


--
-- Name: Chapter_novelId_order_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Chapter_novelId_order_idx" ON public."Chapter" USING btree ("novelId", "order");


--
-- Name: Chapter_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Chapter_status_idx" ON public."Chapter" USING btree (status);


--
-- Name: CharacterExperience_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterExperience_chapterId_idx" ON public."CharacterExperience" USING btree ("chapterId");


--
-- Name: CharacterExperience_characterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterExperience_characterId_idx" ON public."CharacterExperience" USING btree ("characterId");


--
-- Name: CharacterRelation_characterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterRelation_characterId_idx" ON public."CharacterRelation" USING btree ("characterId");


--
-- Name: CharacterRelation_relationType_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterRelation_relationType_idx" ON public."CharacterRelation" USING btree ("relationType");


--
-- Name: CharacterRelation_targetId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterRelation_targetId_idx" ON public."CharacterRelation" USING btree ("targetId");


--
-- Name: CharacterStateChange_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterStateChange_chapterId_idx" ON public."CharacterStateChange" USING btree ("chapterId");


--
-- Name: CharacterStateChange_characterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CharacterStateChange_characterId_idx" ON public."CharacterStateChange" USING btree ("characterId");


--
-- Name: Character_currentStatus_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Character_currentStatus_idx" ON public."Character" USING btree ("currentStatus");


--
-- Name: Character_factionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Character_factionId_idx" ON public."Character" USING btree ("factionId");


--
-- Name: Character_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Character_novelId_idx" ON public."Character" USING btree ("novelId");


--
-- Name: CreditLedger_requestId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CreditLedger_requestId_idx" ON public."CreditLedger" USING btree ("requestId");


--
-- Name: CreditLedger_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CreditLedger_type_idx" ON public."CreditLedger" USING btree (type);


--
-- Name: CreditLedger_userId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CreditLedger_userId_createdAt_idx" ON public."CreditLedger" USING btree ("userId", "createdAt");


--
-- Name: CreditLedger_userId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "CreditLedger_userId_idx" ON public."CreditLedger" USING btree ("userId");


--
-- Name: Faction_baseId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Faction_baseId_idx" ON public."Faction" USING btree ("baseId");


--
-- Name: Faction_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Faction_novelId_idx" ON public."Faction" USING btree ("novelId");


--
-- Name: Foreshadowing_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Foreshadowing_novelId_idx" ON public."Foreshadowing" USING btree ("novelId");


--
-- Name: Foreshadowing_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Foreshadowing_status_idx" ON public."Foreshadowing" USING btree (status);


--
-- Name: Glossary_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Glossary_novelId_idx" ON public."Glossary" USING btree ("novelId");


--
-- Name: Item_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Item_novelId_idx" ON public."Item" USING btree ("novelId");


--
-- Name: Item_ownerId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Item_ownerId_idx" ON public."Item" USING btree ("ownerId");


--
-- Name: Location_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Location_novelId_idx" ON public."Location" USING btree ("novelId");


--
-- Name: Location_parentId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Location_parentId_idx" ON public."Location" USING btree ("parentId");


--
-- Name: Novel_userId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "Novel_userId_idx" ON public."Novel" USING btree ("userId");


--
-- Name: OutlineNode_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OutlineNode_novelId_idx" ON public."OutlineNode" USING btree ("novelId");


--
-- Name: OutlineNode_novelId_kind_chapterStartOrder_chapterEndOrder_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OutlineNode_novelId_kind_chapterStartOrder_chapterEndOrder_idx" ON public."OutlineNode" USING btree ("novelId", kind, "chapterStartOrder", "chapterEndOrder");


--
-- Name: OutlineNode_novelId_kind_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OutlineNode_novelId_kind_idx" ON public."OutlineNode" USING btree ("novelId", kind);


--
-- Name: OutlineNode_parentId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OutlineNode_parentId_idx" ON public."OutlineNode" USING btree ("parentId");


--
-- Name: OutlineNode_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "OutlineNode_status_idx" ON public."OutlineNode" USING btree (status);


--
-- Name: Outline_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "Outline_novelId_key" ON public."Outline" USING btree ("novelId");


--
-- Name: PlotProgress_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "PlotProgress_novelId_key" ON public."PlotProgress" USING btree ("novelId");


--
-- Name: RagChunk_documentId_chunkIndex_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "RagChunk_documentId_chunkIndex_key" ON public."RagChunk" USING btree ("documentId", "chunkIndex");


--
-- Name: RagChunk_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RagChunk_novelId_idx" ON public."RagChunk" USING btree ("novelId");


--
-- Name: RagDocument_novelId_sourceType_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "RagDocument_novelId_sourceType_idx" ON public."RagDocument" USING btree ("novelId", "sourceType");


--
-- Name: RagDocument_sourceType_sourceId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "RagDocument_sourceType_sourceId_key" ON public."RagDocument" USING btree ("sourceType", "sourceId");


--
-- Name: ReferenceMaterial_novelId_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReferenceMaterial_novelId_type_idx" ON public."ReferenceMaterial" USING btree ("novelId", type);


--
-- Name: ReviewArtifactEvaluation_artifactId_revision_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifactEvaluation_artifactId_revision_idx" ON public."ReviewArtifactEvaluation" USING btree ("artifactId", revision);


--
-- Name: ReviewArtifactEvaluation_evaluatorAgent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifactEvaluation_evaluatorAgent_idx" ON public."ReviewArtifactEvaluation" USING btree ("evaluatorAgent");


--
-- Name: ReviewArtifactRevision_artifactId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifactRevision_artifactId_idx" ON public."ReviewArtifactRevision" USING btree ("artifactId");


--
-- Name: ReviewArtifactRevision_artifactId_revision_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ReviewArtifactRevision_artifactId_revision_key" ON public."ReviewArtifactRevision" USING btree ("artifactId", revision);


--
-- Name: ReviewArtifact_artifactKey_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_artifactKey_idx" ON public."ReviewArtifact" USING btree ("artifactKey");


--
-- Name: ReviewArtifact_chapterId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_chapterId_status_idx" ON public."ReviewArtifact" USING btree ("chapterId", status);


--
-- Name: ReviewArtifact_id_videoAdaptationId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "ReviewArtifact_id_videoAdaptationId_key" ON public."ReviewArtifact" USING btree (id, "videoAdaptationId");


--
-- Name: ReviewArtifact_novelId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_novelId_status_idx" ON public."ReviewArtifact" USING btree ("novelId", status);


--
-- Name: ReviewArtifact_taskId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_taskId_idx" ON public."ReviewArtifact" USING btree ("taskId");


--
-- Name: ReviewArtifact_videoAdaptationId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_videoAdaptationId_status_idx" ON public."ReviewArtifact" USING btree ("videoAdaptationId", status);


--
-- Name: ReviewArtifact_videoSceneId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_videoSceneId_status_idx" ON public."ReviewArtifact" USING btree ("videoSceneId", status);


--
-- Name: ReviewArtifact_workflowRunId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "ReviewArtifact_workflowRunId_idx" ON public."ReviewArtifact" USING btree ("workflowRunId");


--
-- Name: SceneBeat_beatPlanId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "SceneBeat_beatPlanId_idx" ON public."SceneBeat" USING btree ("beatPlanId");


--
-- Name: StoryBackground_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "StoryBackground_novelId_key" ON public."StoryBackground" USING btree ("novelId");


--
-- Name: StylePortraitTask_styleId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "StylePortraitTask_styleId_idx" ON public."StylePortraitTask" USING btree ("styleId");


--
-- Name: StyleReference_styleId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "StyleReference_styleId_idx" ON public."StyleReference" USING btree ("styleId");


--
-- Name: TokenUsage_agentId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "TokenUsage_agentId_idx" ON public."TokenUsage" USING btree ("agentId");


--
-- Name: TokenUsage_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "TokenUsage_novelId_idx" ON public."TokenUsage" USING btree ("novelId");


--
-- Name: TokenUsage_requestId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "TokenUsage_requestId_key" ON public."TokenUsage" USING btree ("requestId");


--
-- Name: TokenUsage_runId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "TokenUsage_runId_createdAt_idx" ON public."TokenUsage" USING btree ("runId", "createdAt");


--
-- Name: TokenUsage_userId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "TokenUsage_userId_createdAt_idx" ON public."TokenUsage" USING btree ("userId", "createdAt");


--
-- Name: TokenUsage_userId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "TokenUsage_userId_idx" ON public."TokenUsage" USING btree ("userId");


--
-- Name: TokenUsage_userId_taskId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "TokenUsage_userId_taskId_createdAt_idx" ON public."TokenUsage" USING btree ("userId", "taskId", "createdAt");


--
-- Name: User_username_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "User_username_key" ON public."User" USING btree (username);


--
-- Name: VideoAdaptationDecisionCommand_adaptation_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoAdaptationDecisionCommand_adaptation_created_idx" ON public."VideoAdaptationDecisionCommand" USING btree ("adaptationId", "createdAt");


--
-- Name: VideoAdaptationDecisionCommand_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoAdaptationDecisionCommand_user_request_key" ON public."VideoAdaptationDecisionCommand" USING btree ("requestedByUserId", "clientRequestId");


--
-- Name: VideoAdaptationTask_adaptation_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoAdaptationTask_adaptation_created_idx" ON public."VideoAdaptationTask" USING btree ("adaptationId", "createdAt");


--
-- Name: VideoAdaptationTask_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoAdaptationTask_due_idx" ON public."VideoAdaptationTask" USING btree (status, "nextAttemptAt", "createdAt") WHERE (status = ANY (ARRAY['pending'::text, 'submitted'::text, 'processing'::text]));


--
-- Name: VideoAdaptationTask_id_adaptationId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoAdaptationTask_id_adaptationId_key" ON public."VideoAdaptationTask" USING btree (id, "adaptationId");


--
-- Name: VideoAdaptationTask_id_baseShotPlanVersionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoAdaptationTask_id_baseShotPlanVersionId_key" ON public."VideoAdaptationTask" USING btree (id, "baseShotPlanVersionId");


--
-- Name: VideoAdaptationTask_idempotencyKey_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoAdaptationTask_idempotencyKey_key" ON public."VideoAdaptationTask" USING btree ("idempotencyKey");


--
-- Name: VideoAdaptationTask_jobId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoAdaptationTask_jobId_key" ON public."VideoAdaptationTask" USING btree ("jobId");


--
-- Name: VideoAssetBinding_sceneId_priority_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoAssetBinding_sceneId_priority_idx" ON public."VideoAssetBinding" USING btree ("sceneId", priority, "createdAt");


--
-- Name: VideoAsset_projectId_modality_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoAsset_projectId_modality_idx" ON public."VideoAsset" USING btree ("projectId", modality, "createdAt");


--
-- Name: VideoChapterAdaptation_id_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoChapterAdaptation_id_novelId_key" ON public."VideoChapterAdaptation" USING btree (id, "novelId");


--
-- Name: VideoChapterAdaptation_id_projectId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoChapterAdaptation_id_projectId_key" ON public."VideoChapterAdaptation" USING btree (id, "projectId");


--
-- Name: VideoChapterAdaptation_project_chapter_source_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoChapterAdaptation_project_chapter_source_key" ON public."VideoChapterAdaptation" USING btree ("projectId", "chapterId", "sourceHash") WHERE (("chapterId" IS NOT NULL) AND ("lifecycleStatus" = 'active'::text));


--
-- Name: VideoChapterAdaptation_project_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoChapterAdaptation_project_created_idx" ON public."VideoChapterAdaptation" USING btree ("projectId", "createdAt");


--
-- Name: VideoCinematicScene_id_planVersionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoCinematicScene_id_planVersionId_key" ON public."VideoCinematicScene" USING btree (id, "planVersionId");


--
-- Name: VideoDramaticBeat_id_planVersionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoDramaticBeat_id_planVersionId_key" ON public."VideoDramaticBeat" USING btree (id, "planVersionId");


--
-- Name: VideoDramaticBeat_id_sceneId_planVersionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoDramaticBeat_id_sceneId_planVersionId_key" ON public."VideoDramaticBeat" USING btree (id, "sceneId", "planVersionId");


--
-- Name: VideoEpisodeEditClip_version_shot_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeEditClip_version_shot_key" ON public."VideoEpisodeEditClip" USING btree ("editVersionId", "shotId");


--
-- Name: VideoEpisodeEditVersion_episode_version_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeEditVersion_episode_version_key" ON public."VideoEpisodeEditVersion" USING btree ("episodePlanVersionId", "episodeNo", "versionNo");


--
-- Name: VideoEpisodeEditVersion_id_plan_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeEditVersion_id_plan_key" ON public."VideoEpisodeEditVersion" USING btree (id, "shotPlanVersionId");


--
-- Name: VideoEpisodeEditVersion_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeEditVersion_user_request_key" ON public."VideoEpisodeEditVersion" USING btree ("createdByUserId", "clientRequestId");


--
-- Name: VideoEpisodeExportTask_active_episode_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeExportTask_active_episode_key" ON public."VideoEpisodeExportTask" USING btree ("episodePlanVersionId", "episodeNo") WHERE (status = ANY (ARRAY['pending'::text, 'rendering'::text]));


--
-- Name: VideoEpisodeExportTask_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoEpisodeExportTask_due_idx" ON public."VideoEpisodeExportTask" USING btree ("nextAttemptAt", "createdAt") WHERE (status = ANY (ARRAY['pending'::text, 'rendering'::text]));


--
-- Name: VideoEpisodeExportTask_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeExportTask_user_request_key" ON public."VideoEpisodeExportTask" USING btree ("requestedByUserId", "clientRequestId");


--
-- Name: VideoEpisodeExport_assetId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeExport_assetId_key" ON public."VideoEpisodeExport" USING btree ("assetId");


--
-- Name: VideoEpisodeExport_episode_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoEpisodeExport_episode_created_idx" ON public."VideoEpisodeExport" USING btree ("episodePlanVersionId", "episodeNo", "createdAt");


--
-- Name: VideoEpisodeExport_episode_version_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeExport_episode_version_key" ON public."VideoEpisodeExport" USING btree ("episodePlanVersionId", "episodeNo", "versionNo");


--
-- Name: VideoEpisodeExport_taskId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeExport_taskId_key" ON public."VideoEpisodeExport" USING btree ("taskId");


--
-- Name: VideoEpisodeMixVersion_episode_version_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeMixVersion_episode_version_key" ON public."VideoEpisodeMixVersion" USING btree ("episodePlanVersionId", "episodeNo", "versionNo");


--
-- Name: VideoEpisodeMixVersion_id_plan_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeMixVersion_id_plan_key" ON public."VideoEpisodeMixVersion" USING btree (id, "shotPlanVersionId");


--
-- Name: VideoEpisodeMixVersion_id_project_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeMixVersion_id_project_key" ON public."VideoEpisodeMixVersion" USING btree (id, "projectId");


--
-- Name: VideoEpisodeMixVersion_id_project_plan_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeMixVersion_id_project_plan_key" ON public."VideoEpisodeMixVersion" USING btree (id, "projectId", "shotPlanVersionId");


--
-- Name: VideoEpisodeMixVersion_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodeMixVersion_user_request_key" ON public."VideoEpisodeMixVersion" USING btree ("createdByUserId", "clientRequestId");


--
-- Name: VideoEpisodePlanVersion_id_adaptationId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodePlanVersion_id_adaptationId_key" ON public."VideoEpisodePlanVersion" USING btree (id, "adaptationId");


--
-- Name: VideoEpisodePlanVersion_id_shotPlanVersionId_adaptationId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodePlanVersion_id_shotPlanVersionId_adaptationId_key" ON public."VideoEpisodePlanVersion" USING btree (id, "shotPlanVersionId", "adaptationId");


--
-- Name: VideoEpisodePlanVersion_id_shotPlanVersionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoEpisodePlanVersion_id_shotPlanVersionId_key" ON public."VideoEpisodePlanVersion" USING btree (id, "shotPlanVersionId");


--
-- Name: VideoGenerationTask_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoGenerationTask_due_idx" ON public."VideoGenerationTask" USING btree (status, "nextAttemptAt", "createdAt") WHERE (status = ANY (ARRAY['pending'::text, 'submitted'::text, 'processing'::text]));


--
-- Name: VideoGenerationTask_sceneId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoGenerationTask_sceneId_createdAt_idx" ON public."VideoGenerationTask" USING btree ("sceneId", "createdAt");


--
-- Name: VideoProject_novelId_updatedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoProject_novelId_updatedAt_idx" ON public."VideoProject" USING btree ("novelId", "updatedAt") WHERE ("deletedAt" IS NULL);


--
-- Name: VideoReviewDecisionCommand_artifact_revision_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoReviewDecisionCommand_artifact_revision_idx" ON public."VideoReviewDecisionCommand" USING btree ("artifactId", "expectedArtifactRevision", decision);


--
-- Name: VideoReviewDecisionCommand_scene_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoReviewDecisionCommand_scene_created_idx" ON public."VideoReviewDecisionCommand" USING btree ("sceneId", "createdAt");


--
-- Name: VideoReviewDecisionCommand_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoReviewDecisionCommand_user_request_key" ON public."VideoReviewDecisionCommand" USING btree ("requestedByUserId", "clientRequestId");


--
-- Name: VideoScene_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoScene_chapterId_idx" ON public."VideoScene" USING btree ("chapterId");


--
-- Name: VideoScene_projectId_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoScene_projectId_status_idx" ON public."VideoScene" USING btree ("projectId", status, ordinal);


--
-- Name: VideoShotKeyframeVersion_shot_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoShotKeyframeVersion_shot_created_idx" ON public."VideoShotKeyframeVersion" USING btree ("shotId", "createdAt");


--
-- Name: VideoShotKeyframeVersion_shot_role_version_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotKeyframeVersion_shot_role_version_key" ON public."VideoShotKeyframeVersion" USING btree ("shotId", role, "versionNo");


--
-- Name: VideoShotKeyframeVersion_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotKeyframeVersion_user_request_key" ON public."VideoShotKeyframeVersion" USING btree ("createdByUserId", "clientRequestId");


--
-- Name: VideoShotPlanVersion_id_adaptationId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotPlanVersion_id_adaptationId_key" ON public."VideoShotPlanVersion" USING btree (id, "adaptationId");


--
-- Name: VideoShotPromptVersion_id_shotId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotPromptVersion_id_shotId_key" ON public."VideoShotPromptVersion" USING btree (id, "shotId");


--
-- Name: VideoShotPromptVersion_id_shot_plan_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotPromptVersion_id_shot_plan_key" ON public."VideoShotPromptVersion" USING btree (id, "shotId", "shotPlanVersionId");


--
-- Name: VideoShotRenderTask_active_shot_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotRenderTask_active_shot_key" ON public."VideoShotRenderTask" USING btree ("shotId") WHERE (status = ANY (ARRAY['pending'::text, 'submitting'::text, 'queued'::text, 'running'::text, 'archiving'::text]));


--
-- Name: VideoShotRenderTask_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoShotRenderTask_due_idx" ON public."VideoShotRenderTask" USING btree ("nextAttemptAt", "createdAt") WHERE (status = ANY (ARRAY['pending'::text, 'queued'::text, 'running'::text, 'archiving'::text]));


--
-- Name: VideoShotRenderTask_id_scope_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotRenderTask_id_scope_key" ON public."VideoShotRenderTask" USING btree (id, "adaptationId", "projectId", "novelId", "shotId", "shotPlanVersionId", "promptVersionId");


--
-- Name: VideoShotRenderTask_provider_task_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotRenderTask_provider_task_key" ON public."VideoShotRenderTask" USING btree (provider, "providerTaskId") WHERE ("providerTaskId" IS NOT NULL);


--
-- Name: VideoShotRenderTask_shot_client_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotRenderTask_shot_client_request_key" ON public."VideoShotRenderTask" USING btree ("shotId", "clientRequestId");


--
-- Name: VideoShotRenderTask_shot_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoShotRenderTask_shot_created_idx" ON public."VideoShotRenderTask" USING btree ("shotId", "createdAt");


--
-- Name: VideoShotTakeDecisionCommand_shot_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoShotTakeDecisionCommand_shot_created_idx" ON public."VideoShotTakeDecisionCommand" USING btree ("shotId", "createdAt");


--
-- Name: VideoShotTakeDecisionCommand_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotTakeDecisionCommand_user_request_key" ON public."VideoShotTakeDecisionCommand" USING btree ("requestedByUserId", "clientRequestId");


--
-- Name: VideoShotTake_assetId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotTake_assetId_key" ON public."VideoShotTake" USING btree ("assetId");


--
-- Name: VideoShotTake_id_shot_adaptation_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotTake_id_shot_adaptation_key" ON public."VideoShotTake" USING btree (id, "shotId", "adaptationId");


--
-- Name: VideoShotTake_id_shot_plan_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotTake_id_shot_plan_key" ON public."VideoShotTake" USING btree (id, "shotId", "shotPlanVersionId");


--
-- Name: VideoShotTake_shot_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoShotTake_shot_created_idx" ON public."VideoShotTake" USING btree ("shotId", "createdAt");


--
-- Name: VideoShotTake_shot_take_no_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotTake_shot_take_no_key" ON public."VideoShotTake" USING btree ("shotId", "takeNo");


--
-- Name: VideoShotTake_taskId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotTake_taskId_key" ON public."VideoShotTake" USING btree ("taskId");


--
-- Name: VideoShotVisualReferenceSet_scope_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShotVisualReferenceSet_scope_key" ON public."VideoShotVisualReferenceSet" USING btree ("shotId", "planVersionId", "adaptationId", "projectId", "novelId");


--
-- Name: VideoShot_id_planVersionId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoShot_id_planVersionId_key" ON public."VideoShot" USING btree (id, "planVersionId");


--
-- Name: VideoTakeFrameExtraction_take_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoTakeFrameExtraction_take_created_idx" ON public."VideoTakeFrameExtraction" USING btree ("takeId", "createdAt");


--
-- Name: VideoTakeFrameExtraction_user_request_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoTakeFrameExtraction_user_request_key" ON public."VideoTakeFrameExtraction" USING btree ("requestedByUserId", "clientRequestId");


--
-- Name: VideoVisualCanonVersion_id_canonId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoVisualCanonVersion_id_canonId_key" ON public."VideoVisualCanonVersion" USING btree (id, "canonId");


--
-- Name: VideoVisualCanonVersion_id_project_novel_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoVisualCanonVersion_id_project_novel_key" ON public."VideoVisualCanonVersion" USING btree (id, "projectId", "novelId");


--
-- Name: VideoVisualCanon_id_project_novel_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoVisualCanon_id_project_novel_key" ON public."VideoVisualCanon" USING btree (id, "projectId", "novelId");


--
-- Name: VideoVisualCanon_project_setting_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "VideoVisualCanon_project_setting_idx" ON public."VideoVisualCanon" USING btree ("projectId", "settingKind", "settingId");


--
-- Name: VideoVisualCanon_slot_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "VideoVisualCanon_slot_key" ON public."VideoVisualCanon" USING btree ("projectId", "settingKind", "settingId", duty, "variantKey");


--
-- Name: WorkflowRun_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WorkflowRun_chapterId_idx" ON public."WorkflowRun" USING btree ("chapterId");


--
-- Name: WorkflowRun_kind_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WorkflowRun_kind_idx" ON public."WorkflowRun" USING btree (kind);


--
-- Name: WorkflowRun_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WorkflowRun_novelId_idx" ON public."WorkflowRun" USING btree ("novelId");


--
-- Name: WorkflowRun_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WorkflowRun_status_idx" ON public."WorkflowRun" USING btree (status);


--
-- Name: WorkflowRun_userId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WorkflowRun_userId_idx" ON public."WorkflowRun" USING btree ("userId");


--
-- Name: WorkflowStep_runId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WorkflowStep_runId_idx" ON public."WorkflowStep" USING btree ("runId");


--
-- Name: WorldSetting_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WorldSetting_novelId_key" ON public."WorldSetting" USING btree ("novelId");


--
-- Name: WritingBible_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingBible_novelId_key" ON public."WritingBible" USING btree ("novelId");


--
-- Name: WritingConfig_novelId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingConfig_novelId_key" ON public."WritingConfig" USING btree ("novelId");


--
-- Name: WritingEventOutbox_dedupeKey_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingEventOutbox_dedupeKey_key" ON public."WritingEventOutbox" USING btree ("dedupeKey");


--
-- Name: WritingEventOutbox_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingEventOutbox_due_idx" ON public."WritingEventOutbox" USING btree ("deliveryState", "nextAttemptAt", "createdAt") WHERE ("deliveryState" = ANY (ARRAY['pending'::text, 'delivering'::text]));


--
-- Name: WritingEventOutbox_publishedAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingEventOutbox_publishedAt_idx" ON public."WritingEventOutbox" USING btree ("publishedAt") WHERE ("publishedAt" IS NOT NULL);


--
-- Name: WritingEventOutbox_sourceEventId_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingEventOutbox_sourceEventId_key" ON public."WritingEventOutbox" USING btree ("sourceEventId");


--
-- Name: WritingEventOutbox_taskId_sourceSequence_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingEventOutbox_taskId_sourceSequence_key" ON public."WritingEventOutbox" USING btree ("taskId", "sourceSequence");


--
-- Name: WritingEventOutbox_task_sequence_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingEventOutbox_task_sequence_idx" ON public."WritingEventOutbox" USING btree ("taskId", "sourceSequence");


--
-- Name: WritingMessage_sessionId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingMessage_sessionId_createdAt_idx" ON public."WritingMessage" USING btree ("sessionId", "createdAt");


--
-- Name: WritingRunCommand_active_task_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingRunCommand_active_task_key" ON public."WritingRunCommand" USING btree ("taskId") WHERE (status = ANY (ARRAY['pending'::text, 'submitted'::text, 'processing'::text]));


--
-- Name: WritingRunCommand_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingRunCommand_due_idx" ON public."WritingRunCommand" USING btree (status, "nextAttemptAt");


--
-- Name: WritingRunCommand_idempotencyKey_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX "WritingRunCommand_idempotencyKey_key" ON public."WritingRunCommand" USING btree ("idempotencyKey");


--
-- Name: WritingSession_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingSession_chapterId_idx" ON public."WritingSession" USING btree ("chapterId");


--
-- Name: WritingSession_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingSession_novelId_idx" ON public."WritingSession" USING btree ("novelId");


--
-- Name: WritingStyle_userId_createdAt_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingStyle_userId_createdAt_idx" ON public."WritingStyle" USING btree ("userId", "createdAt");


--
-- Name: WritingTask_chapterId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingTask_chapterId_idx" ON public."WritingTask" USING btree ("chapterId");


--
-- Name: WritingTask_novelId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingTask_novelId_idx" ON public."WritingTask" USING btree ("novelId");


--
-- Name: WritingTask_writingSessionId_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "WritingTask_writingSessionId_idx" ON public."WritingTask" USING btree ("writingSessionId");


--
-- Name: _FactionTerritories_B_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "_FactionTerritories_B_index" ON public."_FactionTerritories" USING btree ("B");


--
-- Name: ChapterBeatPlan ChapterBeatPlan_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterBeatPlan"
    ADD CONSTRAINT "ChapterBeatPlan_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ChapterBeatPlan ChapterBeatPlan_goalId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterBeatPlan"
    ADD CONSTRAINT "ChapterBeatPlan_goalId_fkey" FOREIGN KEY ("goalId") REFERENCES public."ChapterWritingGoal"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: ChapterProgress ChapterProgress_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterProgress"
    ADD CONSTRAINT "ChapterProgress_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ChapterQualityCheck ChapterQualityCheck_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterQualityCheck"
    ADD CONSTRAINT "ChapterQualityCheck_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ChapterWritingGoal ChapterWritingGoal_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterWritingGoal"
    ADD CONSTRAINT "ChapterWritingGoal_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ChapterWritingGoal ChapterWritingGoal_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ChapterWritingGoal"
    ADD CONSTRAINT "ChapterWritingGoal_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Chapter Chapter_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Chapter"
    ADD CONSTRAINT "Chapter_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: CharacterExperience CharacterExperience_characterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterExperience"
    ADD CONSTRAINT "CharacterExperience_characterId_fkey" FOREIGN KEY ("characterId") REFERENCES public."Character"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: CharacterRelation CharacterRelation_characterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterRelation"
    ADD CONSTRAINT "CharacterRelation_characterId_fkey" FOREIGN KEY ("characterId") REFERENCES public."Character"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: CharacterRelation CharacterRelation_targetId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterRelation"
    ADD CONSTRAINT "CharacterRelation_targetId_fkey" FOREIGN KEY ("targetId") REFERENCES public."Character"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: CharacterStateChange CharacterStateChange_characterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CharacterStateChange"
    ADD CONSTRAINT "CharacterStateChange_characterId_fkey" FOREIGN KEY ("characterId") REFERENCES public."Character"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Character Character_factionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Character"
    ADD CONSTRAINT "Character_factionId_fkey" FOREIGN KEY ("factionId") REFERENCES public."Faction"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Character Character_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Character"
    ADD CONSTRAINT "Character_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: CreditLedger CreditLedger_userId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."CreditLedger"
    ADD CONSTRAINT "CreditLedger_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Faction Faction_baseId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Faction"
    ADD CONSTRAINT "Faction_baseId_fkey" FOREIGN KEY ("baseId") REFERENCES public."Location"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Faction Faction_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Faction"
    ADD CONSTRAINT "Faction_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Foreshadowing Foreshadowing_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Foreshadowing"
    ADD CONSTRAINT "Foreshadowing_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Glossary Glossary_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Glossary"
    ADD CONSTRAINT "Glossary_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Item Item_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Item"
    ADD CONSTRAINT "Item_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Item Item_ownerId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Item"
    ADD CONSTRAINT "Item_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES public."Character"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Location Location_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Location"
    ADD CONSTRAINT "Location_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: Location Location_parentId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Location"
    ADD CONSTRAINT "Location_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES public."Location"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Novel Novel_appliedStyleId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Novel"
    ADD CONSTRAINT "Novel_appliedStyleId_fkey" FOREIGN KEY ("appliedStyleId") REFERENCES public."WritingStyle"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Novel Novel_userId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Novel"
    ADD CONSTRAINT "Novel_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: OutlineNode OutlineNode_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OutlineNode"
    ADD CONSTRAINT "OutlineNode_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: OutlineNode OutlineNode_parentId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."OutlineNode"
    ADD CONSTRAINT "OutlineNode_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES public."OutlineNode"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: Outline Outline_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."Outline"
    ADD CONSTRAINT "Outline_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: PlotProgress PlotProgress_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."PlotProgress"
    ADD CONSTRAINT "PlotProgress_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: RagChunk RagChunk_documentId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RagChunk"
    ADD CONSTRAINT "RagChunk_documentId_fkey" FOREIGN KEY ("documentId") REFERENCES public."RagDocument"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: RagChunk RagChunk_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RagChunk"
    ADD CONSTRAINT "RagChunk_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: RagDocument RagDocument_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."RagDocument"
    ADD CONSTRAINT "RagDocument_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReferenceMaterial ReferenceMaterial_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReferenceMaterial"
    ADD CONSTRAINT "ReferenceMaterial_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifactEvaluation ReviewArtifactEvaluation_artifactId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifactEvaluation"
    ADD CONSTRAINT "ReviewArtifactEvaluation_artifactId_fkey" FOREIGN KEY ("artifactId") REFERENCES public."ReviewArtifact"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifactRevision ReviewArtifactRevision_artifactId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifactRevision"
    ADD CONSTRAINT "ReviewArtifactRevision_artifactId_fkey" FOREIGN KEY ("artifactId") REFERENCES public."ReviewArtifact"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_taskId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_taskId_fkey" FOREIGN KEY ("taskId") REFERENCES public."WritingTask"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: ReviewArtifact ReviewArtifact_videoAdaptationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_videoAdaptationId_fkey" FOREIGN KEY ("videoAdaptationId") REFERENCES public."VideoChapterAdaptation"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_videoSceneId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_videoSceneId_fkey" FOREIGN KEY ("videoSceneId") REFERENCES public."VideoScene"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_video_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_adaptation_novel_fkey" FOREIGN KEY ("videoAdaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_video_adaptation_task_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_adaptation_task_fkey" FOREIGN KEY ("videoAdaptationTaskId", "videoAdaptationId") REFERENCES public."VideoAdaptationTask"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_video_scene_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_scene_novel_fkey" FOREIGN KEY ("videoSceneId", "novelId") REFERENCES public."VideoScene"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: ReviewArtifact ReviewArtifact_workflowRunId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_workflowRunId_fkey" FOREIGN KEY ("workflowRunId") REFERENCES public."WorkflowRun"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: SceneBeat SceneBeat_beatPlanId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."SceneBeat"
    ADD CONSTRAINT "SceneBeat_beatPlanId_fkey" FOREIGN KEY ("beatPlanId") REFERENCES public."ChapterBeatPlan"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: StoryBackground StoryBackground_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."StoryBackground"
    ADD CONSTRAINT "StoryBackground_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: StylePortraitTask StylePortraitTask_styleId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."StylePortraitTask"
    ADD CONSTRAINT "StylePortraitTask_styleId_fkey" FOREIGN KEY ("styleId") REFERENCES public."WritingStyle"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: StyleReference StyleReference_styleId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."StyleReference"
    ADD CONSTRAINT "StyleReference_styleId_fkey" FOREIGN KEY ("styleId") REFERENCES public."WritingStyle"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: TokenUsage TokenUsage_userId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."TokenUsage"
    ADD CONSTRAINT "TokenUsage_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_artifact_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_artifact_adaptation_fkey" FOREIGN KEY ("artifactId", "adaptationId") REFERENCES public."ReviewArtifact"(id, "videoAdaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_novel_owner_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_novel_owner_fkey" FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES public."Novel"(id, "userId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_task_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_task_adaptation_fkey" FOREIGN KEY ("sourceTaskId", "adaptationId") REFERENCES public."VideoAdaptationTask"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationDecisionCommand VideoAdaptationDecisionCommand_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationDecisionCommand"
    ADD CONSTRAINT "VideoAdaptationDecisionCommand_user_fkey" FOREIGN KEY ("requestedByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationTask VideoAdaptationTask_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationTask"
    ADD CONSTRAINT "VideoAdaptationTask_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationTask VideoAdaptationTask_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationTask"
    ADD CONSTRAINT "VideoAdaptationTask_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAdaptationTask VideoAdaptationTask_base_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationTask"
    ADD CONSTRAINT "VideoAdaptationTask_base_plan_fkey" FOREIGN KEY ("baseShotPlanVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoAdaptationTask VideoAdaptationTask_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAdaptationTask"
    ADD CONSTRAINT "VideoAdaptationTask_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAssetBinding VideoAssetBinding_assetId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES public."VideoAsset"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAssetBinding VideoAssetBinding_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAssetBinding VideoAssetBinding_sceneId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_sceneId_fkey" FOREIGN KEY ("sceneId") REFERENCES public."VideoScene"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAssetBinding VideoAssetBinding_scene_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_scene_project_fkey" FOREIGN KEY ("sceneId", "projectId") REFERENCES public."VideoScene"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoAsset VideoAsset_projectId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoAsset"
    ADD CONSTRAINT "VideoAsset_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES public."VideoProject"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoChapterAdaptationHead VideoChapterAdaptationHead_adaptationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_adaptationId_fkey" FOREIGN KEY ("adaptationId") REFERENCES public."VideoChapterAdaptation"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoChapterAdaptationHead VideoChapterAdaptationHead_current_episode_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_current_episode_fkey" FOREIGN KEY ("currentEpisodePlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoChapterAdaptationHead VideoChapterAdaptationHead_current_episode_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_current_episode_plan_fkey" FOREIGN KEY ("currentEpisodePlanVersionId", "currentShotPlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId", "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoChapterAdaptationHead VideoChapterAdaptationHead_current_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_current_plan_fkey" FOREIGN KEY ("currentShotPlanVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoChapterAdaptation VideoChapterAdaptation_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptation"
    ADD CONSTRAINT "VideoChapterAdaptation_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: VideoChapterAdaptation VideoChapterAdaptation_chapter_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptation"
    ADD CONSTRAINT "VideoChapterAdaptation_chapter_novel_fkey" FOREIGN KEY ("chapterId", "novelId") REFERENCES public."Chapter"(id, "novelId") ON UPDATE CASCADE;


--
-- Name: VideoChapterAdaptation VideoChapterAdaptation_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoChapterAdaptation"
    ADD CONSTRAINT "VideoChapterAdaptation_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoCinematicScene VideoCinematicScene_plan_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoCinematicScene"
    ADD CONSTRAINT "VideoCinematicScene_plan_adaptation_fkey" FOREIGN KEY ("planVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoDramaticBeatSourceAnchor VideoDramaticBeatSourceAnchor_beat_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoDramaticBeatSourceAnchor"
    ADD CONSTRAINT "VideoDramaticBeatSourceAnchor_beat_plan_fkey" FOREIGN KEY ("beatId", "planVersionId") REFERENCES public."VideoDramaticBeat"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoDramaticBeat VideoDramaticBeat_scene_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoDramaticBeat"
    ADD CONSTRAINT "VideoDramaticBeat_scene_plan_fkey" FOREIGN KEY ("sceneId", "planVersionId") REFERENCES public."VideoCinematicScene"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeAudioClip VideoEpisodeAudioClip_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeAudioClip"
    ADD CONSTRAINT "VideoEpisodeAudioClip_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeAudioClip VideoEpisodeAudioClip_mix_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeAudioClip"
    ADD CONSTRAINT "VideoEpisodeAudioClip_mix_project_fkey" FOREIGN KEY ("mixVersionId", "projectId", "shotPlanVersionId") REFERENCES public."VideoEpisodeMixVersion"(id, "projectId", "shotPlanVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeAudioClip VideoEpisodeAudioClip_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeAudioClip"
    ADD CONSTRAINT "VideoEpisodeAudioClip_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeBoundary VideoEpisodeBoundary_episode_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeBoundary"
    ADD CONSTRAINT "VideoEpisodeBoundary_episode_shot_plan_fkey" FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeBoundary VideoEpisodeBoundary_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeBoundary"
    ADD CONSTRAINT "VideoEpisodeBoundary_shot_plan_fkey" FOREIGN KEY ("afterShotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeEditClip VideoEpisodeEditClip_edit_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditClip"
    ADD CONSTRAINT "VideoEpisodeEditClip_edit_plan_fkey" FOREIGN KEY ("editVersionId", "shotPlanVersionId") REFERENCES public."VideoEpisodeEditVersion"(id, "shotPlanVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeEditClip VideoEpisodeEditClip_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditClip"
    ADD CONSTRAINT "VideoEpisodeEditClip_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeEditClip VideoEpisodeEditClip_take_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditClip"
    ADD CONSTRAINT "VideoEpisodeEditClip_take_scope_fkey" FOREIGN KEY ("takeId", "shotId", "shotPlanVersionId") REFERENCES public."VideoShotTake"(id, "shotId", "shotPlanVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeEditHead VideoEpisodeEditHead_current_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditHead"
    ADD CONSTRAINT "VideoEpisodeEditHead_current_version_fkey" FOREIGN KEY ("currentVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeEditVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeEditHead VideoEpisodeEditHead_episode_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditHead"
    ADD CONSTRAINT "VideoEpisodeEditHead_episode_plan_fkey" FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId", "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_based_on_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_based_on_fkey" FOREIGN KEY ("basedOnVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeEditVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_episode_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_episode_plan_fkey" FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId", "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeEditVersion VideoEpisodeEditVersion_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeEditVersion"
    ADD CONSTRAINT "VideoEpisodeEditVersion_user_fkey" FOREIGN KEY ("createdByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_edit_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_edit_version_fkey" FOREIGN KEY ("editVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeEditVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_episode_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_episode_plan_fkey" FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId", "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_mix_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_mix_version_fkey" FOREIGN KEY ("mixVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeMixVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_novel_owner_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_novel_owner_fkey" FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES public."Novel"(id, "userId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_retry_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_retry_scope_fkey" FOREIGN KEY ("retryOfTaskId", "adaptationId", "episodeNo") REFERENCES public."VideoEpisodeExportTask"(id, "adaptationId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExportTask VideoEpisodeExportTask_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExportTask"
    ADD CONSTRAINT "VideoEpisodeExportTask_user_fkey" FOREIGN KEY ("requestedByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExport VideoEpisodeExport_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExport"
    ADD CONSTRAINT "VideoEpisodeExport_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExport VideoEpisodeExport_edit_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExport"
    ADD CONSTRAINT "VideoEpisodeExport_edit_version_fkey" FOREIGN KEY ("editVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeEditVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExport VideoEpisodeExport_mix_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExport"
    ADD CONSTRAINT "VideoEpisodeExport_mix_version_fkey" FOREIGN KEY ("mixVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeMixVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeExport VideoEpisodeExport_task_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeExport"
    ADD CONSTRAINT "VideoEpisodeExport_task_scope_fkey" FOREIGN KEY ("taskId", "adaptationId", "episodeNo") REFERENCES public."VideoEpisodeExportTask"(id, "adaptationId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeMixHead VideoEpisodeMixHead_current_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixHead"
    ADD CONSTRAINT "VideoEpisodeMixHead_current_version_fkey" FOREIGN KEY ("currentVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeMixVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeMixHead VideoEpisodeMixHead_episode_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixHead"
    ADD CONSTRAINT "VideoEpisodeMixHead_episode_plan_fkey" FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId", "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_based_on_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_based_on_fkey" FOREIGN KEY ("basedOnVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeMixVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_edit_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_edit_version_fkey" FOREIGN KEY ("editVersionId", "episodePlanVersionId", "episodeNo") REFERENCES public."VideoEpisodeEditVersion"(id, "episodePlanVersionId", "episodeNo") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_episode_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_episode_plan_fkey" FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "shotPlanVersionId", "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeMixVersion VideoEpisodeMixVersion_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeMixVersion"
    ADD CONSTRAINT "VideoEpisodeMixVersion_user_fkey" FOREIGN KEY ("createdByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodePlanVersion VideoEpisodePlanVersion_based_on_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodePlanVersion"
    ADD CONSTRAINT "VideoEpisodePlanVersion_based_on_fkey" FOREIGN KEY ("basedOnVersionId", "adaptationId") REFERENCES public."VideoEpisodePlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodePlanVersion VideoEpisodePlanVersion_createdByUserId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodePlanVersion"
    ADD CONSTRAINT "VideoEpisodePlanVersion_createdByUserId_fkey" FOREIGN KEY ("createdByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoEpisodePlanVersion VideoEpisodePlanVersion_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodePlanVersion"
    ADD CONSTRAINT "VideoEpisodePlanVersion_shot_plan_fkey" FOREIGN KEY ("shotPlanVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeSubtitleCue VideoEpisodeSubtitleCue_mix_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeSubtitleCue"
    ADD CONSTRAINT "VideoEpisodeSubtitleCue_mix_plan_fkey" FOREIGN KEY ("mixVersionId", "shotPlanVersionId") REFERENCES public."VideoEpisodeMixVersion"(id, "shotPlanVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoEpisodeSubtitleCue VideoEpisodeSubtitleCue_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoEpisodeSubtitleCue"
    ADD CONSTRAINT "VideoEpisodeSubtitleCue_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoGenerationTask VideoGenerationTask_projectId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES public."VideoProject"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoGenerationTask VideoGenerationTask_sceneId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_sceneId_fkey" FOREIGN KEY ("sceneId") REFERENCES public."VideoScene"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoGenerationTask VideoGenerationTask_scene_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_scene_project_fkey" FOREIGN KEY ("sceneId", "projectId") REFERENCES public."VideoScene"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoProject VideoProject_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoProject"
    ADD CONSTRAINT "VideoProject_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_artifactId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_artifactId_fkey" FOREIGN KEY ("artifactId") REFERENCES public."ReviewArtifact"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_artifact_scene_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_artifact_scene_fkey" FOREIGN KEY ("artifactId", "sceneId") REFERENCES public."ReviewArtifact"(id, "videoSceneId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_novel_owner_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_novel_owner_fkey" FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES public."Novel"(id, "userId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_requestedByUserId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_requestedByUserId_fkey" FOREIGN KEY ("requestedByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_sceneId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_sceneId_fkey" FOREIGN KEY ("sceneId") REFERENCES public."VideoScene"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_scene_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_scene_project_fkey" FOREIGN KEY ("sceneId", "projectId") REFERENCES public."VideoScene"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_sourceTaskId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_sourceTaskId_fkey" FOREIGN KEY ("sourceTaskId") REFERENCES public."VideoGenerationTask"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoReviewDecisionCommand VideoReviewDecisionCommand_task_scene_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_task_scene_project_fkey" FOREIGN KEY ("sourceTaskId", "sceneId", "projectId") REFERENCES public."VideoGenerationTask"(id, "sceneId", "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoScene VideoScene_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: VideoScene VideoScene_chapter_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_chapter_novel_fkey" FOREIGN KEY ("chapterId", "novelId") REFERENCES public."Chapter"(id, "novelId") ON UPDATE CASCADE;


--
-- Name: VideoScene VideoScene_projectId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES public."VideoProject"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoScene VideoScene_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoScene"
    ADD CONSTRAINT "VideoScene_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeHead VideoShotKeyframeHead_current_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeHead"
    ADD CONSTRAINT "VideoShotKeyframeHead_current_version_fkey" FOREIGN KEY ("currentVersionId", "shotId", role) REFERENCES public."VideoShotKeyframeVersion"(id, "shotId", role) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotKeyframeHead VideoShotKeyframeHead_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeHead"
    ADD CONSTRAINT "VideoShotKeyframeHead_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_based_on_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_based_on_fkey" FOREIGN KEY ("basedOnVersionId", "shotId", role) REFERENCES public."VideoShotKeyframeVersion"(id, "shotId", role) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_extraction_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_extraction_fkey" FOREIGN KEY ("assetId", "sourceTakeId", "sourceTimeMs") REFERENCES public."VideoTakeFrameExtraction"("assetId", "takeId", "timestampMs") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_plan_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_plan_adaptation_fkey" FOREIGN KEY ("shotPlanVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_source_take_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_source_take_fkey" FOREIGN KEY ("sourceTakeId", "shotId", "adaptationId") REFERENCES public."VideoShotTake"(id, "shotId", "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotKeyframeVersion VideoShotKeyframeVersion_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotKeyframeVersion"
    ADD CONSTRAINT "VideoShotKeyframeVersion_user_fkey" FOREIGN KEY ("createdByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_adaptationId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_adaptationId_fkey" FOREIGN KEY ("adaptationId") REFERENCES public."VideoChapterAdaptation"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_based_on_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_based_on_fkey" FOREIGN KEY ("basedOnVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_createdByUserId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_createdByUserId_fkey" FOREIGN KEY ("createdByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_review_artifact_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_review_artifact_fkey" FOREIGN KEY ("reviewArtifactId", "adaptationId") REFERENCES public."ReviewArtifact"(id, "videoAdaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPlanVersion VideoShotPlanVersion_source_task_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_source_task_fkey" FOREIGN KEY ("sourceTaskId", "adaptationId") REFERENCES public."VideoAdaptationTask"(id, "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptHead VideoShotPromptHead_current_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptHead"
    ADD CONSTRAINT "VideoShotPromptHead_current_version_fkey" FOREIGN KEY ("currentVersionId", "shotId") REFERENCES public."VideoShotPromptVersion"(id, "shotId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptHead VideoShotPromptHead_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptHead"
    ADD CONSTRAINT "VideoShotPromptHead_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_based_on_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_based_on_fkey" FOREIGN KEY ("basedOnVersionId", "shotId") REFERENCES public."VideoShotPromptVersion"(id, "shotId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_createdByUserId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_createdByUserId_fkey" FOREIGN KEY ("createdByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_sourceTaskId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_sourceTaskId_fkey" FOREIGN KEY ("sourceTaskId") REFERENCES public."VideoAdaptationTask"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptVersion VideoShotPromptVersion_source_task_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_source_task_plan_fkey" FOREIGN KEY ("sourceTaskId", "shotPlanVersionId") REFERENCES public."VideoAdaptationTask"(id, "baseShotPlanVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_canon_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_canon_scope_fkey" FOREIGN KEY ("canonVersionId", "projectId", "novelId") REFERENCES public."VideoVisualCanonVersion"(id, "projectId", "novelId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_plan_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_plan_adaptation_fkey" FOREIGN KEY ("shotPlanVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotPromptVisualReference VideoShotPromptVisualReference_prompt_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotPromptVisualReference"
    ADD CONSTRAINT "VideoShotPromptVisualReference_prompt_scope_fkey" FOREIGN KEY ("promptVersionId", "shotId", "shotPlanVersionId") REFERENCES public."VideoShotPromptVersion"(id, "shotId", "shotPlanVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_plan_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_plan_adaptation_fkey" FOREIGN KEY ("shotPlanVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_prompt_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_prompt_scope_fkey" FOREIGN KEY ("promptVersionId", "shotId", "shotPlanVersionId") REFERENCES public."VideoShotPromptVersion"(id, "shotId", "shotPlanVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_retry_shot_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_retry_shot_fkey" FOREIGN KEY ("retryOfTaskId", "shotId") REFERENCES public."VideoShotRenderTask"(id, "shotId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotRenderTask VideoShotRenderTask_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotRenderTask"
    ADD CONSTRAINT "VideoShotRenderTask_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotSourceAnchor VideoShotSourceAnchor_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotSourceAnchor"
    ADD CONSTRAINT "VideoShotSourceAnchor_shot_plan_fkey" FOREIGN KEY ("shotId", "planVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotTakeDecisionCommand VideoShotTakeDecisionCommand_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeDecisionCommand"
    ADD CONSTRAINT "VideoShotTakeDecisionCommand_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotTakeDecisionCommand VideoShotTakeDecisionCommand_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeDecisionCommand"
    ADD CONSTRAINT "VideoShotTakeDecisionCommand_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotTakeDecisionCommand VideoShotTakeDecisionCommand_novel_owner_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeDecisionCommand"
    ADD CONSTRAINT "VideoShotTakeDecisionCommand_novel_owner_fkey" FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES public."Novel"(id, "userId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotTakeDecisionCommand VideoShotTakeDecisionCommand_take_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeDecisionCommand"
    ADD CONSTRAINT "VideoShotTakeDecisionCommand_take_scope_fkey" FOREIGN KEY ("takeId", "shotId", "adaptationId") REFERENCES public."VideoShotTake"(id, "shotId", "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotTakeDecisionCommand VideoShotTakeDecisionCommand_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeDecisionCommand"
    ADD CONSTRAINT "VideoShotTakeDecisionCommand_user_fkey" FOREIGN KEY ("requestedByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotTakeHead VideoShotTakeHead_current_take_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeHead"
    ADD CONSTRAINT "VideoShotTakeHead_current_take_fkey" FOREIGN KEY ("currentTakeId", "shotId", "shotPlanVersionId") REFERENCES public."VideoShotTake"(id, "shotId", "shotPlanVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotTakeHead VideoShotTakeHead_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTakeHead"
    ADD CONSTRAINT "VideoShotTakeHead_shot_plan_fkey" FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotTake VideoShotTake_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTake"
    ADD CONSTRAINT "VideoShotTake_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotTake VideoShotTake_task_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotTake"
    ADD CONSTRAINT "VideoShotTake_task_scope_fkey" FOREIGN KEY ("taskId", "adaptationId", "projectId", "novelId", "shotId", "shotPlanVersionId", "promptVersionId") REFERENCES public."VideoShotRenderTask"(id, "adaptationId", "projectId", "novelId", "shotId", "shotPlanVersionId", "promptVersionId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotVisualReferenceBinding VideoShotVisualReferenceBinding_canon_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceBinding"
    ADD CONSTRAINT "VideoShotVisualReferenceBinding_canon_scope_fkey" FOREIGN KEY ("canonVersionId", "projectId", "novelId") REFERENCES public."VideoVisualCanonVersion"(id, "projectId", "novelId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoShotVisualReferenceBinding VideoShotVisualReferenceBinding_set_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceBinding"
    ADD CONSTRAINT "VideoShotVisualReferenceBinding_set_scope_fkey" FOREIGN KEY ("shotId", "planVersionId", "adaptationId", "projectId", "novelId") REFERENCES public."VideoShotVisualReferenceSet"("shotId", "planVersionId", "adaptationId", "projectId", "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotVisualReferenceSet VideoShotVisualReferenceSet_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceSet"
    ADD CONSTRAINT "VideoShotVisualReferenceSet_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotVisualReferenceSet VideoShotVisualReferenceSet_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceSet"
    ADD CONSTRAINT "VideoShotVisualReferenceSet_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotVisualReferenceSet VideoShotVisualReferenceSet_plan_adaptation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceSet"
    ADD CONSTRAINT "VideoShotVisualReferenceSet_plan_adaptation_fkey" FOREIGN KEY ("planVersionId", "adaptationId") REFERENCES public."VideoShotPlanVersion"(id, "adaptationId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotVisualReferenceSet VideoShotVisualReferenceSet_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceSet"
    ADD CONSTRAINT "VideoShotVisualReferenceSet_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShotVisualReferenceSet VideoShotVisualReferenceSet_shot_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShotVisualReferenceSet"
    ADD CONSTRAINT "VideoShotVisualReferenceSet_shot_plan_fkey" FOREIGN KEY ("shotId", "planVersionId") REFERENCES public."VideoShot"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShot VideoShot_beat_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShot"
    ADD CONSTRAINT "VideoShot_beat_plan_fkey" FOREIGN KEY ("beatId", "planVersionId") REFERENCES public."VideoDramaticBeat"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShot VideoShot_beat_scene_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShot"
    ADD CONSTRAINT "VideoShot_beat_scene_plan_fkey" FOREIGN KEY ("beatId", "sceneId", "planVersionId") REFERENCES public."VideoDramaticBeat"(id, "sceneId", "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoShot VideoShot_scene_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoShot"
    ADD CONSTRAINT "VideoShot_scene_plan_fkey" FOREIGN KEY ("sceneId", "planVersionId") REFERENCES public."VideoCinematicScene"(id, "planVersionId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_adaptation_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_adaptation_novel_fkey" FOREIGN KEY ("adaptationId", "novelId") REFERENCES public."VideoChapterAdaptation"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_adaptation_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_adaptation_project_fkey" FOREIGN KEY ("adaptationId", "projectId") REFERENCES public."VideoChapterAdaptation"(id, "projectId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_novel_owner_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_novel_owner_fkey" FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES public."Novel"(id, "userId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_take_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_take_scope_fkey" FOREIGN KEY ("takeId", "shotId", "adaptationId") REFERENCES public."VideoShotTake"(id, "shotId", "adaptationId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoTakeFrameExtraction VideoTakeFrameExtraction_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoTakeFrameExtraction"
    ADD CONSTRAINT "VideoTakeFrameExtraction_user_fkey" FOREIGN KEY ("requestedByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoVisualCanonVersion VideoVisualCanonVersion_asset_project_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanonVersion"
    ADD CONSTRAINT "VideoVisualCanonVersion_asset_project_fkey" FOREIGN KEY ("assetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoVisualCanonVersion VideoVisualCanonVersion_canon_scope_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanonVersion"
    ADD CONSTRAINT "VideoVisualCanonVersion_canon_scope_fkey" FOREIGN KEY ("canonId", "projectId", "novelId") REFERENCES public."VideoVisualCanon"(id, "projectId", "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: VideoVisualCanonVersion VideoVisualCanonVersion_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanonVersion"
    ADD CONSTRAINT "VideoVisualCanonVersion_user_fkey" FOREIGN KEY ("approvedByUserId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoVisualCanon VideoVisualCanon_candidate_asset_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanon"
    ADD CONSTRAINT "VideoVisualCanon_candidate_asset_fkey" FOREIGN KEY ("candidateAssetId", "projectId") REFERENCES public."VideoAsset"(id, "projectId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoVisualCanon VideoVisualCanon_current_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanon"
    ADD CONSTRAINT "VideoVisualCanon_current_version_fkey" FOREIGN KEY ("currentVersionId", id) REFERENCES public."VideoVisualCanonVersion"(id, "canonId") ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: VideoVisualCanon VideoVisualCanon_project_novel_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."VideoVisualCanon"
    ADD CONSTRAINT "VideoVisualCanon_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES public."VideoProject"(id, "novelId") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WorkflowRun WorkflowRun_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WorkflowRun"
    ADD CONSTRAINT "WorkflowRun_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WorkflowStep WorkflowStep_runId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WorkflowStep"
    ADD CONSTRAINT "WorkflowStep_runId_fkey" FOREIGN KEY ("runId") REFERENCES public."WorkflowRun"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WorldSetting WorldSetting_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WorldSetting"
    ADD CONSTRAINT "WorldSetting_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingBible WritingBible_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingBible"
    ADD CONSTRAINT "WritingBible_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingConfig WritingConfig_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingConfig"
    ADD CONSTRAINT "WritingConfig_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingEventOutbox WritingEventOutbox_commandId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingEventOutbox"
    ADD CONSTRAINT "WritingEventOutbox_commandId_fkey" FOREIGN KEY ("commandId") REFERENCES public."WritingRunCommand"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: WritingEventOutbox WritingEventOutbox_taskId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingEventOutbox"
    ADD CONSTRAINT "WritingEventOutbox_taskId_fkey" FOREIGN KEY ("taskId") REFERENCES public."WritingTask"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingMessage WritingMessage_sessionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingMessage"
    ADD CONSTRAINT "WritingMessage_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES public."WritingSession"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingRunCommand WritingRunCommand_taskId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingRunCommand"
    ADD CONSTRAINT "WritingRunCommand_taskId_fkey" FOREIGN KEY ("taskId") REFERENCES public."WritingTask"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingSession WritingSession_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingSession"
    ADD CONSTRAINT "WritingSession_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingSession WritingSession_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingSession"
    ADD CONSTRAINT "WritingSession_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingStyle WritingStyle_userId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingStyle"
    ADD CONSTRAINT "WritingStyle_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."User"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingTask WritingTask_chapterId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingTask"
    ADD CONSTRAINT "WritingTask_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES public."Chapter"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingTask WritingTask_novelId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingTask"
    ADD CONSTRAINT "WritingTask_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES public."Novel"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: WritingTask WritingTask_writingSessionId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."WritingTask"
    ADD CONSTRAINT "WritingTask_writingSessionId_fkey" FOREIGN KEY ("writingSessionId") REFERENCES public."WritingSession"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: _FactionTerritories _FactionTerritories_A_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."_FactionTerritories"
    ADD CONSTRAINT "_FactionTerritories_A_fkey" FOREIGN KEY ("A") REFERENCES public."Faction"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: _FactionTerritories _FactionTerritories_B_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."_FactionTerritories"
    ADD CONSTRAINT "_FactionTerritories_B_fkey" FOREIGN KEY ("B") REFERENCES public."Location"(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--
