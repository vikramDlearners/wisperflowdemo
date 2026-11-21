import { careProfiles, getProfile, type CareProfileOut } from "./api";

// Medicines and prescription scans are filed under a care profile. When a family has
// none yet, create one from the parent details entered during onboarding so the user
// is never blocked. Needs the parent_profile.edit permission (Family manager has it).

// Onboarding stores the language name; care profiles take a code (en, ta, hi).
const LANGUAGE_CODES: Record<string, string> = { english: "en", tamil: "ta", hindi: "hi" };

export async function createCareProfileFromOnboarding(familyId: string): Promise<CareProfileOut> {
  const parent = await getProfile().catch(() => null);
  const fullName = parent?.parent_full_name?.trim() || "My parent";
  return careProfiles.create(familyId, {
    display_name: fullName,
    greeting_name: parent?.preferred_name?.trim() || fullName.split(/\s+/)[0],
    preferred_language: LANGUAGE_CODES[(parent?.preferred_language ?? "").toLowerCase()] ?? "en",
  });
}
