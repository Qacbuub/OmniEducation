import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { GuestOnly, HomeRedirect, RequireAuth, SignedOutLink } from "./auth/guards";
import { MODE } from "./config/roles";
import AppShell from "./components/layout/AppShell";
import Login from "./pages/auth/Login";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";
import AcceptInvitation from "./pages/auth/AcceptInvitation";
import PlatformDashboard from "./pages/platform/PlatformDashboard";
import Institutions from "./pages/platform/Institutions";
import InstitutionDetail from "./pages/platform/InstitutionDetail";
import PlatformInvitations from "./pages/platform/PlatformInvitations";
import SchoolDashboard from "./pages/school/SchoolDashboard";
import Classes from "./pages/school/Classes";
import Attendance from "./pages/school/Attendance";
import SchoolTimetable from "./pages/school/Timetable";
import Homework from "./pages/school/Homework";
import Marks from "./pages/school/Marks";
import ReportCards from "./pages/school/ReportCards";
import Promotions from "./pages/school/Promotions";
import MyChildren from "./pages/school/MyChildren";
import UniversityDashboard from "./pages/university/UniversityDashboard";
import Programs from "./pages/university/Programs";
import Offerings from "./pages/university/Offerings";
import Registration from "./pages/university/Registration";
import UniTimetable from "./pages/university/Timetable";
import Gradebook from "./pages/university/Gradebook";
import GradeApprovals from "./pages/university/GradeApprovals";
import Transcript from "./pages/university/Transcript";
import DegreeAudit from "./pages/university/DegreeAudit";
import Students from "./pages/common/Students";
import StudentDetail from "./pages/common/StudentDetail";
import Admissions from "./pages/common/Admissions";
import Announcements from "./pages/common/Announcements";
import Notifications from "./pages/common/Notifications";
import FeeLedger from "./pages/common/FeeLedger";
import Staff from "./pages/common/Staff";
import Reports from "./pages/common/Reports";
import AuditLog from "./pages/common/AuditLog";
import Settings from "./pages/common/Settings";
import Profile from "./pages/common/Profile";
import SchoolSetup from "./pages/school/Setup";
import UniversitySetup from "./pages/university/Setup";
import MyCourses from "./pages/university/MyCourses";
import { NotFound } from "./pages/common/ComingSoon";

/** Screens every institution has; the same components adapt to school or university mode. */
function sharedRoutes(base) {
  return [
    <Route key="students" path={`${base}/students`} element={<Students />} />,
    <Route key="student" path={`${base}/students/:id`} element={<StudentDetail />} />,
    <Route key="admissions" path={`${base}/admissions`} element={<Admissions />} />,
    <Route key="announcements" path={`${base}/announcements`} element={<Announcements />} />,
    <Route key="notifications" path={`${base}/notifications`} element={<Notifications />} />,
    <Route key="fees" path={`${base}/fees`} element={<FeeLedger />} />,
    <Route key="staff" path={`${base}/staff`} element={<Staff />} />,
    <Route key="reports" path={`${base}/reports`} element={<Reports />} />,
    <Route key="audit" path={`${base}/audit`} element={<AuditLog />} />,
    <Route key="settings" path={`${base}/settings`} element={<Settings />} />,
    <Route key="profile" path={`${base}/profile`} element={<Profile />} />,
    <Route key="404" path={`${base}/*`} element={<NotFound />} />,
  ];
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<GuestOnly />}>
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
          </Route>
          <Route element={<SignedOutLink />}>
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/accept-invitation" element={<AcceptInvitation />} />
          </Route>

          {/* Platform super admin */}
          <Route element={<RequireAuth mode={MODE.PLATFORM} />}>
            <Route element={<AppShell />}>
              <Route path="/platform" element={<PlatformDashboard />} />
              <Route path="/platform/institutions" element={<Institutions />} />
              <Route path="/platform/institutions/:id" element={<InstitutionDetail />} />
              <Route path="/platform/invitations" element={<PlatformInvitations />} />
              <Route path="/platform/audit" element={<AuditLog />} />
              <Route path="/platform/profile" element={<Profile />} />
              <Route path="/platform/*" element={<NotFound />} />
            </Route>
          </Route>

          {/* School (K-12) */}
          <Route element={<RequireAuth mode={MODE.SCHOOL} />}>
            <Route element={<AppShell />}>
              <Route path="/school" element={<SchoolDashboard />} />
              <Route path="/school/children" element={<MyChildren />} />
              <Route path="/school/classes" element={<Classes />} />
              <Route path="/school/attendance" element={<Attendance />} />
              <Route path="/school/timetable" element={<SchoolTimetable />} />
              <Route path="/school/assignments" element={<Homework />} />
              <Route path="/school/marks" element={<Marks />} />
              <Route path="/school/report-cards" element={<ReportCards />} />
              <Route path="/school/promotions" element={<Promotions />} />
              <Route path="/school/setup" element={<SchoolSetup />} />
              {sharedRoutes("/school")}
            </Route>
          </Route>

          {/* University */}
          <Route element={<RequireAuth mode={MODE.UNIVERSITY} />}>
            <Route element={<AppShell />}>
              <Route path="/university" element={<UniversityDashboard />} />
              <Route path="/university/programs" element={<Programs />} />
              <Route path="/university/offerings" element={<Offerings />} />
              <Route path="/university/registration" element={<Registration />} />
              <Route path="/university/timetable" element={<UniTimetable />} />
              <Route path="/university/gradebook" element={<Gradebook />} />
              <Route path="/university/grade-approvals" element={<GradeApprovals />} />
              <Route path="/university/transcript" element={<Transcript />} />
              <Route path="/university/degree-audit" element={<DegreeAudit />} />
              <Route path="/university/setup" element={<UniversitySetup />} />
              <Route path="/university/my-courses" element={<MyCourses />} />
              {sharedRoutes("/university")}
            </Route>
          </Route>

          <Route path="/" element={<HomeRedirect />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
