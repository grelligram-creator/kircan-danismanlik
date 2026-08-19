import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, Upload, FileText, Trash2, Edit3, Loader2, Plus, X, Sparkles, Share2, Users, History } from "lucide-react";
import { toast } from "sonner";

const FIELD_TYPES = [
  { value: "text", label: "Metin" },
  { value: "textarea", label: "Uzun Metin" },
  { value: "number", label: "Sayı" },
  { value: "date", label: "Tarih" },
  { value: "image", label: "Görsel" },
];

export default function TemplateManager() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState(null);
  const [sharing, setSharing] = useState(null);
  const [versioning, setVersioning] = useState(null);
  const fileRef = useRef(null);
  const [meta, setMeta] = useState({ name: "", description: "" });
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/user_templates");
      setItems(data.templates);
    } catch {
      toast.error("Şablonlar yüklenemedi");
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".docx")) {
      toast.error("Sadece .docx desteklenir");
      return;
    }
    if (!meta.name.trim()) {
      toast.error("Önce şablona bir ad verin");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    form.append("name", meta.name);
    form.append("description", meta.description);
    try {
      const { data } = await api.post("/user_templates/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
      });
      toast.success(`${data.template.fields.length} alan tespit edildi`, {
        description: "Alanları gözden geçirmek için 'Düzenle'ye tıklayın.",
      });
      setMeta({ name: "", description: "" });
      if (fileRef.current) fileRef.current.value = "";
      await load();
      setEditing(data.template);
    } catch (e) {
      toast.error("Yükleme başarısız", { description: e?.response?.data?.detail || "" });
    } finally {
      setUploading(false);
    }
  };

  const remove = async (tid) => {
    if (!confirm("Bu şablonu silmek istediğinize emin misiniz?")) return;
    try {
      await api.delete(`/user_templates/${tid}`);
      toast.success("Şablon silindi");
      load();
    } catch {
      toast.error("Silinemedi");
    }
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-zinc-50">
        <div className="text-zinc-500 text-sm font-mono uppercase tracking-widest">Yükleniyor...</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-zinc-50 font-body" data-testid="templates-page">
      {/* Header */}
      <div className="border-b border-zinc-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/dashboard")}
              className="text-zinc-600 hover:text-zinc-950"
              data-testid="back-btn"
            >
              <ArrowLeft className="w-4 h-4 mr-1.5" /> Panel
            </Button>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500">Kütüphane</div>
              <h1 className="text-xl tracking-tight font-medium text-zinc-950">Word Şablonları</h1>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {/* Upload */}
        <section className="bg-white border border-zinc-200 rounded-md p-6" data-testid="upload-panel">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-1">
            Yeni Şablon
          </div>
          <h2 className="text-lg font-medium tracking-tight text-zinc-950 mb-4">
            Word (.docx) yükleyin, boşlukları AI tespit etsin
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <Input
              placeholder="Şablon adı (örn: SPK Konut Değerleme)"
              value={meta.name}
              onChange={(e) => setMeta((m) => ({ ...m, name: e.target.value }))}
              data-testid="template-name-input"
            />
            <Input
              placeholder="Kısa açıklama (isteğe bağlı)"
              value={meta.description}
              onChange={(e) => setMeta((m) => ({ ...m, description: e.target.value }))}
              data-testid="template-desc-input"
            />
          </div>
          <div className="flex items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={handleUpload}
              data-testid="template-file-input"
            />
            <Button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="bg-zinc-950 text-white hover:bg-zinc-800"
              data-testid="upload-template-btn"
            >
              {uploading ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> AI Analiz Ediyor...</>
              ) : (
                <><Upload className="w-4 h-4 mr-2" /> .docx Seç</>
              )}
            </Button>
            <div className="text-xs text-zinc-500">
              <Sparkles className="w-3 h-3 inline mr-1 text-amber-500" />
              Claude Sonnet 5 dokümanınızı analiz eder, boş yerleri, tablo hücrelerini ve fotoğraf slotlarını çıkarır.
            </div>
          </div>
        </section>

        {/* List */}
        <section>
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-3">Yüklenen Şablonlar</div>
          {items.length === 0 ? (
            <div className="bg-white border border-dashed border-zinc-300 rounded-md p-10 text-center text-sm text-zinc-500">
              Henüz şablon yüklenmemiş. İlk .docx'inizi yükleyerek başlayın.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="template-list">
              {items.map((t) => (
                <div key={t.template_id} className="bg-white border border-zinc-200 rounded-md p-5" data-testid={`tpl-card-${t.template_id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="w-8 h-8 rounded-md bg-zinc-100 text-zinc-700 flex items-center justify-center mb-3">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div className="font-medium text-zinc-950 mb-0.5 flex items-center gap-2">
                        {t.name}
                        {t.is_shared_with_me && (
                          <span className="text-[10px] font-mono uppercase tracking-widest text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded inline-flex items-center gap-1">
                            <Users className="w-2.5 h-2.5" /> Paylaşılan
                          </span>
                        )}
                        {(t.shared_with?.length || 0) > 0 && !t.is_shared_with_me && (
                          <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded inline-flex items-center gap-1">
                            <Users className="w-2.5 h-2.5" /> {t.shared_with.length}
                          </span>
                        )}
                      </div>
                      {t.description && <div className="text-xs text-zinc-500 mb-2">{t.description}</div>}
                      <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                        {t.fields?.length || 0} alan · {t.filename}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      {!t.is_shared_with_me && (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => setSharing(t)} data-testid={`share-${t.template_id}`} title="Paylaş">
                            <Share2 className="w-3.5 h-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setVersioning(t)} data-testid={`versions-${t.template_id}`} title="Sürümler">
                            <History className="w-3.5 h-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditing(t)} data-testid={`edit-${t.template_id}`}>
                            <Edit3 className="w-3.5 h-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => remove(t.template_id)} className="text-red-600 hover:text-red-700 hover:bg-red-50" data-testid={`del-${t.template_id}`}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {editing && (
        <FieldEditorDialog
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
      {sharing && (
        <ShareDialog template={sharing} onClose={() => setSharing(null)} onSaved={() => { setSharing(null); load(); }} />
      )}
      {versioning && (
        <VersionsDialog template={versioning} onClose={() => setVersioning(null)} onRestored={() => { setVersioning(null); load(); }} />
      )}
    </div>
  );
}

function VersionsDialog({ template, onClose, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(null);

  useEffect(() => {
    api.get(`/user_templates/${template.template_id}/versions`)
      .then((r) => setVersions(r.data.versions))
      .catch(() => toast.error("Sürümler yüklenemedi"))
      .finally(() => setLoading(false));
  }, [template.template_id]);

  const restore = async (vid) => {
    if (!confirm("Bu sürüme geri dönmek istediğinize emin misiniz? Mevcut durum otomatik olarak yedeklenecek.")) return;
    setRestoring(vid);
    try {
      await api.post(`/user_templates/${template.template_id}/versions/${vid}/restore`);
      toast.success("Sürüm geri yüklendi");
      onRestored();
    } catch {
      toast.error("Geri yükleme başarısız");
    } finally { setRestoring(null); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl bg-white" data-testid="versions-dialog">
        <DialogHeader>
          <div className="flex items-center gap-2 text-zinc-500 mb-1">
            <History className="w-4 h-4" />
            <span className="text-[10px] font-mono uppercase tracking-[0.25em]">Sürüm Geçmişi</span>
          </div>
          <DialogTitle className="text-2xl tracking-tight font-light">{template.name}</DialogTitle>
          <DialogDescription>Her düzenleme veya alan güncellemesinde otomatik bir sürüm kaydedilir. İstediğiniz sürüme geri dönebilirsiniz.</DialogDescription>
        </DialogHeader>
        <div className="max-h-96 overflow-y-auto space-y-2">
          {loading && <div className="text-sm text-zinc-500 italic py-4 text-center">Yükleniyor...</div>}
          {!loading && versions.length === 0 && (
            <div className="text-sm text-zinc-500 italic py-4 text-center">Henüz sürüm yok. Alan editöründe bir değişiklik yaptığınızda ilk sürüm oluşacak.</div>
          )}
          {versions.map((v) => (
            <div key={v.version_id} className="flex items-center justify-between p-3 border border-zinc-200 rounded-md" data-testid={`version-${v.version_id}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-950 truncate">
                  {v.name || template.name}
                  {v.note && <span className="ml-2 text-[10px] font-mono uppercase tracking-widest text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">Otomatik</span>}
                </div>
                <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                  {new Date(v.created_at).toLocaleString("tr-TR")} · {v.fields?.length || 0} alan · {v.version_id}
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={restoring === v.version_id}
                onClick={() => restore(v.version_id)}
                data-testid={`restore-${v.version_id}`}
              >
                {restoring === v.version_id ? "Geri yükleniyor..." : "Geri Yükle"}
              </Button>
            </div>
          ))}
        </div>
        <div className="flex justify-end pt-4 border-t border-zinc-200">
          <Button variant="outline" onClick={onClose}>Kapat</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ShareDialog({ template, onClose, onSaved }) {
  const [emails, setEmails] = useState(template.shared_with || []);
  const [newEmail, setNewEmail] = useState("");
  const [saving, setSaving] = useState(false);

  const add = () => {
    const e = newEmail.trim().toLowerCase();
    if (!e || !/^\S+@\S+\.\S+$/.test(e)) {
      toast.error("Geçerli bir e-posta girin");
      return;
    }
    if (emails.map((x) => x.toLowerCase()).includes(e)) return;
    setEmails([...emails, e]);
    setNewEmail("");
  };

  const remove = (email) => setEmails(emails.filter((e) => e !== email));

  const save = async () => {
    setSaving(true);
    try {
      const currentSet = new Set((template.shared_with || []).map((e) => e.toLowerCase()));
      const newSet = new Set(emails.map((e) => e.toLowerCase()));
      const add_list = [...newSet].filter((e) => !currentSet.has(e));
      const remove_list = [...currentSet].filter((e) => !newSet.has(e));
      await api.post(`/user_templates/${template.template_id}/share`, { add: add_list, remove: remove_list });
      toast.success("Paylaşım güncellendi");
      onSaved();
    } catch {
      toast.error("Paylaşım kaydedilemedi");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg bg-white" data-testid="share-dialog">
        <DialogHeader>
          <div className="flex items-center gap-2 text-zinc-500 mb-1">
            <Users className="w-4 h-4" />
            <span className="text-[10px] font-mono uppercase tracking-[0.25em]">Ekip Paylaşımı</span>
          </div>
          <DialogTitle className="text-2xl tracking-tight font-light">{template.name}</DialogTitle>
          <DialogDescription>Şablona erişebilecek ekip üyelerinin e-posta adreslerini ekleyin. Onlar da kendi paketlerinde bu şablonu görecek ve kullanabilecek.</DialogDescription>
        </DialogHeader>
        <div className="flex gap-2">
          <Input placeholder="ekip.uyesi@sirket.com" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} data-testid="share-email-input" />
          <Button onClick={add} variant="outline">Ekle</Button>
        </div>
        <div className="mt-2 min-h-[60px] flex flex-wrap gap-1.5">
          {emails.length === 0 && <div className="text-xs text-zinc-500 italic">Kimseyle paylaşılmadı.</div>}
          {emails.map((e) => (
            <span key={e} className="inline-flex items-center gap-1.5 text-xs bg-zinc-100 rounded px-2 py-1">
              {e}
              <button onClick={() => remove(e)} className="text-zinc-500 hover:text-red-600"><X className="w-3 h-3" /></button>
            </span>
          ))}
        </div>
        <div className="flex justify-end gap-2 pt-4 border-t border-zinc-200">
          <Button variant="outline" onClick={onClose}>Vazgeç</Button>
          <Button onClick={save} disabled={saving} className="bg-zinc-950 text-white hover:bg-zinc-800" data-testid="save-share-btn">
            {saving ? "Kaydediliyor..." : "Kaydet"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function FieldEditorDialog({ template, onClose, onSaved }) {
  const [fields, setFields] = useState(template.fields || []);
  const [saving, setSaving] = useState(false);

  const updateField = (idx, patch) => {
    setFields((prev) => prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  };
  const removeField = (idx) => setFields((prev) => prev.filter((_, i) => i !== idx));
  const addField = () => setFields((prev) => [
    ...prev,
    { key: `alan_${prev.length + 1}`, label: "Yeni Alan", type: "text", node_id: null, replace_text: null, append_after_label: null, hint: "" },
  ]);
  const moveUp = (idx) => {
    if (idx === 0) return;
    setFields((prev) => {
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/user_templates/${template.template_id}`, { fields });
      toast.success("Şablon güncellendi");
      onSaved();
    } catch (e) {
      toast.error("Kaydedilemedi", { description: e?.response?.data?.detail || "" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col bg-white" data-testid="field-editor">
        <DialogHeader>
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-1">Alan Editörü</div>
          <DialogTitle className="text-2xl tracking-tight font-light">{template.name}</DialogTitle>
          <DialogDescription>
            AI tespitini gözden geçirin. Alan adları (key) DOCX içindeki `{"{{ }}"}` etiketleriyle eşleşir, bu yüzden dikkatli değiştirin.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-2 pr-2">
          {fields.map((f, idx) => (
            <div key={idx} className="border border-zinc-200 rounded-md p-3 bg-zinc-50" data-testid={`field-row-${idx}`}>
              <div className="grid grid-cols-12 gap-2 items-start">
                <div className="col-span-3">
                  <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Anahtar</label>
                  <Input value={f.key} onChange={(e) => updateField(idx, { key: e.target.value.replace(/[^a-z0-9_]/g, "_") })} className="mt-1 font-mono text-xs" />
                </div>
                <div className="col-span-4">
                  <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Etiket</label>
                  <Input value={f.label} onChange={(e) => updateField(idx, { label: e.target.value })} className="mt-1" />
                </div>
                <div className="col-span-2">
                  <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Tip</label>
                  <Select value={f.type} onValueChange={(v) => updateField(idx, { type: v })}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {FIELD_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-2">
                  <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Değişecek Metin</label>
                  <Input value={f.replace_text || ""} onChange={(e) => updateField(idx, { replace_text: e.target.value || null })} className="mt-1 text-xs font-mono" placeholder="____" />
                </div>
                <div className="col-span-1 flex flex-col gap-1 mt-4">
                  <button onClick={() => moveUp(idx)} disabled={idx === 0} className="text-zinc-500 hover:text-zinc-950 disabled:opacity-30" title="Yukarı taşı">↑</button>
                  <button onClick={() => removeField(idx)} className="text-red-500 hover:text-red-700" title="Sil"><X className="w-3.5 h-3.5" /></button>
                </div>
                <div className="col-span-12">
                  <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">İpucu (AI kullanıcıya sorarken)</label>
                  <Textarea value={f.hint || ""} onChange={(e) => updateField(idx, { hint: e.target.value })} className="mt-1 min-h-[40px] text-sm" rows={1} />
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-zinc-200 mt-2">
          <Button variant="outline" size="sm" onClick={addField}>
            <Plus className="w-3.5 h-3.5 mr-1.5" /> Alan Ekle
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Vazgeç</Button>
            <Button onClick={save} disabled={saving} className="bg-zinc-950 text-white hover:bg-zinc-800" data-testid="save-fields-btn">
              {saving ? "Kaydediliyor..." : "Kaydet ve Yeniden Hazırla"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
