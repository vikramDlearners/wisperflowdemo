import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import "../insurance.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  ApiError,
  careProfiles,
  families,
  insurance as api,
  members,
  type CareProfileOut,
  type InsuranceDocumentRead,
  type InsuranceIn,
  type InsuranceOut,
  type MemberOut,
} from "../api";
import {
  attachInsuranceDocument,
  checkDocument,
  openInsuranceDocument,
  readInsuranceDocument,
  removeInsuranceDocument,
  DUE_WITHIN_DAYS,
  FREQUENCIES,
  POLICY_TYPES,
  formatDay,
  frequencyLabel,
  parseDay,
  renewalState,
  renewalText,
  rupees,
  typeIcon,
  typeLabel,
  yearlyPremium,
} from "../insurance";

// Insurance & renewals: the family's policies (health, life, ...), when each renews, and "Mark renewed".
// Renewals due within 30 days (or overdue) are listed first, and also show on the Overview.

interface Draft {
  id: string | null; // null = new policy
  care_profile_id: string; // "" = family policy
  policy_type: InsuranceOut["policy_type"];
  insurer: string;
  plan_name: string;
  policy_number: string;
  sum_insured: string;
  premium: string;
  premium_frequency: InsuranceOut["premium_frequency"];
  start_date: string;
  renewal_date: string;
  agent_name: string;
  agent_phone: string;
  helpline: string;
  notes: string;
  responsible_user_id: string;
  // The policy document picked in the form; uploaded when the policy is saved.
  docFile: File | null;
  removeDoc: boolean;
  hasDoc: boolean; // already has one (editing)
  docName: string | null;
}

const EMPTY: Draft = {
  id: null,
  care_profile_id: "",
  policy_type: "health",
  insurer: "",
  plan_name: "",
  policy_number: "",
  sum_insured: "",
  premium: "",
  premium_frequency: "yearly",
  start_date: "",
  renewal_date: "",
  agent_name: "",
  agent_phone: "",
  helpline: "",
  notes: "",
  responsible_user_id: "",
  docFile: null,
  removeDoc: false,
  hasDoc: false,
  docName: null,
};

const toDraft = (p: InsuranceOut): Draft => ({
  id: p.id,
  care_profile_id: p.care_profile_id ?? "",
  policy_type: p.policy_type,
  insurer: p.insurer,
  plan_name: p.plan_name ?? "",
  policy_number: p.policy_number ?? "",
  sum_insured: p.sum_insured != null ? String(Number(p.sum_insured)) : "",
  premium: p.premium != null ? String(Number(p.premium)) : "",
  premium_frequency: p.premium_frequency,
  start_date: p.start_date ?? "",
  renewal_date: p.renewal_date,
  agent_name: p.agent_name ?? "",
  agent_phone: p.agent_phone ?? "",
  helpline: p.helpline ?? "",
  notes: p.notes ?? "",
  responsible_user_id: p.responsible_user_id ?? "",
  docFile: null,
  removeDoc: false,
  hasDoc: Boolean(p.has_document),
  docName: p.document_name ?? null,
});

/** Labels for what a document filled in, in form order. */
const READ_LABELS: [keyof InsuranceDocumentRead, string][] = [
  ["policy_type", "type"],
  ["insurer", "insurance company"],
  ["plan_name", "plan"],
  ["policy_number", "policy number"],
  ["renewal_date", "renewal date"],
  ["premium", "premium"],
  ["sum_insured", "sum insured"],
  ["start_date", "start date"],
  ["agent_name", "agent"],
  ["helpline", "helpline"],
];

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

/** Ends a notice with one full stop, even after a name like "Co. Ltd.". */
const sentence = (text: string) => (/[.!?]$/.test(text) ? text : `${text}.`);

const amount = (s: string) => (s.trim() === "" ? null : Math.round(Number(s) * 100) / 100);

export default function Insurance({ familyId }: { familyId: string }) {
  const [policies, setPolicies] = useState<InsuranceOut[]>([]);
  const [parents, setParents] = useState<CareProfileOut[]>([]);
  const [people, setPeople] = useState<MemberOut[]>([]);
  const [canEdit, setCanEdit] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all"); // all | family | <care profile id>
  const [draft, setDraft] = useState<Draft | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [renewing, setRenewing] = useState<{ id: string; date: string; premium: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<{ text: string; bad?: boolean } | null>(null);
  // The form as it is now, so a document read that finishes later fills the latest values.
  const draftRef = useRef<Draft | null>(null);
  draftRef.current = draft;

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      api.list(familyId),
      careProfiles.list(familyId).catch(() => [] as CareProfileOut[]),
      members.list(familyId).catch(() => [] as MemberOut[]),
      families.me(familyId).catch(() => null),
    ])
      .then(([list, profiles, team, access]) => {
        if (!active) return;
        setPolicies(list);
        setParents(profiles);
        setPeople(team.filter((m) => m.role_name.toLowerCase() !== "parent"));
        setCanEdit(access ? access.permissions.includes("reports.upload") : true);
      })
      .catch((err) => active && setError(messageOf(err, "Could not load insurance policies.")))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [familyId]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(t);
  }, [notice]);

  const parentName = (id: string | null) =>
    id ? parents.find((p) => p.id === id)?.display_name ?? "A parent" : "Whole family";
  const personName = (id: string | null) => (id && people.find((p) => p.user_id === id)?.display_name) || null;

  const shown = useMemo(
    () =>
      policies
        .filter((p) => filter === "all" || (filter === "family" ? !p.care_profile_id : p.care_profile_id === filter))
        .sort((a, b) => a.renewal_date.localeCompare(b.renewal_date)),
    [policies, filter],
  );
  const due = shown.filter((p) => renewalState(p) !== "ok");
  const later = shown.filter((p) => renewalState(p) === "ok");
  const overdueCount = policies.filter((p) => renewalState(p) === "overdue").length;
  const dueCount = policies.filter((p) => renewalState(p) === "due").length;
  const yearly = policies.reduce((sum, p) => sum + yearlyPremium(p), 0);

  const replace = (p: InsuranceOut) => setPolicies((list) => list.map((x) => (x.id === p.id ? p : x)));

  /** A document was picked in the form: keep it for upload and fill in what can be read from it. */
  async function pickDocument(file: File | undefined) {
    if (!draft || !file) return;
    const problem = checkDocument(file);
    if (problem) {
      setReadNote({ text: problem, bad: true });
      return;
    }
    setDraft((d) => (d ? { ...d, docFile: file, removeDoc: false } : d));
    setReadNote(null);
    setReading(true);
    try {
      const r = await readInsuranceDocument(familyId, file);
      if (r.source === "none") {
        setReadNote({
          text: "The document will be attached. Its details couldn't be read automatically, so please fill them in.",
        });
        return;
      }
      const current = draftRef.current;
      if (!current) return; // the form was closed meanwhile
      const filled: string[] = [];
      {
        const next = { ...current };
        // Fill only empty fields, so nothing already typed is replaced.
        const put = <K extends keyof Draft>(key: K, value: Draft[K] | null | undefined, label: string) => {
          if (value === null || value === undefined || value === "") return;
          if (key !== "policy_type" && key !== "premium_frequency" && String(next[key] ?? "").trim() !== "") return;
          next[key] = value as Draft[K];
          filled.push(label);
        };
        put("policy_type", r.policy_type ?? undefined, "type");
        put("insurer", r.insurer, "insurance company");
        put("plan_name", r.plan_name, "plan");
        put("policy_number", r.policy_number, "policy number");
        put("renewal_date", r.renewal_date, "renewal date");
        put("premium_frequency", r.premium_frequency ?? undefined, "how often it's paid");
        put("premium", r.premium != null ? String(Number(r.premium)) : null, "premium");
        put("sum_insured", r.sum_insured != null ? String(Number(r.sum_insured)) : null, "sum insured");
        put("start_date", r.start_date, "start date");
        put("agent_name", r.agent_name, "agent");
        put("agent_phone", r.agent_phone, "agent phone");
        put("helpline", r.helpline, "helpline");
        // The insured person's name matching a parent: that parent is covered.
        const insured = r.insured_name?.toLowerCase().trim();
        const match = insured
          ? parents.find((p) => {
              const name = p.display_name.toLowerCase();
              return name.includes(insured) || insured.includes(name);
            })
          : undefined;
        if (match && !next.care_profile_id) {
          next.care_profile_id = match.id;
          filled.push("who it covers");
        }
        setDraft(next);
      }
      setReadNote({
        text: filled.length
          ? `Filled ${[...new Set(filled)].join(", ")} from the document (read by Gemini). Please check them.`
          : "The document will be attached. Nothing more could be read from it.",
      });
    } catch (err) {
      setReadNote({ text: messageOf(err, "Could not read the document. It will still be attached."), bad: true });
    } finally {
      setReading(false);
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    if (!draft.insurer.trim()) return setFormError("Enter the insurance company.");
    if (!draft.renewal_date) return setFormError("Enter the renewal (due) date.");
    for (const [label, v] of [
      ["Sum insured", draft.sum_insured],
      ["Premium", draft.premium],
    ] as const) {
      if (v.trim() !== "" && !(Number(v) >= 0)) return setFormError(`${label} must be a number, 0 or more.`);
    }
    const body: InsuranceIn = {
      care_profile_id: draft.care_profile_id || null,
      policy_type: draft.policy_type,
      insurer: draft.insurer.trim(),
      plan_name: draft.plan_name.trim() || null,
      policy_number: draft.policy_number.trim() || null,
      sum_insured: amount(draft.sum_insured),
      premium: amount(draft.premium),
      premium_frequency: draft.premium_frequency,
      start_date: draft.start_date || null,
      renewal_date: draft.renewal_date,
      agent_name: draft.agent_name.trim() || null,
      agent_phone: draft.agent_phone.trim() || null,
      helpline: draft.helpline.trim() || null,
      notes: draft.notes.trim() || null,
      responsible_user_id: draft.responsible_user_id || null,
    };
    setSaving(true);
    setFormError(null);
    try {
      let saved: InsuranceOut;
      if (draft.id) {
        saved = await api.update(familyId, draft.id, body);
        replace(saved);
      } else {
        saved = await api.create(familyId, body);
        setPolicies((list) => [...list, saved]);
      }
      // The document goes up once the policy exists.
      let docProblem: string | null = null;
      try {
        if (draft.docFile) replace(await attachInsuranceDocument(familyId, saved.id, draft.docFile));
        else if (draft.removeDoc && draft.hasDoc) replace(await removeInsuranceDocument(familyId, saved.id));
      } catch (err) {
        docProblem = messageOf(err, "the upload failed");
      }
      const done = draft.id ? "Policy updated" : `Added ${saved.insurer}`;
      setNotice(docProblem ? `${done}, but the document wasn't attached: ${docProblem}` : sentence(done));
      setDraft(null);
      setReadNote(null);
    } catch (err) {
      setFormError(messageOf(err, "Could not save the policy."));
    } finally {
      setSaving(false);
    }
  }

  async function renew(p: InsuranceOut) {
    if (!renewing) return;
    if (renewing.premium.trim() !== "" && !(Number(renewing.premium) >= 0)) {
      setError("The new premium must be a number, 0 or more.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.renew(familyId, p.id, {
        renewal_date: renewing.date || null,
        premium: amount(renewing.premium),
      });
      replace(updated);
      setRenewing(null);
      setNotice(`${p.insurer} marked renewed. Next renewal: ${formatDay(updated.renewal_date)}.`);
    } catch (err) {
      setError(messageOf(err, "Could not mark it renewed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(p: InsuranceOut) {
    setBusy(true);
    setError(null);
    try {
      await api.remove(familyId, p.id);
      setPolicies((list) => list.filter((x) => x.id !== p.id));
      setConfirmDelete(null);
      setNotice(sentence(`Deleted ${p.insurer}`));
    } catch (err) {
      setError(messageOf(err, "Could not delete the policy."));
    } finally {
      setBusy(false);
    }
  }

  /** One period after the current renewal date, as the "Mark renewed" suggestion. */
  function suggestedNext(p: InsuranceOut): string {
    const months = { yearly: 12, half_yearly: 6, quarterly: 3, monthly: 1 }[p.premium_frequency] ?? 12;
    const d = parseDay(p.renewal_date);
    const target = new Date(d.getFullYear(), d.getMonth() + months, 1);
    const last = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
    target.setDate(Math.min(d.getDate(), last));
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}`;
  }

  const card = (p: InsuranceOut) => {
    const state = renewalState(p);
    const who = personName(p.responsible_user_id);
    return (
      <li key={p.id} className={`ins-card is-${state}`}>
        <div className="ins-card-top">
          <span className="ins-type" aria-hidden="true">
            {typeIcon(p.policy_type)}
          </span>
          <div className="ins-card-main">
            <strong>{p.insurer}</strong>
            <span>
              {typeLabel(p.policy_type)} insurance{p.plan_name ? ` · ${p.plan_name}` : ""}
            </span>
          </div>
          <span className={`ins-due is-${state}`}>{renewalText(p)}</span>
        </div>

        <dl className="ins-facts">
          <div>
            <dt>Covers</dt>
            <dd>{parentName(p.care_profile_id)}</dd>
          </div>
          <div>
            <dt>Renewal date</dt>
            <dd>{formatDay(p.renewal_date)}</dd>
          </div>
          <div>
            <dt>Premium</dt>
            <dd>{rupees(p.premium) ? `${rupees(p.premium)} · ${frequencyLabel(p.premium_frequency)}` : "—"}</dd>
          </div>
          <div>
            <dt>Sum insured</dt>
            <dd>{rupees(p.sum_insured) ?? "—"}</dd>
          </div>
          {p.policy_number && (
            <div>
              <dt>Policy number</dt>
              <dd className="ins-mono">{p.policy_number}</dd>
            </div>
          )}
          {(p.agent_name || p.agent_phone) && (
            <div>
              <dt>Agent</dt>
              <dd>
                {p.agent_name}
                {p.agent_name && p.agent_phone ? " · " : ""}
                {p.agent_phone && <a href={`tel:${p.agent_phone.replace(/\s/g, "")}`}>{p.agent_phone}</a>}
              </dd>
            </div>
          )}
          {p.helpline && (
            <div>
              <dt>Claims helpline</dt>
              <dd>
                <a href={`tel:${p.helpline.replace(/\s/g, "")}`}>{p.helpline}</a>
              </dd>
            </div>
          )}
          {who && (
            <div>
              <dt>Renewed by</dt>
              <dd>{who}</dd>
            </div>
          )}
          {p.last_renewed_on && (
            <div>
              <dt>Last renewed</dt>
              <dd>{formatDay(p.last_renewed_on)}</dd>
            </div>
          )}
        </dl>
        {p.notes && <p className="ins-notes">{p.notes}</p>}
        {p.has_document && (
          <button
            type="button"
            className="ins-doc"
            onClick={() =>
              void openInsuranceDocument(familyId, p.id).catch((err) =>
                setError(messageOf(err, "Could not open the document.")),
              )
            }
          >
            <span aria-hidden="true">{p.document_type === "application/pdf" ? "📄" : "🖼️"}</span>
            <span>
              <strong>Policy document</strong>
              <small>{p.document_name ?? "Open"}</small>
            </span>
            <span className="ins-doc-open">Open ↗</span>
          </button>
        )}

        {canEdit &&
          (renewing?.id === p.id ? (
            <div className="ins-renew">
              <p>
                <strong>Mark renewed</strong> · the premium is paid for the next period.
              </p>
              <div className="ins-renew-row">
                <label className="pp-field">
                  Next renewal date
                  <input
                    type="date"
                    value={renewing.date}
                    onChange={(e) => setRenewing({ ...renewing, date: e.target.value })}
                  />
                </label>
                <label className="pp-field">
                  Premium paid (₹) <span className="ins-optional">if it changed</span>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    inputMode="decimal"
                    placeholder={p.premium != null ? String(Number(p.premium)) : "e.g. 25000"}
                    value={renewing.premium}
                    onChange={(e) => setRenewing({ ...renewing, premium: e.target.value })}
                  />
                </label>
              </div>
              <div className="ins-actions">
                <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setRenewing(null)} disabled={busy}>
                  Cancel
                </button>
                <button type="button" className="pp-btn" onClick={() => void renew(p)} disabled={busy}>
                  {busy ? "Saving…" : "Confirm renewal"}
                </button>
              </div>
            </div>
          ) : confirmDelete === p.id ? (
            <div className="ins-actions ins-confirm">
              <span>Delete this policy?</span>
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setConfirmDelete(null)} disabled={busy}>
                Keep
              </button>
              <button type="button" className="pp-btn ins-danger" onClick={() => void remove(p)} disabled={busy}>
                Delete
              </button>
            </div>
          ) : (
            <div className="ins-actions">
              <button type="button" className="ins-link ins-link-danger" onClick={() => setConfirmDelete(p.id)}>
                Delete
              </button>
              <span className="ins-spacer" />
              <button
                type="button"
                className="pp-btn pp-btn-ghost"
                onClick={() => {
                  setFormError(null);
                  setReadNote(null);
                  setDraft(toDraft(p));
                }}
              >
                Edit
              </button>
              <button
                type="button"
                className={`pp-btn${state === "ok" ? " pp-btn-ghost" : ""}`}
                onClick={() => setRenewing({ id: p.id, date: suggestedNext(p), premium: "" })}
              >
                ✓ Mark renewed
              </button>
            </div>
          ))}
      </li>
    );
  };

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => draft && setDraft({ ...draft, [key]: value });

  return (
    <WorkspaceLayout familyId={familyId} current="insurance" title="Insurance & renewals">
      <div className="pp-content ins-page">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>Insurance &amp; renewals</h1>
            <p className="pp-muted">
              Keep every policy in one place and never miss a renewal. Renewals due in the next {DUE_WITHIN_DAYS} days
              also show on the Overview.
            </p>
          </div>
          {canEdit && (
            <div className="pp-head-actions">
              <button
                type="button"
                className="pp-btn"
                onClick={() => {
                  setFormError(null);
                  setReadNote(null);
                  setDraft({ ...EMPTY, care_profile_id: parents.length === 1 ? parents[0].id : "" });
                }}
              >
                + Add policy
              </button>
            </div>
          )}
        </div>

        {notice && (
          <p role="status" className="ins-notice">
            ✓ {notice}
          </p>
        )}
        {error && (
          <p role="alert" className="pp-alert">
            {error}
          </p>
        )}

        {loading ? (
          <p role="status" className="pp-muted">
            Loading policies…
          </p>
        ) : (
          <>
            <div className="ins-stats">
              <div className="ins-stat">
                <strong>{policies.length}</strong>
                <span>{policies.length === 1 ? "Policy" : "Policies"}</span>
              </div>
              <div className={`ins-stat${dueCount ? " is-due" : ""}`}>
                <strong>{dueCount}</strong>
                <span>Due in {DUE_WITHIN_DAYS} days</span>
              </div>
              <div className={`ins-stat${overdueCount ? " is-overdue" : ""}`}>
                <strong>{overdueCount}</strong>
                <span>Overdue</span>
              </div>
              <div className="ins-stat">
                <strong>{rupees(yearly) ?? "₹0"}</strong>
                <span>Premiums a year</span>
              </div>
            </div>

            {policies.length === 0 ? (
              <div className="ins-empty">
                <div aria-hidden="true">🛡️</div>
                <h2>No policies yet</h2>
                <p>
                  Add your parents' health insurance and other policies with their renewal dates. CareCircle reminds
                  the family on the Overview when a renewal is coming up.
                </p>
                {canEdit && (
                  <button type="button" className="pp-btn" onClick={() => setDraft({ ...EMPTY })}>
                    + Add the first policy
                  </button>
                )}
              </div>
            ) : (
              <>
                {(parents.length > 1 || policies.some((p) => !p.care_profile_id)) && (
                  <div className="ins-filters" role="group" aria-label="Show policies for">
                    {[
                      { key: "all", label: "All" },
                      ...parents.map((p) => ({ key: p.id, label: p.display_name })),
                      { key: "family", label: "Whole family" },
                    ].map((f) => (
                      <button
                        key={f.key}
                        type="button"
                        className={`ins-chip${filter === f.key ? " is-on" : ""}`}
                        aria-pressed={filter === f.key}
                        onClick={() => setFilter(f.key)}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                )}

                {due.length > 0 && (
                  <section aria-labelledby="ins-due-title">
                    <h2 id="ins-due-title" className="ins-section-title">
                      Renewals due <span>{due.length}</span>
                    </h2>
                    <ul className="ins-list">{due.map(card)}</ul>
                  </section>
                )}
                <section aria-labelledby="ins-all-title">
                  <h2 id="ins-all-title" className="ins-section-title">
                    {due.length ? "Later renewals" : "All policies"} <span>{later.length}</span>
                  </h2>
                  {later.length ? (
                    <ul className="ins-list">{later.map(card)}</ul>
                  ) : (
                    <p className="pp-muted">Nothing else to show.</p>
                  )}
                </section>
              </>
            )}
          </>
        )}
      </div>

      {draft && (
        <div className="ins-overlay" onMouseDown={(e) => e.target === e.currentTarget && !saving && setDraft(null)}>
          <form className="ins-modal" role="dialog" aria-modal="true" aria-label={draft.id ? "Edit policy" : "Add policy"} onSubmit={save} noValidate>
            <div className="ins-modal-head">
              <h2>{draft.id ? "Edit policy" : "Add insurance policy"}</h2>
              <button type="button" className="ins-close" aria-label="Close" onClick={() => setDraft(null)} disabled={saving}>
                ×
              </button>
            </div>

            <div className="ins-upload">
              {draft.docFile || (draft.hasDoc && !draft.removeDoc) ? (
                <div className="ins-upload-file">
                  <span aria-hidden="true">
                    {(draft.docFile?.type ?? "") === "application/pdf" || (!draft.docFile && draft.docName?.toLowerCase().endsWith(".pdf"))
                      ? "📄"
                      : "🖼️"}
                  </span>
                  <span className="ins-upload-name">
                    <strong>{draft.docFile?.name ?? draft.docName ?? "Policy document"}</strong>
                    <small>
                      {reading
                        ? "Reading the document…"
                        : draft.docFile
                          ? "Attached when you save"
                          : "Attached"}
                    </small>
                  </span>
                  <label className="ins-link">
                    Replace
                    <input
                      type="file"
                      accept="application/pdf,image/jpeg,image/png,image/webp"
                      className="ins-file-input"
                      onChange={(e) => {
                        void pickDocument(e.target.files?.[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="ins-link ins-link-danger"
                    onClick={() => {
                      setDraft({ ...draft, docFile: null, removeDoc: draft.hasDoc });
                      setReadNote(null);
                    }}
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <label className="ins-drop">
                  <input
                    type="file"
                    accept="application/pdf,image/jpeg,image/png,image/webp"
                    className="ins-file-input"
                    onChange={(e) => {
                      void pickDocument(e.target.files?.[0]);
                      e.target.value = "";
                    }}
                  />
                  <span className="ins-drop-icon" aria-hidden="true">
                    📎
                  </span>
                  <strong>Upload the policy document</strong>
                  <span>PDF or a photo (JPG, PNG, WebP) · up to 10 MB</span>
                  <span className="ins-drop-hint">We'll fill in the details we can read from it.</span>
                </label>
              )}
              {readNote && (
                <p className={`ins-read-note${readNote.bad ? " is-bad" : ""}`} role={readNote.bad ? "alert" : "status"}>
                  {readNote.text}
                </p>
              )}
            </div>

            <div className="ins-form">
              <div className="pp-field ins-span">
                <span>Type of insurance</span>
                <div className="ins-types" role="radiogroup" aria-label="Type of insurance">
                  {POLICY_TYPES.map((t) => (
                    <button
                      key={t.key}
                      type="button"
                      role="radio"
                      aria-checked={draft.policy_type === t.key}
                      className={`ins-chip${draft.policy_type === t.key ? " is-on" : ""}`}
                      onClick={() => set("policy_type", t.key)}
                    >
                      <span aria-hidden="true">{t.icon}</span> {t.label}
                    </button>
                  ))}
                </div>
              </div>
              <label className="pp-field">
                Covers
                <select value={draft.care_profile_id} onChange={(e) => set("care_profile_id", e.target.value)}>
                  <option value="">Whole family</option>
                  {parents.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="pp-field">
                Insurance company
                <input
                  value={draft.insurer}
                  maxLength={120}
                  placeholder="e.g. Star Health, LIC, HDFC Ergo"
                  autoFocus
                  onChange={(e) => set("insurer", e.target.value)}
                />
              </label>
              <label className="pp-field">
                <span>
                  Plan name <span className="ins-optional">Optional</span>
                </span>
                <input value={draft.plan_name} maxLength={160} placeholder="e.g. Senior Citizens Red Carpet" onChange={(e) => set("plan_name", e.target.value)} />
              </label>
              <label className="pp-field">
                <span>
                  Policy number <span className="ins-optional">Optional</span>
                </span>
                <input value={draft.policy_number} maxLength={80} onChange={(e) => set("policy_number", e.target.value)} />
              </label>
              <label className="pp-field">
                Renewal (due) date
                <input type="date" value={draft.renewal_date} onChange={(e) => set("renewal_date", e.target.value)} />
              </label>
              <label className="pp-field">
                Premium paid
                <select value={draft.premium_frequency} onChange={(e) => set("premium_frequency", e.target.value as Draft["premium_frequency"])}>
                  {FREQUENCIES.map((f) => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="pp-field">
                Premium (₹)
                <input type="number" min={0} step="0.01" inputMode="decimal" placeholder="e.g. 28450" value={draft.premium} onChange={(e) => set("premium", e.target.value)} />
              </label>
              <label className="pp-field">
                Sum insured (₹)
                <input type="number" min={0} step="1" inputMode="numeric" placeholder="e.g. 500000" value={draft.sum_insured} onChange={(e) => set("sum_insured", e.target.value)} />
              </label>
              <label className="pp-field">
                <span>
                  Policy start date <span className="ins-optional">Optional</span>
                </span>
                <input type="date" value={draft.start_date} onChange={(e) => set("start_date", e.target.value)} />
              </label>
              <label className="pp-field">
                <span>
                  Who renews it <span className="ins-optional">Optional</span>
                </span>
                <select value={draft.responsible_user_id} onChange={(e) => set("responsible_user_id", e.target.value)}>
                  <option value="">Not set</option>
                  {people.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.display_name} · {m.role_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="pp-field">
                <span>
                  Agent name <span className="ins-optional">Optional</span>
                </span>
                <input value={draft.agent_name} maxLength={120} onChange={(e) => set("agent_name", e.target.value)} />
              </label>
              <label className="pp-field">
                <span>
                  Agent phone <span className="ins-optional">Optional</span>
                </span>
                <input type="tel" value={draft.agent_phone} maxLength={32} placeholder="+91 98450 12345" onChange={(e) => set("agent_phone", e.target.value)} />
              </label>
              <label className="pp-field">
                <span>
                  Claims helpline <span className="ins-optional">Optional</span>
                </span>
                <input type="tel" value={draft.helpline} maxLength={32} placeholder="e.g. 1800 425 2255" onChange={(e) => set("helpline", e.target.value)} />
              </label>
              <label className="pp-field ins-span">
                <span>
                  Notes <span className="ins-optional">Optional</span>
                </span>
                <textarea rows={3} maxLength={4000} placeholder="e.g. Cashless at Apollo. Covers cataract after 2 years." value={draft.notes} onChange={(e) => set("notes", e.target.value)} />
              </label>
            </div>

            {formError && (
              <p role="alert" className="pp-alert">
                {formError}
              </p>
            )}
            <div className="ins-actions">
              <span className="ins-spacer" />
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setDraft(null)} disabled={saving}>
                Cancel
              </button>
              <button type="submit" className="pp-btn" disabled={saving || reading}>
                {saving ? "Saving…" : reading ? "Reading document…" : draft.id ? "Save changes" : "Add policy"}
              </button>
            </div>
          </form>
        </div>
      )}
    </WorkspaceLayout>
  );
}
