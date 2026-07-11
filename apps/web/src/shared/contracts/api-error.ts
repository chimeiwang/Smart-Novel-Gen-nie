/**
 * API 错误响应契约。
 *
 * @module shared/contracts/api-error
 * @description 统一接口校验失败和业务失败的中文错误结构，前端不需要猜测返回格式。
 */

import { z } from "zod";

export const ApiValidationIssueSchema = z.object({
  path: z.string(),
  message: z.string(),
});
export type ApiValidationIssue = z.infer<typeof ApiValidationIssueSchema>;

export const ApiErrorResponseSchema = z.object({
  error: z.string(),
  issues: z.array(ApiValidationIssueSchema).optional(),
});
export type ApiErrorResponse = z.infer<typeof ApiErrorResponseSchema>;

export function formatZodIssues(error: z.ZodError): ApiValidationIssue[] {
  return error.issues.map((issue) => ({
    path: issue.path.length > 0 ? issue.path.join(".") : "body",
    message: issue.message,
  }));
}

export function createApiErrorResponse(
  error: string,
  init?: ResponseInit & { issues?: ApiValidationIssue[] }
): Response {
  return Response.json(
    {
      error,
      ...(init?.issues?.length ? { issues: init.issues } : {}),
    } satisfies ApiErrorResponse,
    { status: init?.status ?? 400, headers: init?.headers }
  );
}

export function createZodErrorResponse(error: z.ZodError, message = "参数校验失败"): Response {
  return createApiErrorResponse(message, {
    status: 400,
    issues: formatZodIssues(error),
  });
}
