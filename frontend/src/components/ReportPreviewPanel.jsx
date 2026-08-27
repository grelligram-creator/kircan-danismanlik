import { Button } from "@/components/ui/button";
import { Download, Mail, FileText, CheckCircle2, Loader2, Upload, Table as TableIcon, Plus, X, Wand2, AlertTriangle } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { useState, useEffect, useRef, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

export default function ReportPreviewPanel({ chat }) {
  const [emailing, setEmailing] = useState(false);
  const [customPreview, setCustomPreview] = useState(null); // {html, fields}
  const [previewError, setPreviewError] = useState(null);
  const [uploadingImageKey, setUploadingImageKey] = useState(null);
  const [grammarLoading, setGrammarLoading] = useState(false);
  const [grammarResult, setGrammarResult] = useState(null);
  const [appliedIdx, setAppliedIdx] = useState(new Set());
  const [applyingIdx, setApplyingIdx] = useState(null);
  const fileRef = useRef(null);
  const pendingKeyRef = useRef(null);
  const previewReqRef = useRef(0);

  const runGrammarCheck = async () => {
    if (!chat?.chat_id) return;
    setGrammarLoading(true);
    try {
      const { data } = await api.post(`/chats/${chat.chat_id}/grammar-check`);
      setGrammarResult(data);
      if ((data.suggestions || []).length === 0) {
        toast.success("Rapor metinlerinde imla/anlatım hatası bulunamadı");
      }
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (typeof detail === "object" && detail?.error === "insufficient_balance") {
        toast.error(`Yetersiz bakiye — gerekli: ₺${detail.required}`);
      } else {
        toast.error(typeof detail === "string" ? detail : "Kontrol başarısız");
      }
    } finally {
      setGrammarLoading(false);
    }
  };

  const applySuggestion = async (idx, s) => {
    if (!chat?.chat_id || !s?.field || !s?.corrected) return;
    setApplyingIdx(idx);
    try {
      await api.patch(`/chats/${chat.chat_id}/fields`, { fields: { [s.field]: s.corrected } });
      setAppliedIdx((prev) => { const n = new Set(prev); n.add(idx); return n; });
      loadCustomPreview();
      toast.success("Alan güncellendi");
    } catch {
      toast.error("Uygulanamadı");
    } finally {
      setApplyingIdx(null);
    }
  };

  const applyAllSuggestions = async () => {
    if (!grammarResult?.suggestions?.length) return;
    const merged = {};
    (grammarResult.suggestions || []).forEach((s, i) => {
      if (!appliedIdx.has(i) && s.field && s.corrected) merged[s.field] = s.corrected;
    });
    if (!Object.keys(merged).length) return;
    try {
      await api.patch(`/chats/${chat.chat_id}/fields`, { fields: merged });
      const all = new Set(appliedIdx);
      (grammarResult.suggestions || []).forEach((s, i) => { if (s.field && s.corrected) all.add(i); });
      setAppliedIdx(all);
      loadCustomPreview();
      toast.success(`${Object.keys(merged).length} öneri uygulandı`);
    } catch {
      toast.error("Uygulanamadı");
    }
  };

  const loadCustomPreview = useCallback(async () => {
    if (!chat?.user_template_id) return;
    const reqId = ++previewReqRef.current;
    try {
      const { data } = await api.get(`/user_templates/${chat.user_template_id}/preview`, {
        params: { chat_id: chat.chat_id },
        timeout: 20000,
      });
      // Guard: ignore stale responses (only apply if this is the newest in-flight request)
      if (reqId !== previewReqRef.current) return;
      setCustomPreview(data);
      setPreviewError(null);
    } catch (e) {
      if (reqId !== previewReqRef.current) return;
      setPreviewError(e?.response?.data?.detail || "Şablon önizlemesi yüklenemedi");
    }
  }, [chat?.user_template_id, chat?.chat_id, chat?.fields]);

  // Debounce preview reloads by 300ms — avoids one fetch per keystroke.
  useEffect(() => {
    if (!chat?.user_template_id) return;
    const t = setTimeout(() => { loadCustomPreview(); }, 300);
    return () => clearTimeout(t);
  }, [loadCustomPreview, chat?.user_template_id]);

  const download = (fmt) => {
    const url = `${API}/chats/${chat.chat_id}/download/${fmt}`;
    window.open(url, "_blank");
  };

  const sendEmail = async () => {
    setEmailing(true);
    try {
      const { data } = await api.post(`/chats/${chat.chat_id}/email`);
      toast.success(`Rapor e-posta ile gönderildi (MOCK)`, { description: `Alıcı: ${data.sent_to}` });
    } catch {
      toast.error("E-posta gönderilemedi");
    } finally {
      setEmailing(false);
    }
  };

  const startImageUpload = (fieldKey) => {
    pendingKeyRef.current = fieldKey;
    fileRef.current?.click();
  };

  const handleImageFile = async (e) => {
    const file = e.target.files?.[0];
    const key = pendingKeyRef.current;
    if (fileRef.current) fileRef.current.value = "";
    if (!file || !key) return;
    setUploadingImageKey(key);
    const form = new FormData();
    form.append("field_key", key);
    form.append("file", file);
    try {
      await api.post(`/chats/${chat.chat_id}/image`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Görsel yüklendi: ${key}`);
      await loadCustomPreview();
    } catch {
      toast.error("Görsel yüklenemedi");
    } finally {
      setUploadingImageKey(null);
      pendingKeyRef.current = null;
    }
  };

  const resizeImage = async (fieldKey, width_mm) => {
    try {
      await api.patch(`/chats/${chat.chat_id}/image/${fieldKey}`, { width_mm });
      await loadCustomPreview();
    } catch {
      toast.error("Yeniden boyutlandırma başarısız");
    }
  };

  if (!chat || chat.mode === "faq") {
    return (
      <div className="h-full flex items-center justify-center bg-zinc-100/50 p-8">
        <div className="text-center max-w-sm">
          <div className="w-14 h-14 mx-auto rounded-md bg-white border border-zinc-200 flex items-center justify-center mb-4">
            <FileText className="w-6 h-6 text-zinc-400" />
          </div>
          <div className="text-xs font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">Önizleme</div>
          <div className="text-lg font-light text-zinc-700">
            FAQ modunda rapor önizlemesi bulunmaz. Rapor oluşturmak için yeni bir sohbet başlatın.
          </div>
        </div>
      </div>
    );
  }

  const template = chat.template_name || "Değerleme Raporu";
  const completed = chat.status === "completed";
  const isUserTpl = !!chat.user_template_id;

  const fieldsList = Object.entries(chat.fields || {})
    .filter(([, v]) => !(v && typeof v === "object" && v.__image__));
  const sectionsList = Object.entries(chat.sections || {});
  const imageFields = isUserTpl
    ? (customPreview?.fields || []).filter((f) => f.type === "image")
    : [];
  const tableFields = isUserTpl
    ? (customPreview?.fields || []).filter((f) => f.type === "table")
    : [];
  const hasContent = fieldsList.length > 0 || sectionsList.length > 0 || (isUserTpl && !!customPreview);

  return (
    <div className="h-full flex flex-col bg-zinc-100/50" data-testid="preview-panel">
      {/* Sticky header */}
      <div className="border-b border-zinc-200 bg-white px-6 py-4 flex items-center justify-between flex-shrink-0">
        <div className="min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 truncate">
            Rapor Önizleme · {chat.report_no || "-"}
          </div>
          <div className="text-sm font-medium text-zinc-900 mt-0.5 flex items-center gap-2 truncate">
            {template}
            {completed && (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                <CheckCircle2 className="w-3 h-3" /> Tamamlandı
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {!isUserTpl && (
            <Button data-testid="download-pdf-btn" variant="outline" size="sm" onClick={() => download("pdf")} disabled={!hasContent}>
              <Download className="w-3.5 h-3.5 mr-1.5" /> PDF
            </Button>
          )}
          <Button data-testid="download-docx-btn" variant="outline" size="sm" onClick={() => download("docx")} disabled={!hasContent}>
            <Download className="w-3.5 h-3.5 mr-1.5" /> DOCX
          </Button>
          <Button data-testid="download-udf-btn" variant="outline" size="sm" onClick={() => download("udf")} disabled={!hasContent} title="UYAP UDF formatı — mahkeme başvuruları için">
            <Download className="w-3.5 h-3.5 mr-1.5" /> UDF
          </Button>
          <Button data-testid="grammar-check-btn" variant="outline" size="sm" onClick={runGrammarCheck} disabled={!hasContent || grammarLoading} title="Rapor metinlerini yazım/anlatım açısından kontrol et">
            {grammarLoading ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5 mr-1.5" />}
            İmla
          </Button>
          <Button data-testid="email-report-btn" size="sm" className="bg-zinc-950 text-white hover:bg-zinc-800" onClick={sendEmail} disabled={!hasContent || emailing}>
            {emailing ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Mail className="w-3.5 h-3.5 mr-1.5" />}
            E-posta
          </Button>
        </div>
      </div>

      {/* Hidden file input for image uploads */}
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImageFile} data-testid="image-upload-input" />

      {/* Image slot bar (for user templates only) */}
      {isUserTpl && (imageFields.length > 0 || tableFields.length > 0) && (
        <div className="border-b border-zinc-200 bg-white px-6 py-3 flex items-center gap-2 flex-wrap" data-testid="image-slot-bar">
          {imageFields.length > 0 && (
            <>
              <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mr-1">Görseller:</span>
              {imageFields.map((f) => (
                <ImageSlotChip
                  key={f.key}
                  field={f}
                  chatId={chat.chat_id}
                  value={chat.fields?.[f.key]}
                  onUpload={() => startImageUpload(f.key)}
                  onResize={(w) => resizeImage(f.key, w)}
                  onCropped={loadCustomPreview}
                  uploading={uploadingImageKey === f.key}
                />
              ))}
            </>
          )}
          {tableFields.length > 0 && (
            <>
              <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 ml-3 mr-1">Tablolar:</span>
              {tableFields.map((f) => (
                <TableFieldChip
                  key={f.key}
                  field={f}
                  rows={chat.fields?.[f.key] || []}
                  chatId={chat.chat_id}
                  onSaved={loadCustomPreview}
                />
              ))}
            </>
          )}
        </div>
      )}

      {/* Paper */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto bg-white shadow-sm ring-1 ring-zinc-200 min-h-full">
          {isUserTpl ? (
            customPreview ? (
              <div
                className="doc-preview p-10"
                dangerouslySetInnerHTML={{ __html: customPreview.html }}
                data-testid="custom-preview-html"
              />
            ) : (
              <div className="p-10 text-zinc-400 text-sm">
                {previewError ? (
                  <div className="text-center space-y-3">
                    <div className="text-red-600 text-xs">{previewError}</div>
                    <button
                      onClick={loadCustomPreview}
                      className="text-xs text-[var(--brand-navy)] hover:underline"
                      data-testid="preview-retry-btn"
                    >
                      Tekrar dene
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Şablon yükleniyor...</span>
                  </div>
                )}
              </div>
            )
          ) : (
            <BuiltinPreview chat={chat} fieldsList={fieldsList} sectionsList={sectionsList} template={template} />
          )}
        </div>
      </div>

      {/* Grammar check result dialog — belongs to ReportPreviewPanel so grammarResult/setGrammarResult are in scope */}
      <Dialog open={!!grammarResult} onOpenChange={(v) => { if (!v) setGrammarResult(null); }}>
        <DialogContent className="max-w-2xl" data-testid="grammar-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wand2 className="w-4 h-4 text-[var(--brand-gold-2)]" />
              İmla ve Anlatım Önerileri
            </DialogTitle>
          </DialogHeader>
          {grammarResult && (
            <div className="space-y-3 max-h-[500px] overflow-y-auto">
              <div className="text-xs text-zinc-500 border-b border-zinc-100 pb-2 font-mono">
                {(grammarResult.suggestions || []).length} öneri · Maliyet: ₺{grammarResult.cost_try} · {grammarResult.tokens?.input || 0} in / {grammarResult.tokens?.output || 0} out
              </div>
              {(grammarResult.suggestions || []).length === 0 ? (
                <div className="text-center text-zinc-500 py-6 flex flex-col items-center gap-2">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500" />
                  Raporda imla veya anlatım hatası bulunamadı
                </div>
              ) : (
                (grammarResult.suggestions || []).map((s, i) => {
                  const applied = appliedIdx.has(i);
                  const applying = applyingIdx === i;
                  return (
                    <div key={i} className={`border rounded-md p-3 space-y-2 ${applied ? "border-emerald-300 bg-emerald-50/40" : "border-zinc-200"}`} data-testid={`grammar-item-${i}`}>
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-mono uppercase text-zinc-500">{s.field}</div>
                        {applied ? (
                          <div className="flex items-center gap-1 text-emerald-700 text-xs font-medium">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Uygulandı
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => applySuggestion(i, s)}
                            disabled={applying || !s.corrected}
                            data-testid={`grammar-apply-${i}`}
                            className="h-7 text-xs"
                          >
                            {applying ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                            Uygula
                          </Button>
                        )}
                      </div>
                      <div className="text-xs bg-red-50 border-l-2 border-red-300 p-2 whitespace-pre-wrap"><b>Mevcut:</b> {s.original}</div>
                      <div className="text-xs bg-emerald-50 border-l-2 border-emerald-400 p-2 whitespace-pre-wrap"><b>Öneri:</b> {s.corrected}</div>
                      {s.reason && <div className="text-xs text-zinc-500 italic flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5" />{s.reason}</div>}
                    </div>
                  );
                })
              )}
            </div>
          )}
          <DialogFooter>
            {(grammarResult?.suggestions?.length || 0) > 0 && (
              <Button
                variant="outline"
                onClick={applyAllSuggestions}
                data-testid="grammar-apply-all-btn"
                disabled={(grammarResult?.suggestions || []).every((_, i) => appliedIdx.has(i))}
              >
                Tümünü Uygula
              </Button>
            )}
            <Button onClick={() => { setGrammarResult(null); setAppliedIdx(new Set()); }} className="bg-[var(--brand-navy)] text-white">Kapat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ImageSlotChip({ field, chatId, value, onUpload, onResize, onCropped, uploading }) {
  const filled = value?.__image__;
  const [open, setOpen] = useState(false);
  const [width, setWidth] = useState(value?.width_mm || 80);
  const [cropping, setCropping] = useState(false);
  useEffect(() => { if (value?.width_mm) setWidth(value.width_mm); }, [value?.width_mm]);

  const applyAspect = async (ar) => {
    setCropping(true);
    try {
      await api.patch(`/chats/${chatId}/image/${field.key}`, { aspect_ratio: ar });
      toast.success(`Kırpma uygulandı: ${ar}`);
      onCropped?.();
    } catch (e) {
      toast.error("Kırpma başarısız", { description: e?.response?.data?.detail || "" });
    } finally { setCropping(false); }
  };

  return (
    <div className="relative inline-block">
      <button
        onClick={() => (filled ? setOpen((o) => !o) : onUpload())}
        disabled={uploading}
        data-testid={`img-slot-${field.key}`}
        className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border transition-colors ${
          filled
            ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
            : "border-zinc-300 bg-white text-zinc-700 hover:border-zinc-950"
        }`}
      >
        {uploading ? <Loader2 className="w-3 h-3 animate-spin" /> : filled ? <CheckCircle2 className="w-3 h-3" /> : <Upload className="w-3 h-3" />}
        {field.label}
        {filled && <span className="text-[10px] font-mono text-emerald-700">·{Math.round(width)}mm</span>}
      </button>
      {open && filled && (
        <div className="absolute z-20 top-full mt-1 left-0 bg-white border border-zinc-200 rounded-md shadow-lg p-3 w-72" data-testid={`img-resize-${field.key}`}>
          <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">Boyut · {Math.round(width)}mm</div>
          <Slider min={30} max={170} step={5} value={[width]} onValueChange={(v) => setWidth(v[0])} onValueCommit={(v) => onResize(v[0])} />
          <div className="flex justify-between text-[10px] font-mono text-zinc-400 mt-1">
            <span>30mm</span><span>170mm</span>
          </div>

          <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mt-3 mb-1.5">Otomatik Kırpma</div>
          <div className="grid grid-cols-5 gap-1" data-testid={`img-crop-${field.key}`}>
            {[
              { id: "original", label: "Orj." },
              { id: "16:9", label: "16:9" },
              { id: "4:3", label: "4:3" },
              { id: "1:1", label: "1:1" },
              { id: "3:4", label: "3:4" },
            ].map((a) => (
              <button
                key={a.id}
                onClick={() => applyAspect(a.id)}
                disabled={cropping}
                data-testid={`crop-${field.key}-${a.id}`}
                className="text-[10px] font-mono border border-zinc-200 rounded px-1.5 py-1 hover:border-zinc-950 hover:bg-zinc-50 transition-colors disabled:opacity-40"
              >
                {a.label}
              </button>
            ))}
          </div>

          <div className="flex gap-2 mt-3 pt-2 border-t border-zinc-200">
            <Button size="sm" variant="outline" className="flex-1" onClick={onUpload}>Değiştir</Button>
            <Button size="sm" variant="ghost" className="text-zinc-500" onClick={() => setOpen(false)}>Kapat</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function TableFieldChip({ field, rows, chatId, onSaved }) {
  const [open, setOpen] = useState(false);
  const [localRows, setLocalRows] = useState(rows);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setLocalRows(rows); }, [rows]);

  const cols = field.columns || [];
  const [colWidths, setColWidths] = useState({});
  useEffect(() => {
    // Load column widths from special __widths__ row if present
    const meta = (rows || []).find((r) => r && r.__widths__);
    setColWidths(meta?.__widths__ || {});
  }, [rows]);

  const addRow = () => setLocalRows((prev) => [...prev, Object.fromEntries(cols.map((c) => [c.key, ""]))]);
  // Data-index-aware operations (skip __widths__ meta rows)
  const _realIdx = (dataIdx) => {
    let seen = -1;
    for (let idx = 0; idx < localRows.length; idx++) {
      if (localRows[idx]?.__widths__) continue;
      seen += 1;
      if (seen === dataIdx) return idx;
    }
    return -1;
  };
  const removeRow = (dataIdx) => {
    const real = _realIdx(dataIdx);
    setLocalRows((prev) => prev.filter((_, idx) => idx !== real));
  };
  const updateCell = (dataIdx, k, v) => {
    const real = _realIdx(dataIdx);
    setLocalRows((prev) => prev.map((r, idx) => (idx === real ? { ...r, [k]: v } : r)));
  };

  const save = async () => {
    setSaving(true);
    try {
      // Persist column widths as a hidden meta row (backend ignores rows with __widths__ during Jinja loop rendering)
      const cleanRows = localRows.filter((r) => !r?.__widths__);
      const hasWidths = Object.values(colWidths || {}).some((v) => v !== "" && v != null);
      const rowsToSave = hasWidths ? [{ __widths__: colWidths }, ...cleanRows] : cleanRows;
      await api.patch(`/chats/${chatId}/table/${field.key}`, { rows: rowsToSave });
      toast.success(`${cleanRows.length} satır kaydedildi`);
      await onSaved();
      setOpen(false);
    } catch {
      toast.error("Kaydedilemedi");
    } finally { setSaving(false); }
  };

  const filled = rows.length > 0;
  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen((o) => !o)}
        data-testid={`table-slot-${field.key}`}
        className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border transition-colors ${
          filled ? "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100" : "border-zinc-300 bg-white text-zinc-700 hover:border-zinc-950"
        }`}
      >
        <TableIcon className="w-3 h-3" />
        {field.label} <span className="font-mono text-[10px] text-zinc-500">· {rows.length} satır</span>
      </button>
      {open && (
        <div className="absolute z-20 top-full mt-1 left-0 bg-white border border-zinc-200 rounded-md shadow-lg p-3 w-[640px] max-w-[90vw]" data-testid={`table-editor-${field.key}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">{field.label} — {cols.length} sütun</div>
          </div>
          {/* Column widths row (mm) */}
          <div className="flex items-center gap-1.5 mb-1.5">
            <div className="w-8 text-[10px] font-mono text-zinc-400 uppercase">Gnşl</div>
            {cols.map((c) => (
              <Input
                key={c.key}
                type="number"
                placeholder="mm"
                min="10" max="200" step="5"
                value={colWidths[c.key] ?? ""}
                onChange={(e) => setColWidths((prev) => ({ ...prev, [c.key]: e.target.value }))}
                className="text-[10px] h-7 font-mono"
                data-testid={`table-colwidth-${field.key}-${c.key}`}
                title={`${c.label} sütun genişliği (mm)`}
              />
            ))}
            <div className="w-8" />
            <div className="w-7" />
          </div>
          <div className="max-h-64 overflow-y-auto space-y-1.5">
            {localRows.filter((r) => !r?.__widths__).map((row, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <Input
                  type="number"
                  placeholder="mm"
                  min="5" max="100" step="1"
                  value={row.__height_mm__ ?? ""}
                  onChange={(e) => updateCell(i, "__height_mm__", e.target.value)}
                  className="text-[10px] h-8 w-8 font-mono px-1"
                  data-testid={`table-rowheight-${field.key}-${i}`}
                  title="Satır yüksekliği (mm)"
                />
                {cols.map((c) => (
                  <Input
                    key={c.key}
                    placeholder={c.label}
                    value={row[c.key] ?? ""}
                    onChange={(e) => updateCell(i, c.key, e.target.value)}
                    type={c.type === "number" ? "number" : "text"}
                    className="text-xs h-8"
                    data-testid={`table-cell-${field.key}-${i}-${c.key}`}
                  />
                ))}
                <button onClick={() => removeRow(i)} data-testid={`table-row-del-${field.key}-${i}`} className="text-red-500 hover:text-red-700" title="Sil">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {localRows.length === 0 && (
              <div className="text-xs text-zinc-500 italic py-3 text-center">Henüz satır yok</div>
            )}
          </div>
          <div className="flex items-center justify-between mt-3 pt-2 border-t border-zinc-200">
            <Button size="sm" variant="outline" onClick={addRow}><Plus className="w-3 h-3 mr-1" /> Satır Ekle</Button>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Kapat</Button>
              <Button size="sm" onClick={save} disabled={saving} className="bg-zinc-950 text-white hover:bg-zinc-800">
                {saving ? "Kaydediliyor..." : "Kaydet"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BuiltinPreview({ chat, fieldsList, sectionsList, template }) {
  const hasContent = fieldsList.length > 0 || sectionsList.length > 0;
  return (
    <div className="p-10">
      <div className="border-b border-zinc-200 pb-6 mb-6">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-[var(--brand-gold-2)] mb-1">
          KırCan Danışmanlık · Değerleme Raporu · {chat.report_no}
        </div>
        <h1 className="text-3xl tracking-tight font-light text-[var(--brand-navy)]">{template}</h1>
        <div className="text-xs text-zinc-500 mt-2 font-mono">
          {new Date().toLocaleDateString("tr-TR")}
        </div>
      </div>

      {!hasContent && (
        <div className="text-zinc-400 text-sm italic">
          Sohbet ilerledikçe rapor bu alanda oluşacak. İlk soruyu cevaplayarak başlayın.
        </div>
      )}

      {fieldsList.length > 0 && (
        <section className="mb-8">
          <h2 className="text-sm font-mono uppercase tracking-[0.25em] text-zinc-500 mb-3">
            Gayrimenkul Bilgileri
          </h2>
          <div className="border border-zinc-200 rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {fieldsList.map(([k, v], i) => (
                  <tr key={k} className={i % 2 ? "bg-zinc-50" : "bg-white"}>
                    <td className="px-3 py-2 text-zinc-500 border-b border-zinc-200 font-mono text-xs uppercase tracking-wider">{k}</td>
                    <td className="px-3 py-2 text-zinc-950 border-b border-zinc-200">{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {sectionsList.map(([name, text]) => (
        <section key={name} className="mb-6">
          <h2 className="text-lg tracking-tight font-medium text-zinc-950 mb-2 border-l-2 border-zinc-950 pl-3">
            {name}
          </h2>
          <div className="text-sm text-zinc-800 leading-relaxed whitespace-pre-wrap">{text}</div>
        </section>
      ))}
    </div>
  );
}
