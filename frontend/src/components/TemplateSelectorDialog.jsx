import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Home, Building2, Map, Factory, FileText, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";

const ICONS = { Home, Building2, Map, Factory };

export default function TemplateSelectorDialog({ open, onOpenChange, onSelect }) {
  const [builtin, setBuiltin] = useState([]);
  const [custom, setCustom] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    api.get("/templates").then((r) => {
      setBuiltin(r.data.templates);
      setCustom(r.data.custom_templates || []);
    }).catch(() => {});
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto bg-white">
        <DialogHeader>
          <div className="text-xs font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">
            Adım 1 / 2
          </div>
          <DialogTitle className="text-2xl tracking-tight font-light">
            Bir rapor türü seçin
          </DialogTitle>
          <DialogDescription className="text-zinc-600">
            AI asistan seçtiğiniz şablon için gerekli bilgileri sırayla toplayacak.
          </DialogDescription>
        </DialogHeader>

        {custom.length > 0 && (
          <div className="mt-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">
                Word Kütüphaneniz · {custom.length}
              </div>
              <Button variant="ghost" size="sm" onClick={() => { onOpenChange(false); navigate("/templates"); }} className="text-xs">
                Yönet
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {custom.map((t) => (
                <button
                  key={t.template_id}
                  data-testid={`user-template-card-${t.template_id}`}
                  onClick={() => onSelect({ id: null, user_template_id: t.template_id, mode: "report" })}
                  className="text-left p-4 border border-zinc-200 rounded-md hover:border-zinc-950 hover:bg-zinc-50 transition-colors group"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="w-8 h-8 rounded-md bg-[#0055FF]/10 text-[#0055FF] group-hover:bg-[#0055FF] group-hover:text-white flex items-center justify-center transition-colors">
                      <FileText className="w-4 h-4" />
                    </div>
                    <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-400">
                      {t.fields?.length || 0} alan · ₺5/msg
                    </span>
                  </div>
                  <div className="font-medium text-zinc-950 mb-1">{t.name}</div>
                  <div className="text-xs text-zinc-500 leading-relaxed line-clamp-2">
                    {t.description || t.filename}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">
            Hazır Şablonlar
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="template-grid">
            {builtin.map((t) => {
              const Icon = ICONS[t.icon] || Home;
              return (
                <button
                  key={t.id}
                  data-testid={`template-card-${t.id}`}
                  onClick={() => onSelect(t)}
                  className="text-left p-4 border border-zinc-200 rounded-md hover:border-zinc-950 hover:bg-zinc-50 transition-colors group"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="w-8 h-8 rounded-md bg-zinc-100 group-hover:bg-zinc-950 group-hover:text-white flex items-center justify-center transition-colors">
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-400">
                      ₺{t.cost_per_message}/msg
                    </span>
                  </div>
                  <div className="font-medium text-zinc-950 mb-1">{t.name}</div>
                  <div className="text-xs text-zinc-500 leading-relaxed">{t.description}</div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-zinc-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => { onOpenChange(false); navigate("/templates"); }}
              data-testid="upload-template-cta"
            >
              <Upload className="w-3.5 h-3.5 mr-1.5" /> .docx Yükle
            </Button>
            <Button variant="outline" size="sm" data-testid="faq-mode-btn" onClick={() => onSelect({ id: null, mode: "faq" })}>
              FAQ Sohbeti
            </Button>
          </div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-400">
            {builtin.length + custom.length} şablon
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
