const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

interface ErrorPayload {
  detail?: string | Array<{ msg?: string }>;
  message?: string;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(message: string, status: number, detail: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function formatErrorDetail(payload: ErrorPayload | null, fallback: string) {
  if (!payload) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item.msg)
      .filter(Boolean)
      .join(", ");
  }
  return payload.message || fallback;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!response.ok) {
      let payload: ErrorPayload | null = null;
      try {
        payload = (await response.json()) as ErrorPayload;
      } catch {
        // 서버가 JSON 오류를 반환하지 않는 경우 상태 문구를 사용한다.
      }
      const detail = formatErrorDetail(payload, response.statusText);
      throw new ApiError(
        "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
        response.status,
        detail,
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const detail =
      error instanceof Error ? error.message : "알 수 없는 네트워크 오류";
    throw new ApiError(
      "서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.",
      0,
      detail,
    );
  }
}
