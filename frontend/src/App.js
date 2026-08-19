import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import AuthCallback from "@/pages/AuthCallback";
import Analytics from "@/pages/Analytics";
import TemplateManager from "@/pages/TemplateManager";
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";
import { Toaster } from "@/components/ui/sonner";

function AppRouter() {
  const location = useLocation();
  // Detect session_id in URL fragment BEFORE ProtectedRoute runs
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<RootRoute />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/analytics" element={<Analytics />} />
      <Route path="/templates" element={<TemplateManager />} />
      <Route path="/payment/success" element={<PaymentSuccess />} />
      <Route path="/payment/cancel" element={<PaymentCancel />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function RootRoute() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-zinc-50">
        <div className="text-zinc-500 text-sm font-mono uppercase tracking-widest">Yükleniyor...</div>
      </div>
    );
  }
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
}

function App() {
  return (
    <div className="App min-h-screen">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster position="top-right" richColors />
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
