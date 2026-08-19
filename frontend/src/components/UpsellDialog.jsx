import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Check, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function UpsellDialog({ open, onOpenChange, onPurchased }) {
  const [pkgs, setPkgs] = useState([]);
  const [buying, setBuying] = useState(null);

  useEffect(() => {
    if (!open) return;
    api.get("/credits/packages").then((r) => setPkgs(r.data.packages)).catch(() => {});
  }, [open]);

  const buy = async (id) => {
    setBuying(id);
    try {
      const { data } = await api.post("/credits/purchase", { package_id: id });
      toast.success(`${data.added} kredi bakiyenize eklendi (MOCK)`, {
        description: `Yeni bakiyeniz: ${data.credits} kredi`,
      });
      onPurchased?.(data.credits);
      onOpenChange(false);
    } catch {
      toast.error("Satın alma başarısız.");
    } finally {
      setBuying(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-white" data-testid="upsell-modal">
        <DialogHeader>
          <div className="flex items-center gap-2 text-amber-600 mb-3">
            <Zap className="w-4 h-4" />
            <span className="text-xs font-mono uppercase tracking-[0.25em]">Kredi Bakiyeniz Düşük</span>
          </div>
          <DialogTitle className="text-2xl tracking-tight font-light">
            Raporlarınızı kesintisiz tamamlayın
          </DialogTitle>
          <DialogDescription className="text-zinc-600">
            Bir kredi paketi seçin — AI sorularına ve rapor oluşturmaya kaldığınız yerden devam edin.
            <span className="ml-2 text-xs font-mono uppercase tracking-widest text-amber-600">MOCK ÖDEME</span>
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-2">
          {pkgs.map((p) => (
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
              <div className="text-sm font-mono uppercase tracking-widest text-zinc-500 mb-1">{p.name}</div>
              <div className="font-black text-3xl tracking-tight text-zinc-950">{p.credits}</div>
              <div className="text-xs text-zinc-500 mb-4">kredi</div>
              <div className="text-lg font-light tracking-tight mb-4">₺{p.price_try.toLocaleString("tr-TR")}</div>
              <ul className="space-y-1.5 text-xs text-zinc-600 mb-5">
                <li className="flex gap-1.5"><Check className="w-3 h-3 mt-0.5 text-emerald-600" /> Tüm rapor türleri</li>
                <li className="flex gap-1.5"><Check className="w-3 h-3 mt-0.5 text-emerald-600" /> PDF + DOCX indirme</li>
                <li className="flex gap-1.5"><Check className="w-3 h-3 mt-0.5 text-emerald-600" /> E-mail iletimi</li>
              </ul>
              <Button
                data-testid={`buy-package-${p.id}`}
                disabled={buying === p.id}
                onClick={() => buy(p.id)}
                className={p.popular ? "bg-zinc-950 text-white hover:bg-zinc-800" : ""}
                variant={p.popular ? "default" : "outline"}
              >
                {buying === p.id ? "İşleniyor..." : "Satın Al"}
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
