import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import "../dashboard.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  ApiError,
  getFamilyDashboard,
  type DashboardParentOut,
  type DashboardResponse,
} from "../api";

// Parent details: GET /api/families/{familyId}/dashboard scoped to one parent.

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Could not load the parent's details.";
}

export default function ParentDetails() {
  const { familyId = "", careProfileId = "" } = useParams();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getFamilyDashboard(familyId, { care_profile_id: careProfileId })
      .then((res) => {
        if (active) setData(res);
      })
      .catch((err) => {
        if (active) setError(errorText(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [familyId, careProfileId]);

  let content: ReactNode;
  if (!data) {
    content = error ? (
      <div role="alert" className="db-banner is-error">
        {error}
      </div>
    ) : (
      <p role="status" className="pp-muted">
        {loading ? "Loading parent details…" : "No details available."}
      </p>
    );
  } else {
    const parent: DashboardParentOut | undefined =
      data.parents.find((p) => p.care_profile_id === careProfileId) ?? data.parents[0];

    content = parent ? (
      <>
        {error && (
          <div role="alert" className="db-banner is-error">
            {error}
          </div>
        )}
        <section className="db-card db-tint-teal" aria-label="Profile details">
          <h2 className="db-card-title">{parent.display_name}</h2>
          <dl className="db-facts">
            <div>
              <dt>Age</dt>
              <dd>{parent.age !== null ? `${parent.age} years` : "Not set"}</dd>
            </div>
            <div>
              <dt>Relationship</dt>
              <dd>{parent.relationship || "Not set"}</dd>
            </div>
            <div>
              <dt>Health conditions</dt>
              <dd>{parent.known_health_conditions || "None recorded"}</dd>
            </div>
            <div>
              <dt>Primary Caregiver</dt>
              <dd>{parent.primary_caregiver_name || "Not set"}</dd>
            </div>
            <div>
              <dt>Medicines</dt>
              <dd>{data.daily_medicine_count} Medicine(s) daily</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{parent.all_good ? "✓ All Good" : "Needs attention"}</dd>
            </div>
          </dl>
        </section>
      </>
    ) : (
      <p className="pp-muted">No parent found.</p>
    );
  }

  return (
    <WorkspaceLayout familyId={familyId} current="overview" title="Parent details">
      <div className="pp-content db">
        <div className="pp-page-head">
          <div>
            <h1>Parent details</h1>
            <p className="pp-muted">
              <Link to={`/family/${familyId}`}>← Back to dashboard</Link>
            </p>
          </div>
        </div>
        {content}
      </div>
    </WorkspaceLayout>
  );
}
