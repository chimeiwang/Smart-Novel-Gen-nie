type ApiResult<T> = {
  data?: T;
  error?: unknown;
  response: Response;
};

export class CoreApiPageError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "CoreApiPageError";
  }
}

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string" &&
    error.message.trim()
  ) {
    return error.message;
  }
  return "请求核心服务失败";
}

export function requireApiData<T>(result: ApiResult<T>): T {
  if (result.data !== undefined) return result.data;
  if (result.response.status === 204) return undefined as T;
  throw new CoreApiPageError(result.response.status, getErrorMessage(result.error));
}
