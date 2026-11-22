import { Route, Routes } from "react-router-dom";
import { useAuthStatus } from "./api/hooks";
import { Layout } from "./components/Layout";
import { ErrorState, Skeleton } from "./components/ui";
import { CheckInPage } from "./pages/CheckIn";
import { Dashboard } from "./pages/Dashboard";
import { EvaluationPage } from "./pages/Evaluation";
import { InsightsPage } from "./pages/Insights";
import { Login } from "./pages/Login";
import { SchedulePage } from "./pages/Schedule";
import { SettingsPage } from "./pages/Settings";
import { TasksPage } from "./pages/Tasks";
import { WhatIfPage } from "./pages/WhatIf";

export default function App() {
  const auth = useAuthStatus();
  if (auth.isLoading) return <div className="p-10"><Skeleton className="h-8 w-48" /></div>;
  if (auth.error) return <div className="p-10"><ErrorState error={auth.error} onRetry={() => auth.refetch()} /></div>;
  if (!auth.data?.logged_in || !auth.data.user) return <Login firstRun={!auth.data?.has_account} />;
  return (
    <Layout user={auth.data.user}>
      <Routes>
        <Route path="/" element={<Dashboard user={auth.data.user} />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/check-in" element={<CheckInPage />} />
        <Route path="/schedule" element={<SchedulePage />} />
        <Route path="/insights" element={<InsightsPage />} />
        <Route path="/what-if" element={<WhatIfPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Dashboard user={auth.data.user} />} />
      </Routes>
    </Layout>
  );
}
