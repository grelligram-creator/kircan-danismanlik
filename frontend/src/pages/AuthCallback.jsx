import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = location.hash || "";
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const sessionId = params.get("session_id");
    if (!sessionId) {
      navigate("/", { replace: true });
      return;
    }

    (async () => {
      try {
        const inviteCode = sessionStorage.getItem("kircan_invite_code");
        let data;
        if (inviteCode) {
          const res = await api.post("/auth/session/invite", { session_id: sessionId, invite_code: inviteCode });
          data = res.data;
          sessionStorage.removeItem("kircan_invite_code");
        } else {
          const res = await api.post("/auth/session", { session_id: sessionId });
          data = res.data;
        }
        setUser(data.user);
        window.history.replaceState({}, document.title, "/dashboard");
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch (e) {
        console.error("Auth failed", e);
        navigate("/", { replace: true });
      }
    })();
  }, [location.hash, navigate, setUser]);

  return (
    <div className="h-screen w-full flex items-center justify-center bg-zinc-50">
      <div className="text-zinc-500 text-sm font-mono uppercase tracking-widest">Oturum kuruluyor...</div>
    </div>
  );
}
