import type { AppointmentStatus, RecordType, TaskStatus } from "./types";

export const RECORD_TYPES: RecordType[] = [
  "Prescription",
  "Test result",
  "Discharge letter",
  "Report",
  "Other",
];

export const TASK_STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
];

export const APPOINTMENT_STATUSES: { value: AppointmentStatus; label: string }[] = [
  { value: "scheduled", label: "Scheduled" },
  { value: "rescheduled", label: "Rescheduled" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

// Upload rules for health record attachments (enforced on the client before upload).
export const ALLOWED_UPLOAD_TYPES = ["application/pdf", "image/png", "image/jpeg"];
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

// Member relationship labels. The stored value is the lowercase form of each label.
export const RELATIONSHIP_OPTIONS = ["Mother", "Father", "Grandmother", "Grandfather", "Other"];

