import { Navigate, Route, Routes } from "react-router-dom";
import { Guard } from "./components/Shell";
import { Home, Login, ProblemDetail, ProblemList, Register } from "./pages/public";
import { GovAlerts, GovApplications, GovDashboard, GovEmployees, GovProblemCreate, GovProblemDetail, GovProblems, GovStartups } from "./pages/government";
import { EvalApplicationDetail, EvalApplications, EvalDashboard, EvalDocumentDetail, EvalDocuments, EvalEvaluations } from "./pages/evaluator";
import { ProcComplaints, ProcContract, ProcDashboard, ProcKpis, ProcPilotDetail, ProcPilots, ProcRecommendations } from "./pages/procurement";
import { FieldComplaints, FieldDashboard, FieldPilotDetail, FieldPilots, FieldReports, FieldVerification } from "./pages/field";
import { StartupApplicationDetail, StartupApplications, StartupDashboard, StartupDocuments, StartupFinalReport, StartupPilotDetail, StartupPilots, StartupProblemDetail, StartupProblems, StartupProfile, StartupReports } from "./pages/startup";

function gate(roles, element) {
  return <Guard roles={roles}>{element}</Guard>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/problem-statements" element={<ProblemList />} />
      <Route path="/problem-statements/:id" element={<ProblemDetail />} />

      <Route path="/government/dashboard" element={gate(["GOVERNMENT_ADMIN"], <GovDashboard />)} />
      <Route path="/government/problem-statements" element={gate(["GOVERNMENT_ADMIN"], <GovProblems />)} />
      <Route path="/government/problem-statements/create" element={gate(["GOVERNMENT_ADMIN"], <GovProblemCreate />)} />
      <Route path="/government/problem-statements/:id" element={gate(["GOVERNMENT_ADMIN"], <GovProblemDetail />)} />
      <Route path="/government/applications" element={gate(["GOVERNMENT_ADMIN"], <GovApplications />)} />
      <Route path="/government/startups" element={gate(["GOVERNMENT_ADMIN"], <GovStartups />)} />
      <Route path="/government/alerts" element={gate(["GOVERNMENT_ADMIN"], <GovAlerts />)} />
      <Route path="/government/employees" element={gate(["GOVERNMENT_ADMIN"], <GovEmployees />)} />

      <Route path="/evaluator/dashboard" element={gate(["TECHNICAL_EVALUATOR"], <EvalDashboard />)} />
      <Route path="/evaluator/applications" element={gate(["TECHNICAL_EVALUATOR"], <EvalApplications />)} />
      <Route path="/evaluator/applications/:id" element={gate(["TECHNICAL_EVALUATOR"], <EvalApplicationDetail />)} />
      <Route path="/evaluator/documents" element={gate(["TECHNICAL_EVALUATOR"], <EvalDocuments />)} />
      <Route path="/evaluator/documents/:id" element={gate(["TECHNICAL_EVALUATOR"], <EvalDocumentDetail />)} />
      <Route path="/evaluator/evaluations" element={gate(["TECHNICAL_EVALUATOR"], <EvalEvaluations />)} />

      <Route path="/procurement/dashboard" element={gate(["PROCUREMENT_OFFICER"], <ProcDashboard />)} />
      <Route path="/procurement/pilots" element={gate(["PROCUREMENT_OFFICER"], <ProcPilots />)} />
      <Route path="/procurement/pilots/:id" element={gate(["PROCUREMENT_OFFICER"], <ProcPilotDetail />)} />
      <Route path="/procurement/pilots/:id/contract" element={gate(["PROCUREMENT_OFFICER"], <ProcContract />)} />
      <Route path="/procurement/pilots/:id/kpis" element={gate(["PROCUREMENT_OFFICER"], <ProcKpis />)} />
      <Route path="/procurement/pilots/:id/complaints" element={gate(["PROCUREMENT_OFFICER"], <ProcComplaints />)} />
      <Route path="/procurement/recommendations" element={gate(["PROCUREMENT_OFFICER"], <ProcRecommendations />)} />

      <Route path="/field/dashboard" element={gate(["FIELD_EVALUATOR"], <FieldDashboard />)} />
      <Route path="/field/pilots" element={gate(["FIELD_EVALUATOR"], <FieldPilots />)} />
      <Route path="/field/pilots/:id" element={gate(["FIELD_EVALUATOR"], <FieldPilotDetail />)} />
      <Route path="/field/pilots/:id/reports" element={gate(["FIELD_EVALUATOR"], <FieldReports />)} />
      <Route path="/field/pilots/:id/verification" element={gate(["FIELD_EVALUATOR"], <FieldVerification />)} />
      <Route path="/field/complaints" element={gate(["FIELD_EVALUATOR"], <FieldComplaints />)} />

      <Route path="/startup/dashboard" element={gate(["STARTUP"], <StartupDashboard />)} />
      <Route path="/startup/profile" element={gate(["STARTUP"], <StartupProfile />)} />
      <Route path="/startup/documents" element={gate(["STARTUP"], <StartupDocuments />)} />
      <Route path="/startup/problem-statements" element={gate(["STARTUP"], <StartupProblems />)} />
      <Route path="/startup/problem-statements/:id" element={gate(["STARTUP"], <StartupProblemDetail />)} />
      <Route path="/startup/applications" element={gate(["STARTUP"], <StartupApplications />)} />
      <Route path="/startup/applications/:id" element={gate(["STARTUP"], <StartupApplicationDetail />)} />
      <Route path="/startup/pilots" element={gate(["STARTUP"], <StartupPilots />)} />
      <Route path="/startup/pilots/:id" element={gate(["STARTUP"], <StartupPilotDetail />)} />
      <Route path="/startup/pilots/:id/reports" element={gate(["STARTUP"], <StartupReports />)} />
      <Route path="/startup/pilots/:id/final-report" element={gate(["STARTUP"], <StartupFinalReport />)} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
