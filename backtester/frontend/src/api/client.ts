const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

type FetchOptions = RequestInit & { rawText?: boolean };

export async function apiFetch<T>(path: string, init?: FetchOptions): Promise<T> {
  const { rawText, ...fetchInit } = init ?? {};
  const response = await fetch(`${API_BASE}${path}`, {
    ...fetchInit,
    headers: {
      "Content-Type": "application/json",
      ...(fetchInit?.headers ?? {})
    }
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  if (rawText) {
    return (await response.text()) as T;
  }
  return (await response.json()) as T;
}
