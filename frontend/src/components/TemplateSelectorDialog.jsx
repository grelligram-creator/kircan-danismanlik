import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Home, Building2, Map, Factory } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const ICONS = { Home, Building2, Map, Factory };

export default function TemplateSelectorDialog({ open, onOpenChange, onSelect }) {
  const [templates, setTemplates] = useState([]);

  useEffect(() => {
    if (!open) return;
    api.get("/templates").then((r) => setTemplates(r.data.templates)).catch(() => {});
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl bg-white">
        <DialogHeader>
          <div className="text-xs font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">
            Adım 1 / 2
          </div>
          <DialogTitle className="text-2xl tracking-tight font-light">
            Bir rapor türü seçin
          </DialogTitle>
          <DialogDescription className="text-zinc-600">
            AI asistan seçtiğiniz rapor için gereken bilgileri sırayla sizinle toplayacak.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4" data-testid="template-grid">
          {templates.map((t) => {
            const Icon = ICONS[t.icon] || Home;
            return (
              <button
                key={t.id}
                data-testid={`template-card-${t.id}`}
                onClick={() => onSelect(t)}
                className="text-left p-5 border border-zinc-200 rounded-md hover:border-zinc-950 hover:bg-zinc-50 transition-colors group"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-9 h-9 rounded-md bg-zinc-100 group-hover:bg-zinc-950 group-hover:text-white flex items-center justify-center transition-colors">
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-400">
                    ₺{t.cost_per_message}/msg
                  </span>
                </div>
                <div className="font-medium text-zinc-950 mb-1">{t.name}</div>
                <div className="text-sm text-zinc-600 leading-relaxed">{t.description}</div>
              </button>
            );
          })}
        </div>

        <div className="mt-2 pt-4 border-t border-zinc-200 flex items-center justify-between">
          <div className="text-xs text-zinc-500">Ya da sadece teknik soru sormak istiyorum:</div>
          <Button
            variant="outline"
            data-testid="faq-mode-btn"
            onClick={() => onSelect({ id: null, mode: "faq" })}
          >
            FAQ Sohbeti Başlat
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
