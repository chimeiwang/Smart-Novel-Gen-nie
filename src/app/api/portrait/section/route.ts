import { NextRequest } from "next/server";

import { PortraitAgentStream, createPortraitAgentStream } from "@/agents/portrait-agent-stream";
import { prisma } from "@/shared/db/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type SectionKey = "creativeMethodology" | "uniqueMarkers" | "generationStyle" | "expressionFeatures" | "styleTraits";

export async function POST(request: NextRequest) {
  const { styleId, section } = await request.json();

  if (!styleId || !section) {
    return new Response(JSON.stringify({ error: "缺少参数" }), { status: 400 });
  }

  // 获取参考资料
  const references = await prisma.styleReference.findMany({
    where: { styleId, status: "ready" },
  });

  if (references.length === 0) {
    return new Response(JSON.stringify({ error: "没有可用的参考资料" }), { status: 400 });
  }

  // 读取文件内容
  const fs = await import("node:fs/promises");
  const texts: string[] = [];
  let totalCharCount = 0;

  for (const ref of references) {
    const content = await fs.readFile(ref.filepath, "utf-8");
    texts.push(`参考资料：${ref.filename}\n\n${content}`);
    totalCharCount += ref.charCount;
  }

  const sourceText = texts.join("\n\n");

  const encoder = new TextEncoder();
  const agent = await createPortraitAgentStream();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: object) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      try {
        send({ type: "start", totalCharCount });

        let fullContent = "";

        const finalContent = await agent.generateSectionStream(
          section as SectionKey,
          sourceText,
          (chunk) => {
            fullContent += chunk;
            send({ type: "chunk", content: chunk });
          }
        );

        // 保存到数据库
        await prisma.writingStyle.update({
          where: { id: styleId },
          data: {
            [section]: finalContent,
            originalCharCount: totalCharCount,
            usedCharCount: Math.min(sourceText.length, 50000),
            truncated: sourceText.length > 50000,
          },
        });

        // 检查是否所有维度都完成了
        const style = await prisma.writingStyle.findUnique({
          where: { id: styleId },
        });

        const allSectionsComplete =
          style?.creativeMethodology &&
          style?.uniqueMarkers &&
          style?.generationStyle &&
          style?.expressionFeatures &&
          style?.styleTraits;

        if (allSectionsComplete) {
          // 生成完整段落文本。portraitMarkdown 是历史字段名，保留用于兼容旧数据结构。
          const portraitMarkdown = [
            "创作方法论", style.creativeMethodology, "",
            "独特标记", style.uniqueMarkers, "",
            "生成风格", style.generationStyle, "",
            "表达特征", style.expressionFeatures, "",
            "风格特质", style.styleTraits,
          ].join("\n");

          await prisma.writingStyle.update({
            where: { id: styleId },
            data: { portraitMarkdown },
          });
        }

        send({ type: "done", content: finalContent });
        controller.close();
      } catch (error) {
        const message = error instanceof Error ? error.message : "生成失败";
        send({ type: "error", message });
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}
