import type { ReactNode } from "react";
import { Route, Routes, useParams } from "react-router-dom";
import SignIn from "./pages/SignIn";
import ParentAcceptInvite from "./pages/ParentAcceptInvite";
import Landing from "./pages/Landing";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import ParentProfile from "./pages/ParentProfile";
import MedicineList from "./pages/MedicineList";
import MedicineForm from "./pages/MedicineForm";
import MedicineDetail from "./pages/MedicineDetail";
import PrescriptionScan from "./pages/PrescriptionScan";
import CareVoiceActivity from "./pages/CareVoiceActivity";
import FamilyTasks from "./pages/FamilyTasks";
import Appointments from "./pages/Appointments";
import SharedRecords from "./pages/SharedRecords";
import FamilyTimeline from "./pages/FamilyTimeline";
import MembersPermissions from "./pages/MembersPermissions";
import NotificationSettings from "./pages/NotificationSettings";
import ParentHome from "./pages/ParentHome";
import ParentCheckin from "./pages/ParentCheckin";
import ParentConfirmation from "./pages/ParentConfirmation";
import ParentHelp from "./pages/ParentHelp";
import ParentOnboarding from "./pages/ParentOnboarding";

// Reads :familyId from the URL and renders the page with it.
function FamilyRoute({ render }: { render: (familyId: string) => ReactNode }) {
  const { familyId = "" } = useParams();
  return <>{render(familyId)}</>;
}

// Reads :familyId and :medicineId from the URL and renders the page with them.
function MedicineRoute({
  render,
}: {
  render: (familyId: string, medicineId: string) => ReactNode;
}) {
  const { familyId = "", medicineId = "" } = useParams();
  return <>{render(familyId, medicineId)}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/start" element={<Landing />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/parent/accept-invite" element={<ParentAcceptInvite />} />

      <Route path="/family/:familyId" element={<Dashboard />} />
      <Route
        path="/family/:familyId/profile"
        element={<FamilyRoute render={(familyId) => <ParentProfile familyId={familyId} />} />}
      />
      <Route
        path="/family/:familyId/medicines"
        element={<FamilyRoute render={(familyId) => <MedicineList familyId={familyId} />} />}
      />
      <Route
        path="/family/:familyId/medicines/new"
        element={<FamilyRoute render={(familyId) => <MedicineForm familyId={familyId} />} />}
      />
      <Route
        path="/family/:familyId/prescription-scan"
        element={
          <FamilyRoute render={(familyId) => <PrescriptionScan familyId={familyId} />} />
        }
      />
      <Route
        path="/family/:familyId/medicines/:medicineId"
        element={
          <MedicineRoute
            render={(familyId, medicineId) => (
              <MedicineDetail familyId={familyId} medicineId={medicineId} />
            )}
          />
        }
      />
      <Route
        path="/family/:familyId/activity"
        element={<FamilyRoute render={(familyId) => <CareVoiceActivity familyId={familyId} />} />}
      />
      <Route
        path="/family/:familyId/tasks"
        element={<FamilyRoute render={(familyId) => <FamilyTasks familyId={familyId} />} />}
      />
      <Route path="/family/:familyId/appointments" element={<Appointments />} />
      <Route path="/family/:familyId/records" element={<SharedRecords />} />
      <Route path="/family/:familyId/timeline" element={<FamilyTimeline />} />
      <Route
        path="/family/:familyId/members"
        element={<FamilyRoute render={(familyId) => <MembersPermissions familyId={familyId} />} />}
      />
      <Route
        path="/family/:familyId/notifications"
        element={
          <FamilyRoute render={(familyId) => <NotificationSettings familyId={familyId} />} />
        }
      />

      <Route path="/parent/home" element={<ParentHome />} />
      <Route path="/parent/checkin" element={<ParentCheckin />} />
      <Route path="/parent/confirmation" element={<ParentConfirmation />} />
      <Route path="/parent/help" element={<ParentHelp />} />
      <Route path="/onboarding/parent" element={<ParentOnboarding />} />
    </Routes>
  );
}
