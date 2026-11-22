import { useEffect, useState } from "react";
import { API_BASE_URL, ApiError, getSessionToken, type MedicineOut } from "./api";

// Medicine photos, under /api/families/{family_id}/medicines:
//
//   POST /{medicine_id}/image   multipart field "file" (JPEG, PNG or WebP, up to 10 MB)
//        -> the updated medicine. Needs medicines.edit. Wrong type / empty / too large -> 400.
//   GET  /{medicine_id}/image   -> the image bytes with their content type, or 404 if none.
//        Needs medicines.view.
//
// There is no delete endpoint, so a saved photo can be replaced but not removed.
// The GET needs the Bearer token, so images are fetched and shown as blob: URLs.

export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/** Thrown when the server has no medicine photo route at all (not deployed yet). */
export class ImageUploadUnavailable extends Error {
  constructor() {
    super("Photo upload isn't available on the server yet.");
    this.name = "ImageUploadUnavailable";
  }
}

const imagePath = (familyId: string, medicineId: string) =>
  `${API_BASE_URL}/api/families/${familyId}/medicines/${medicineId}/image`;

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

export async function uploadMedicineImage(familyId: string, medicineId: string, file: File): Promise<MedicineOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(imagePath(familyId, medicineId), {
    method: "POST",
    headers: { Accept: "application/json", ...authHeaders() },
    body: form,
  });
  if (!res.ok) {
    const detail = await detailOf(res);
    // FastAPI answers an unknown route with 404 {"detail":"Not Found"} or 405.
    if (res.status === 405 || (res.status === 404 && (detail === "" || detail === "Not Found")))
      throw new ImageUploadUnavailable();
    throw new ApiError(res.status, detail || res.statusText || "Upload failed");
  }
  return (await res.json()) as MedicineOut;
}

/** Fetches the medicine's photo as a blob: URL, or null when it has none (404). */
export async function fetchMedicineImage(familyId: string, medicineId: string): Promise<string | null> {
  const res = await fetch(imagePath(familyId, medicineId), { headers: authHeaders() });
  if (res.status === 404 || res.status === 405) return null;
  if (!res.ok) throw new ApiError(res.status, (await detailOf(res)) || res.statusText);
  const blob = await res.blob();
  return blob.size > 0 ? URL.createObjectURL(blob) : null;
}

/**
 * React hook: the photo for one medicine as a blob: URL (null while loading or when there is
 * none). Pass a changing `version` to refetch after an upload. Frees the URL on unmount.
 */
export function useMedicineImage(familyId: string, medicineId: string | null, version = 0): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!medicineId) {
      setUrl(null);
      return;
    }
    let active = true;
    let created: string | null = null;
    fetchMedicineImage(familyId, medicineId)
      .then((u) => {
        created = u;
        if (active) setUrl(u);
        else if (u) URL.revokeObjectURL(u);
      })
      .catch(() => {
        if (active) setUrl(null);
      });
    return () => {
      active = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [familyId, medicineId, version]);
  return url;
}

/** Returns an error message for a picked file, or null when it's fine. */
export function checkImageFile(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return "Use a JPG, PNG or WebP photo.";
  if (file.size === 0) return "This file is empty. Please choose another photo.";
  if (file.size > MAX_IMAGE_BYTES) return "This photo is larger than 10 MB. Please choose a smaller one.";
  return null;
}

// ---------- pricing helpers ----------

/** Formats a price (number or decimal string) as Indian rupees, or null when unset. */
export function formatPrice(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}
