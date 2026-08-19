import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ArrowRight, ShieldCheck, XCircle } from "lucide-react";
import { toast } from "sonner";

/**
 * Join page: user clicks invite link (/join/:code), we validate,
 * store code in sessionStorage, then send them to Google Auth.
 * AuthCallback picks it up and uses /auth/session/invite endpoint.
 */
export default function JoinInvite() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/invites/${code}`)
      .then((r) => setInvite(r.data))
      .catch((e) => setError(e?.response?.data?.detail || "Davet geçersiz"));
  }, [code]);

  const proceed = () => {
    try {
      sessionStorage.setItem("kircan_invite_code", code);
    } catch {}
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50">
        <div className="bg-white border border-zinc-200 rounded-lg p-8 max-w-md text-center">
          <XCircle className="w-12 h-12 text-red-500 mx-auto mb-3" />
          <div className="text-lg font-medium text-zinc-900 mb-1">Davet Geçersiz</div>
          <div className="text-sm text-zinc-500 mb-4">{error}</div>
          <Button onClick={() => navigate("/", { replace: true })}>Ana sayfaya dön</Button>
        </div>
      </div>
    );
  }

  if (!invite) {
    return <div className="min-h-screen flex items-center justify-center text-zinc-500 text-sm font-mono uppercase tracking-widest">Yükleniyor...</div>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 p-6" data-testid="join-page">
      <div className="max-w-md w-full bg-white border border-zinc-200 rounded-lg p-8">
        <div className="flex items-center gap-3 mb-6">
          <img src="/kircan-logo.jpg" alt="KırCan" className="h-12 w-auto rounded" />
          <div>
            <div className="text-xs font-mono uppercase tracking-[0.28em] text-[var(--brand-gold-2)]">KırCan Report AI</div>
            <div className="text-lg font-medium text-[var(--brand-navy)]">Davetiye</div>
          </div>
        </div>

        <div className="bg-emerald-50 border border-emerald-200 rounded-md p-4 mb-6 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-600 mt-0.5" />
          <div className="text-sm">
            <div className="font-medium text-emerald-900 mb-1">Davet geçerli</div>
            <div className="text-emerald-700">
              {invite.company_name ? <><b>{invite.company_name}</b> şirketine </> : ""}
              <b>{invite.role === "admin" ? "admin" : "kullanıcı"}</b> olarak katılacaksınız.
            </div>
          </div>
        </div>

        <p className="text-sm text-zinc-600 mb-6">
          Devam etmek için Google hesabınızla giriş yapın. Otomatik olarak
          {invite.company_name ? ` ${invite.company_name} şirketine bağlanacaksınız.` : " sisteme dahil olacaksınız."}
        </p>

        <Button
          data-testid="join-continue-btn"
          onClick={proceed}
          size="lg"
          className="w-full h-12 text-white"
          style={{ backgroundColor: "var(--brand-navy)" }}
        >
          <span className="flex-1 text-left">Google ile devam et</span>
          <ArrowRight className="w-5 h-5" />
        </Button>
      </div>
    </div>
  );
}
