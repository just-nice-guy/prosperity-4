import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "../components/Shell";
import { DataPage } from "../pages/DataPage";
import { BacktestPage } from "../pages/BacktestPage";
import { ResultsPage } from "../pages/ResultsPage";
import { ComparisonPage } from "../pages/ComparisonPage";
import { VisualizerPage } from "../pages/VisualizerPage";
import { SyntheticsPage } from "../pages/SyntheticsPage";
import { SyntheticsDetailPage } from "../pages/SyntheticsDetailPage";
import { ResearchLabPage } from "../pages/ResearchLabPage";
import { ResearchCpcvPage } from "../pages/ResearchCpcvPage";
import { ResearchOptimizationPage } from "../pages/ResearchOptimizationPage";
import { SettingsPage } from "../pages/SettingsPage";

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to="/data" replace />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/results/:runId" element={<ResultsPage />} />
        <Route path="/comparison/:comparisonId" element={<ComparisonPage />} />
        <Route path="/visualizer" element={<VisualizerPage />} />
        <Route path="/synthetics" element={<SyntheticsPage />} />
        <Route path="/synthetics/:label/:scenario" element={<SyntheticsDetailPage />} />
        <Route path="/research" element={<ResearchLabPage />} />
        <Route path="/research/:mcId" element={<ResearchLabPage />} />
        <Route path="/cpcv" element={<ResearchCpcvPage />} />
        <Route path="/cpcv/:cpcvId" element={<ResearchCpcvPage />} />
        <Route path="/optimization" element={<ResearchOptimizationPage />} />
        <Route path="/optimization/:optId" element={<ResearchOptimizationPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/data" replace />} />
      </Routes>
    </Shell>
  );
}
