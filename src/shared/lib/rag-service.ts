import { createHash, randomUUID } from "node:crypto";

import { prisma } from "@/shared/db/prisma";
import { getRagEmbeddingConfig } from "@/shared/env";

const REFERENCE_SOURCE_TYPE = "reference_material" as const;
const MAX_CHUNK_CHARS = 1800;
const EMBEDDING_BATCH_SIZE = 10;

export type RagSearchResult = {
  title: string;
  sourceId: string;
  chunkIndex: number;
  score: number;
  text: string;
};

export function hashRagContent(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

export function chunkRagText(content: string, maxChars = MAX_CHUNK_CHARS): string[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const chunks: string[] = [];
  let current = "";
  const paragraphs = normalized.split(/\n{2,}/);

  function pushCurrent() {
    if (!current) return;
    chunks.push(current);
    current = "";
  }

  for (const paragraph of paragraphs) {
    const text = paragraph.trim();
    if (!text) continue;

    if (text.length > maxChars) {
      pushCurrent();
      for (let index = 0; index < text.length; index += maxChars) {
        chunks.push(text.slice(index, index + maxChars));
      }
      continue;
    }

    const next = current ? `${current}\n\n${text}` : text;
    if (next.length > maxChars) {
      pushCurrent();
      current = text;
    } else {
      current = next;
    }
  }

  pushCurrent();
  return chunks;
}

export async function upsertReferenceMaterialRagIndex(referenceMaterialId: string): Promise<void> {
  const reference = await prisma.referenceMaterial.findUnique({
    where: { id: referenceMaterialId },
    select: { id: true, novelId: true, title: true, content: true },
  });
  if (!reference) throw new Error(`参考资料不存在: ${referenceMaterialId}`);

  const content = reference.content.trim();
  const contentHash = hashRagContent(content);
  const config = getRagEmbeddingConfig();
  const document = await prisma.ragDocument.upsert({
    where: {
      sourceType_sourceId: {
        sourceType: REFERENCE_SOURCE_TYPE,
        sourceId: reference.id,
      },
    },
    update: {
      novelId: reference.novelId,
      title: reference.title,
      contentHash,
    },
    create: {
      novelId: reference.novelId,
      sourceType: REFERENCE_SOURCE_TYPE,
      sourceId: reference.id,
      title: reference.title,
      contentHash,
      status: "disabled",
      errorMessage: "RAG embedding 未配置",
    },
  });

  if (!config.enabled) {
    await prisma.ragDocument.update({
      where: { id: document.id },
      data: {
        status: "disabled",
        errorMessage: "RAG embedding 未配置",
        contentHash,
      },
    });
    return;
  }

  const chunks = chunkRagText(content);
  if (chunks.length === 0) {
    await prisma.$transaction([
      prisma.ragChunk.deleteMany({ where: { documentId: document.id } }),
      prisma.ragDocument.update({
        where: { id: document.id },
        data: { status: "ready", errorMessage: null, contentHash },
      }),
    ]);
    return;
  }

  try {
    const embeddings = await embedTexts(chunks, config);
    await prisma.$transaction(async (tx) => {
      await tx.ragDocument.update({
        where: { id: document.id },
        data: { status: "ready", errorMessage: null, contentHash, title: reference.title },
      });
      await tx.ragChunk.deleteMany({ where: { documentId: document.id } });

      for (let index = 0; index < chunks.length; index++) {
        const embedding = embeddings[index];
        await tx.$executeRaw`
          INSERT INTO "RagChunk" (
            "id", "documentId", "novelId", "chunkIndex", "text",
            "charCount", "embeddingDimension", "embedding", "createdAt"
          )
          VALUES (
            ${randomUUID()}, ${document.id}, ${reference.novelId}, ${index}, ${chunks[index]},
            ${chunks[index].length}, ${embedding.length}, ${toVectorLiteral(embedding)}::vector, NOW()
          )
        `;
      }
    });
  } catch (error) {
    await prisma.ragDocument.update({
      where: { id: document.id },
      data: {
        status: "failed",
        errorMessage: error instanceof Error ? error.message : "RAG 索引失败",
        contentHash,
      },
    });
  }
}

export async function semanticSearchReferenceChunks(input: {
  novelId: string;
  query: string;
  topK?: number;
}): Promise<{ enabled: boolean; results: RagSearchResult[]; error?: string }> {
  const config = getRagEmbeddingConfig();
  if (!config.enabled) {
    return { enabled: false, results: [], error: "RAG embedding 未配置，参考资料语义召回未启用。" };
  }

  const query = input.query.trim();
  if (!query) return { enabled: true, results: [] };

  const topK = input.topK ?? 5;
  const [embedding] = await embedTexts([query], config);
  const vector = toVectorLiteral(embedding);
  const rows = await prisma.$queryRaw<Array<{
    title: string;
    sourceId: string;
    chunkIndex: number;
    text: string;
    score: number;
  }>>`
    SELECT
      d."title",
      d."sourceId",
      c."chunkIndex",
      c."text",
      1 - (c."embedding" <=> ${vector}::vector) AS "score"
    FROM "RagChunk" c
    INNER JOIN "RagDocument" d ON d."id" = c."documentId"
    WHERE c."novelId" = ${input.novelId}
      AND d."sourceType" = 'reference_material'
      AND d."status" = 'ready'
      AND c."embeddingDimension" = ${embedding.length}
    ORDER BY c."embedding" <=> ${vector}::vector
    LIMIT ${topK}
  `;

  return {
    enabled: true,
    results: rows.map((row) => ({
      title: row.title,
      sourceId: row.sourceId,
      chunkIndex: row.chunkIndex,
      score: Number(row.score),
      text: row.text,
    })),
  };
}

async function embedTexts(
  texts: string[],
  config: { apiKey: string; baseUrl: string; model: string }
): Promise<number[][]> {
  const embeddings: number[][] = [];
  for (let index = 0; index < texts.length; index += EMBEDDING_BATCH_SIZE) {
    const batch = texts.slice(index, index + EMBEDDING_BATCH_SIZE);
    embeddings.push(...await requestEmbeddingBatch(batch, config));
  }
  if (embeddings.length !== texts.length) {
    throw new Error("embedding 返回数量与输入数量不一致");
  }
  return embeddings;
}

async function requestEmbeddingBatch(
  texts: string[],
  config: { apiKey: string; baseUrl: string; model: string }
): Promise<number[][]> {
  const response = await fetch(getEmbeddingEndpoint(config.baseUrl), {
    method: "POST",
    headers: {
      "authorization": `Bearer ${config.apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: config.model,
      input: texts,
      encoding_format: "float",
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`embedding 调用失败: ${response.status} ${body}`);
  }

  const payload = await response.json() as {
    data?: Array<{ embedding?: unknown }>;
  };
  const data = payload.data ?? [];
  return data.map((item) => normalizeEmbedding(item.embedding));
}

function normalizeEmbedding(value: unknown): number[] {
  if (!Array.isArray(value)) throw new Error("embedding 返回格式无效");
  const embedding = value.map((item) => Number(item));
  if (embedding.length === 0 || embedding.some((item) => !Number.isFinite(item))) {
    throw new Error("embedding 向量为空或包含非法数值");
  }
  return embedding;
}

function getEmbeddingEndpoint(baseUrl: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  if (base.endsWith("/embeddings")) return base;
  if (base.endsWith("/v1")) return `${base}/embeddings`;
  return `${base}/v1/embeddings`;
}

function toVectorLiteral(embedding: number[]): string {
  return `[${embedding.join(",")}]`;
}
