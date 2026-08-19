import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Check, Wallet, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";

const fmtTRY = (n) => `₺${Number(n).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

export default function WalletDialog({ open, onOpenChange }) {
  const [pkgs, setPkgs] = useState([]);
  const [costs, setCosts] = useState(null);
  const [redirecting, setRedirecting] = useState(null);

  useEffect(() => {
    if (!open) return;
    api.get("/wallet/packages").then((r) => setPkgs(r.data.packages)).catch(() => {});
    api.get("/wallet/costs").then((r) => setCosts(r.data)).catch(() => {});
  }, [open]);

  const startCheckout = async (pkg) => {
    setRedirecting(pkg.id);
    try {
      const { data } = await api.post("/wallet/checkout", {
        package_id: pkg.id,
        origin_url: window.location.origin,
      });
      window.location.href = data.checkout_url;
    } catch (e) {
      toast.error("Ödeme başlatılamadı", { description: e?.response?.data?.detail || "Lütfen tekrar deneyin." });
      setRedirecting(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl bg-white" data-testid="wallet-modal">
        <DialogHeader>
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Wallet className="w-4 h-4" />
            <span className="text-[10px] font-mono uppercase tracking-[0.25em]">Cüzdanınıza Yükleyin</span>
          </div>
          <DialogTitle className="text-2xl tracking-tight font-light">
            Bakiye ekleyin, mesaj başı ödeyin
          </DialogTitle>
          <DialogDescription className="text-zinc-600">
            Her mesajın maliyeti seçtiğiniz rapor türüne göre değişir. Bakiyeniz kalıcıdır — istediğiniz zaman kullanın.
          </DialogDescription>
        </DialogHeader>

        {costs && (
          <div className="border border-zinc-200 rounded-md p-3 bg-zinc-50 mb-2">
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">Mesaj Başı Maliyet</div>
            <div className="flex flex-wrap gap-3 text-xs">
              <span className="font-mono">FAQ · {fmtTRY(costs.faq)}</span>
              {costs.templates.map((t) => (
                <span key={t.id} className="font-mono">
                  {t.name.split(" ")[0]} · {fmtTRY(t.cost_per_message)}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-2">
          {pkgs.map((p) => {
            const total = p.amount_try + p.bonus_try;
            return (
              <div
                key={p.id}
                className={`relative p-5 border rounded-md flex flex-col ${
                  p.popular ? "border-zinc-950 bg-zinc-50" : "border-zinc-200"
                }`}
              >
                {p.popular && (
                  <span className="absolute -top-2 left-4 text-[10px] font-mono uppercase tracking-widest bg-zinc-950 text-white px-2 py-0.5 rounded">
                    Popüler
                  </span>
                )}
                <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-1">{p.label}</div>
                <div className="font-black text-3xl tracking-tight text-zinc-950">{fmtTRY(p.amount_try)}</div>
                {p.bonus_try > 0 ? (
                  <div className="mt-1 inline-flex items-center gap-1 text-xs text-emerald-700">
                    <Sparkles className="w-3 h-3" /> +{fmtTRY(p.bonus_try)} bonus
                  </div>
                ) : (
                  <div className="mt-1 text-xs text-zinc-400">bonus yok</div>
                )}
                <div className="text-xs text-zinc-500 mb-4 mt-2">Toplam bakiye: <span className="font-medium text-zinc-950">{fmtTRY(total)}</span></div>
                <ul className="space-y-1.5 text-xs text-zinc-600 mb-5">
                  <li className="flex gap-1.5"><Check className="w-3 h-3 mt-0.5 text-emerald-600" /> Tüm rapor türleri</li>
                  <li className="flex gap-1.5"><Check className="w-3 h-3 mt-0.5 text-emerald-600" /> PDF + DOCX indirme</li>
                  <li className="flex gap-1.5"><Check className="w-3 h-3 mt-0.5 text-emerald-600" /> E-mail iletimi</li>
                </ul>
                <Button
                  data-testid={`buy-package-${p.id}`}
                  disabled={redirecting !== null}
                  onClick={() => startCheckout(p)}
                  className={p.popular ? "bg-zinc-950 text-white hover:bg-zinc-800" : ""}
                  variant={p.popular ? "default" : "outline"}
                >
                  {redirecting === p.id ? "Yönlendiriliyor..." : "Stripe ile Öde"}
                </Button>
              </div>
            );
          })}
        </div>
        <div className="mt-2 text-[10px] font-mono uppercase tracking-widest text-zinc-400 text-center">
          Stripe test modu · Test kartı: 4242 4242 4242 4242
        </div>
      </DialogContent>
    </Dialog>
  );
}
