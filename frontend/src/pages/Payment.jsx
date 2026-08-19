import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CheckCircle2, Loader2, XCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

const fmtTRY = (n) => `₺${Number(n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

export function PaymentSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [tx, setTx] = useState(null);
  const [status, setStatus] = useState("polling"); // polling | paid | failed | timeout
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const attemptsRef = useRef(0);
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (!sessionId) {
      navigate("/dashboard", { replace: true });
      return;
    }
    const poll = async () => {
      if (stoppedRef.current) return;
      attemptsRef.current += 1;
      try {
        const { data } = await api.get(`/wallet/status/${sessionId}`);
        setTx(data);
        if ((data.payment_status || "").toLowerCase() === "paid" && data.credited) {
          setStatus("paid");
          stoppedRef.current = true;
          await refreshUser();
          return;
        }
        if (["failed", "expired"].includes((data.payment_status || "").toLowerCase())) {
          setStatus("failed");
          stoppedRef.current = true;
          return;
        }
      } catch (e) {
        // Fail fast on 404 (unknown session) instead of polling for 60s
        if (e?.response?.status === 404) {
          setStatus("failed");
          stoppedRef.current = true;
          return;
        }
      }
      if (attemptsRef.current >= 30) {
        setStatus("timeout");
        stoppedRef.current = true;
        return;
      }
      setTimeout(poll, 2000);
    };
    poll();
    return () => { stoppedRef.current = true; };
  }, [sessionId, navigate, refreshUser]);

  return (
    <div className="h-screen w-full flex items-center justify-center bg-zinc-50 p-8">
      <div className="max-w-md w-full bg-white border border-zinc-200 rounded-md p-10 text-center" data-testid="payment-success-panel">
        {status === "polling" && (
          <>
            <Loader2 className="w-10 h-10 mx-auto animate-spin text-zinc-500 mb-4" />
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-2">Doğrulanıyor</div>
            <h1 className="text-2xl tracking-tight font-light text-zinc-950 mb-2">Ödemeniz kontrol ediliyor...</h1>
            <p className="text-sm text-zinc-600">Bu birkaç saniye sürebilir. Lütfen sayfayı kapatmayın.</p>
          </>
        )}
        {status === "paid" && (
          <>
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-600 mb-4" />
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-emerald-700 mb-2">Ödeme Başarılı</div>
            <h1 className="text-2xl tracking-tight font-light text-zinc-950 mb-2">Bakiyeniz güncellendi</h1>
            <p className="text-sm text-zinc-600 mb-6">
              Cüzdanınıza <span className="font-medium text-zinc-950">{fmtTRY(tx?.credit_try)}</span> eklendi.
            </p>
            <Button
              onClick={() => navigate("/dashboard", { replace: true })}
              className="w-full bg-zinc-950 text-white hover:bg-zinc-800"
              data-testid="back-to-dashboard-btn"
            >
              Panele Dön <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </>
        )}
        {(status === "failed" || status === "timeout") && (
          <>
            <XCircle className="w-10 h-10 mx-auto text-red-600 mb-4" />
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-red-700 mb-2">Sorun Oluştu</div>
            <h1 className="text-2xl tracking-tight font-light text-zinc-950 mb-2">
              {status === "timeout" ? "Doğrulama zaman aşımı" : "Ödeme başarısız"}
            </h1>
            <p className="text-sm text-zinc-600 mb-6">Lütfen tekrar deneyin veya destekle iletişime geçin.</p>
            <Button onClick={() => navigate("/dashboard", { replace: true })} variant="outline" className="w-full">
              Panele Dön
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

export function PaymentCancel() {
  const navigate = useNavigate();
  return (
    <div className="h-screen w-full flex items-center justify-center bg-zinc-50 p-8">
      <div className="max-w-md w-full bg-white border border-zinc-200 rounded-md p-10 text-center">
        <XCircle className="w-10 h-10 mx-auto text-zinc-400 mb-4" />
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-2">İptal edildi</div>
        <h1 className="text-2xl tracking-tight font-light text-zinc-950 mb-2">Ödeme tamamlanmadı</h1>
        <p className="text-sm text-zinc-600 mb-6">İşleminizi tamamlamadınız. Dilediğiniz zaman tekrar deneyebilirsiniz.</p>
        <Button onClick={() => navigate("/dashboard", { replace: true })} className="w-full bg-zinc-950 text-white hover:bg-zinc-800">
          Panele Dön
        </Button>
      </div>
    </div>
  );
}
