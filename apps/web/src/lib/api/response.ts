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

export class ApiResponseError extends CoreApiPageError {
  constructor(
    status: number,
    readonly code: string | undefined,
    message: string,
    readonly details: unknown,
    readonly requestId: string | undefined,
  ) {
    super(status, message);
    this.name = "ApiResponseError";
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

function getStringField(error: unknown, field: string): string | undefined {
  if (
    typeof error === "object" &&
    error !== null &&
    field in error &&
    typeof error[field as keyof typeof error] === "string"
  ) {
    return error[field as keyof typeof error] as string;
  }
  return undefined;
}

function getDetails(error: unknown): unknown {
  if (typeof error === "object" && error !== null && "details" in error) {
    return error.details;
  }
  return undefined;
}

export function apiError(result: { status: number; error?: unknown }): ApiResponseError {
  return new ApiResponseError(
    result.status,
    getStringField(result.error, "code"),
    getErrorMessage(result.error),
    getDetails(result.error),
    getStringField(result.error, "requestId"),
  );
}

export function requireApiData<T>(result: ApiResult<T>): T {
  if (result.data !== undefined) return result.data;
  if (result.response.status === 204) return undefined as T;
  throw apiError({ status: result.response.status, error: result.error });
}
