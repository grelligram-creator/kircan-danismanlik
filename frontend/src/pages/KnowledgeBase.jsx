import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ArrowLeft, Upload, FileText, Trash2, Globe, Building2, DatabaseZap } from "lucide-react";

export default function KnowledgeBase() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [docs, setDocs] = useState([]);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [scope, setScope] = useState("company");
  const [busy, setBusy] = useState(false);

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
    if (user.role === "admin") setScope("company");
    else setScope("global");
    load();
  }, [user]);

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
            {docs.map((d) => (
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
            {docs.length === 0 && (
              <div className="p-8 text-center text-zinc-500 text-sm">Henüz doküman yok</div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
