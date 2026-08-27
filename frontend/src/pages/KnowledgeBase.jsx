import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ArrowLeft, Upload, FileText, Trash2, Globe, Building2, DatabaseZap, HelpCircle, Plus } from "lucide-react";

export default function KnowledgeBase() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("docs");
  const [docs, setDocs] = useState([]);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [scope, setScope] = useState("company");
  const [busy, setBusy] = useState(false);
  // FAQ state
  const [faqQ, setFaqQ] = useState("");
  const [faqA, setFaqA] = useState("");
  const [faqScope, setFaqScope] = useState("company");
  const [faqBusy, setFaqBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/kb/list");
      setDocs(data.documents || []);
    } catch { toast.error("Liste yüklenemedi"); }
  };

  useEffect(() => {
    if (!user) return;
    if (user.role !== "admin" && user.role !== "super_admin") {
      navigate("/dashboard", { replace: true });
      return;
    }
    if (user.role === "admin") { setScope("company"); setFaqScope("company"); }
    else { setScope("global"); setFaqScope("global"); }
    load();
  }, [user]);

  const addFaq = async () => {
    if (!faqQ.trim() || !faqA.trim()) { toast.error("Soru ve cevap gerekli"); return; }
    setFaqBusy(true);
    try {
      await api.post("/kb/faq", { question: faqQ.trim(), answer: faqA.trim(), scope: faqScope });
      toast.success("FAQ eklendi");
      setFaqQ(""); setFaqA("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ekleme başarısız");
    } finally { setFaqBusy(false); }
  };

  if (!user || (user.role !== "admin" && user.role !== "super_admin")) return null;

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("scope", scope);
      fd.append("title", title || file.name);
      await api.post("/kb/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Doküman yüklendi");
      setFile(null); setTitle("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Yükleme başarısız");
    } finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!confirm("Bu dokümanı silmek istediğinize emin misiniz?")) return;
    try {
      await api.delete(`/kb/${id}`);
      toast.success("Silindi");
      load();
    } catch { toast.error("Silme başarısız"); }
  };

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="kb-page">
      <header className="border-b border-zinc-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate("/dashboard")} className="text-zinc-500 hover:text-zinc-950" data-testid="kb-back-btn">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-[var(--brand-navy)] flex items-center justify-center ring-1 ring-[var(--brand-gold)]/40">
                <DatabaseZap className="w-5 h-5 text-[var(--brand-gold-2)]" />
              </div>
              <div>
                <div className="text-xs font-mono uppercase tracking-[0.28em] text-[var(--brand-gold-2)]">Bilgi Bankası</div>
                <div className="text-lg font-medium text-[var(--brand-navy)]">AI Referans Dokümanları</div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Tab bar */}
        <div className="flex gap-1 bg-zinc-100 rounded-md p-1 w-fit">
          <button
            data-testid="kb-tab-docs"
            onClick={() => setTab("docs")}
            className={`px-4 py-1.5 rounded text-sm flex items-center gap-1.5 transition-colors ${tab === "docs" ? "bg-white text-[var(--brand-navy)] shadow-sm" : "text-zinc-600"}`}
          >
            <FileText className="w-3.5 h-3.5" /> Dokümanlar
          </button>
          <button
            data-testid="kb-tab-faq"
            onClick={() => setTab("faq")}
            className={`px-4 py-1.5 rounded text-sm flex items-center gap-1.5 transition-colors ${tab === "faq" ? "bg-white text-[var(--brand-navy)] shadow-sm" : "text-zinc-600"}`}
          >
            <HelpCircle className="w-3.5 h-3.5" /> SSS (FAQ)
          </button>
        </div>

        {tab === "faq" && (
          <>
            <div className="bg-white border border-zinc-200 rounded-lg p-6">
              <h2 className="text-base font-medium text-[var(--brand-navy)] mb-2">Yeni FAQ Ekle</h2>
              <p className="text-xs text-zinc-500 mb-4">
                Şirketiniz veya tüm kullanıcılar için hızlı bir Soru-Cevap girin. AI, FAQ sohbetlerinde önce bu içerikleri kullanır.
              </p>
              <div className="space-y-3">
                <div>
                  <Label>Soru</Label>
                  <Input value={faqQ} onChange={(e) => setFaqQ(e.target.value)} placeholder="Örn: Emsal karşılaştırmasında en az kaç emsal kullanılmalı?" data-testid="faq-q-input" />
                </div>
                <div>
                  <Label>Cevap</Label>
                  <Textarea value={faqA} onChange={(e) => setFaqA(e.target.value)} rows={4} placeholder="SPK Değerleme Standartları'na göre en az 3 benzer taşınmaz kullanılır..." data-testid="faq-a-input" />
                </div>
                <div>
                  <Label>Kapsam</Label>
                  <select value={faqScope} onChange={(e) => setFaqScope(e.target.value)} className="w-full border border-zinc-300 rounded-md px-3 py-2 text-sm" data-testid="faq-scope-select">
                    {user.role === "super_admin" && <option value="global">Global (Tüm Kullanıcılar)</option>}
                    <option value="company">Şirket ({user.company_name || "kendi şirketiniz"})</option>
                  </select>
                </div>
                <div className="flex justify-end">
                  <Button onClick={addFaq} disabled={faqBusy || !faqQ.trim() || !faqA.trim()} className="bg-[var(--brand-navy)] text-white" data-testid="faq-add-btn">
                    <Plus className="w-4 h-4 mr-1" /> {faqBusy ? "Ekleniyor..." : "FAQ Ekle"}
                  </Button>
                </div>
              </div>
            </div>
            <div className="bg-white border border-zinc-200 rounded-lg overflow-hidden">
              <div className="p-4 border-b border-zinc-200">
                <h2 className="text-base font-medium text-[var(--brand-navy)]">Yüklü FAQ ({docs.filter(d => d.kind === "faq").length})</h2>
              </div>
              <div className="divide-y divide-zinc-100">
                {docs.filter(d => d.kind === "faq").map((d) => (
                  <div key={d.doc_id} className="p-4" data-testid={`faq-item-${d.doc_id}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-zinc-900">{d.question || d.title}</div>
                        <div className="text-xs text-zinc-600 mt-1 whitespace-pre-wrap">{d.answer || d.text_preview}</div>
                      </div>
                      <div className="flex-shrink-0 flex items-center gap-2">
                        {d.scope === "global" ? (
                          <Badge className="bg-[var(--brand-gold)]/20 text-[var(--brand-navy)] hover:bg-[var(--brand-gold)]/20 text-[10px]"><Globe className="w-3 h-3 mr-1" />GLOBAL</Badge>
                        ) : (
                          <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100 text-[10px]"><Building2 className="w-3 h-3 mr-1" />ŞİRKET</Badge>
                        )}
                        <button onClick={() => remove(d.doc_id)} className="text-red-600 hover:text-red-700" data-testid={`faq-delete-${d.doc_id}`}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
                {docs.filter(d => d.kind === "faq").length === 0 && (
                  <div className="p-8 text-center text-zinc-500 text-sm">Henüz FAQ eklenmemiş</div>
                )}
              </div>
            </div>
          </>
        )}

        {tab === "docs" && (
          <>
        <div className="bg-white border border-zinc-200 rounded-lg p-6">
          <h2 className="text-base font-medium text-[var(--brand-navy)] mb-2">Yeni Doküman Yükle</h2>
          <p className="text-xs text-zinc-500 mb-4">
            Yüklenen PDF/DOCX/TXT/XLSX/CSV dokümanları AI'ın hem rapor akışında hem de FAQ chat'inde referans olarak kullanacağı bilgi bankasına eklenir.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="md:col-span-2">
              <Label>Dosya (PDF · DOCX · TXT · XLSX · CSV)</Label>
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md,.csv,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-sm mt-1 file:mr-3 file:py-2 file:px-3 file:rounded file:border-0 file:bg-[var(--brand-navy)] file:text-white file:text-xs"
                data-testid="kb-file-input"
              />
            </div>
            <div>
              <Label>Kapsam</Label>
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                className="w-full border border-zinc-300 rounded-md px-3 py-2 text-sm mt-1"
                data-testid="kb-scope-select"
              >
                {user.role === "super_admin" && <option value="global">Global (Tüm Kullanıcılar)</option>}
                <option value="company">Şirket ({user.company_name || "kendi şirketiniz"})</option>
              </select>
            </div>
            <div className="md:col-span-3">
              <Label>Başlık (opsiyonel)</Label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="ör. SPK Değerleme Standartları 2025"
                data-testid="kb-title-input"
              />
            </div>
          </div>
          <div className="flex justify-end mt-4">
            <Button
              onClick={upload}
              disabled={!file || busy}
              className="bg-[var(--brand-navy)] text-white"
              data-testid="kb-upload-btn"
            >
              <Upload className="w-4 h-4 mr-1" />
              {busy ? "Yükleniyor..." : "Yükle"}
            </Button>
          </div>
        </div>

        <div className="bg-white border border-zinc-200 rounded-lg overflow-hidden">
          <div className="p-4 border-b border-zinc-200">
            <h2 className="text-base font-medium text-[var(--brand-navy)]">Yüklü Dokümanlar</h2>
            <p className="text-xs text-zinc-500">{docs.length} doküman</p>
          </div>
          <div className="divide-y divide-zinc-100">
            {docs.filter(d => d.kind !== "faq").map((d) => (
              <div key={d.doc_id} className="flex items-center gap-3 p-4" data-testid={`kb-doc-${d.doc_id}`}>
                <FileText className="w-5 h-5 text-zinc-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-zinc-900 truncate">{d.title}</div>
                  <div className="text-xs text-zinc-500 truncate">{d.filename}</div>
                </div>
                <div className="flex-shrink-0 flex items-center gap-2">
                  {d.scope === "global" ? (
                    <Badge className="bg-[var(--brand-gold)]/20 text-[var(--brand-navy)] hover:bg-[var(--brand-gold)]/20 text-[10px]">
                      <Globe className="w-3 h-3 mr-1" /> GLOBAL
                    </Badge>
                  ) : (
                    <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100 text-[10px]">
                      <Building2 className="w-3 h-3 mr-1" /> ŞİRKET
                    </Badge>
                  )}
                  <div className="text-xs text-zinc-500 hidden md:block">{Math.round((d.size || 0) / 1024)} KB</div>
                  <button
                    onClick={() => remove(d.doc_id)}
                    className="text-red-600 hover:text-red-700"
                    data-testid={`kb-delete-${d.doc_id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
            {docs.filter(d => d.kind !== "faq").length === 0 && (
              <div className="p-8 text-center text-zinc-500 text-sm">Henüz doküman yok</div>
            )}
          </div>
        </div>
          </>
        )}
      </main>
    </div>
  );
}
