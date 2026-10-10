export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

interface ValidationItem {
  msg: string;
}

export function detailFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? (item as ValidationItem).msg : ""))
        .filter(Boolean)
        .join("; ");
    }
  }
  return fallback;
}

let vaultToken = "";
const albumTokens = new Map<number, string>();

export function hasVaultToken(): boolean {
  return vaultToken !== "";
}

export function clearVaultToken(): void {
  vaultToken = "";
}

export function setVaultToken(token: string): void {
  vaultToken = token;
}

export function setAlbumToken(albumId: number, token: string): void {
  albumTokens.set(albumId, token);
}

export function authToken(albumId?: number): string {
  if (albumId !== undefined && albumTokens.has(albumId)) return albumTokens.get(albumId)!;
  return vaultToken;
}

export function authHeaders(albumId?: number): Record<string, string> {
  const token = authToken(albumId);
  return token ? { "x-dam-vault": token } : {};
}

export async function api<T>(path: string, init?: RequestInit, albumId?: number): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: {
      "Content-Type": "application/json",
      "x-dam-local": "1",
      ...authHeaders(albumId),
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, detailFrom(body, res.statusText));
  }
  return (await res.json()) as T;
}

export function thumbUrl(mediaId: number, size = 384): string {
  return `/api/media/${mediaId}/thumb?s=${size}`;
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "x-dam-local": "1" },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((detail as { detail?: string }).detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export function fileUrl(mediaId: number): string {
  return `/api/media/${mediaId}/file`;
}

export function faceThumbUrl(faceId: number): string {
  return `/api/faces/${faceId}/thumb`;
}
