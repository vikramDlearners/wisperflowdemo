import { API_BASE_URL, ApiError, getSessionToken, type ParentProfileOut } from "./api";

// Parent profile photos uploaded from the device.
//   Own profile:  PUT/GET/DELETE /api/auth/me/profile/photo
//   Parent tab:   PUT/GET/DELETE /api/families/{familyId}/parents/{careProfileId}/profile/photo
// PUT takes multipart field "file" (JPEG, PNG or WebP, up to 10 MB) and returns the profile (has_photo).
// GET needs the Bearer token, so the photo is fetched and shown as a blob: URL.

export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const MAX_PHOTO_BYTES = 10 * 1024 * 1024;

export interface PhotoTarget {
  familyId: string | null;
  careProfileId: string | null; // null = the signed-in user's own profile
}

function photoUrl(t: PhotoTarget): string {
  return t.careProfileId && t.familyId
    ? `${API_BASE_URL}/api/families/${t.familyId}/parents/${t.careProfileId}/profile/photo`
    : `${API_BASE_URL}/api/auth/me/profile/photo`;
}

function authHeaders(): Record<string, string> {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function detailOf(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    return typeof data.detail === "string" ? data.detail : "";
  } catch {
    return "";
  }
}

/** The uploaded photo as a blob: URL, or null when there is none. */
export async function fetchProfilePhoto(t: PhotoTarget): Promise<string | null> {
  const res = await fetch(photoUrl(t), { headers: authHeaders() });
  if (!res.ok) return null;
  return URL.createObjectURL(await res.blob());
}

export async function uploadProfilePhoto(t: PhotoTarget, file: File): Promise<ParentProfileOut> {
  if (!PHOTO_TYPES.includes(file.type)) throw new ApiError(400, "Choose a JPEG, PNG or WebP picture.");
  if (file.size > MAX_PHOTO_BYTES) throw new ApiError(400, "The picture must be 10 MB or smaller.");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(photoUrl(t), {
    method: "PUT",
    headers: { Accept: "application/json", ...authHeaders() },
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, (await detailOf(res)) || "Could not upload the picture.");
  return (await res.json()) as ParentProfileOut;
}

export async function removeProfilePhoto(t: PhotoTarget): Promise<void> {
  const res = await fetch(photoUrl(t), { method: "DELETE", headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, (await detailOf(res)) || "Could not remove the picture.");
}
