import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Paperclip, X, FileText, Loader2, Sparkles, AlertCircle, Check } from "lucide-react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const fmtTRY = (n) => `₺${Number(n).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

/** Strip <!--UPDATE {...}--> markers before display so user never sees them. */
function stripUpdateMarker(text) {
  if (!text) return "";
  const idx = text.indexOf("<!--UPDATE");
  if (idx === -1) return text;
  const end = text.indexOf("-->", idx);
  if (end === -1) return text.slice(0, idx);
  return (text.slice(0, idx) + text.slice(end + 3)).trim();
}

export default function ChatPanel({ chat, messages, onStreamStart, onStreamDelta, onStreamDone, onLowBalance, costPerMessage, onFieldsUpdated }) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [autofillLoading, setAutofillLoading] = useState(false);
  const [autofillResult, setAutofillResult] = useState(null);
  const [resolvedDuplicates, setResolvedDuplicates] = useState({});
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const runAutofill = async (ids) => {
    if (!ids?.length) return;
    setAutofillLoading(true);
    try {
      const { data } = await api.post(`/chats/${chat.chat_id}/autofill`, { attachment_ids: ids });
      setAutofillResult(data);
      setResolvedDuplicates({});
      if ((data.out_of_scope || []).length > 0) {
        toast.warning(`${data.out_of_scope.length} belge kapsam dışı`, { description: data.out_of_scope[0]?.reason });
      }
      if (Object.keys(data.fields || {}).length === 0 && (data.duplicates || []).length === 0) {
        toast.info("Belgelerden alan çıkarılamadı");
      }
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (typeof detail === "object" && detail?.error === "insufficient_balance") {
        onLowBalance?.();
      } else {
        toast.error(typeof detail === "string" ? detail : "Analiz başarısız");
      }
    } finally {
      setAutofillLoading(false);
    }
  };

  const acceptAutofill = async () => {
    if (!autofillResult) return;
    const merged = { ...(autofillResult.fields || {}) };
    // Include resolved duplicate choices
    for (const [key, value] of Object.entries(resolvedDuplicates)) {
      merged[key] = value;
    }
    try {
      await api.patch(`/chats/${chat.chat_id}/fields`, { fields: merged });
      toast.success(`${Object.keys(merged).length} alan dolduruldu`, { description: `Ücret: ₺${autofillResult.cost_try}` });
      onFieldsUpdated?.();
      setAttachments([]);
      setAutofillResult(null);
    } catch {
      toast.error("Alanlar kaydedilemedi");
    }
  };

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setUploading(true);
    try {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const { data } = await api.post("/uploads", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setAttachments((prev) => [...prev, data]);
      }
      toast.success(`${files.length} dosya yüklendi.`);
    } catch {
      toast.error("Dosya yüklenemedi");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeAttachment = (id) => setAttachments((prev) => prev.filter((a) => a.upload_id !== id));

  const send = async () => {
    if (sending) return;
    if (!input.trim() && attachments.length === 0) return;
    setSending(true);
    setStreamingText("");
    const attachment_ids = attachments.map((a) => a.upload_id);
    const content = input.trim() || "(Ekli dosyaları analiz et)";
    setInput("");
    setAttachments([]);

    try {
      const res = await fetch(`${API}/chats/${chat.chat_id}/message`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, attachment_ids }),
      });
      if (!res.ok) {
        if (res.status === 402) {
          toast.error("Bakiye yetersiz", { description: "Cüzdanınıza bakiye eklemeniz gerekiyor." });
          onLowBalance?.();
        } else {
          toast.error(`Sunucu hatası (${res.status})`);
        }
        setSending(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          if (!raw.startsWith("data:")) continue;
          const jsonStr = raw.slice(5).trim();
          if (!jsonStr) continue;
          let evt;
          try { evt = JSON.parse(jsonStr); } catch { continue; }

          if (evt.type === "user_message") {
            onStreamStart?.(evt.message);
          } else if (evt.type === "delta") {
            accumulated += evt.content;
            setStreamingText(stripUpdateMarker(accumulated));
            onStreamDelta?.(evt.content);
          } else if (evt.type === "done") {
            onStreamDone?.(evt);
            setStreamingText("");
            if (evt.low_balance_warning) onLowBalance?.();
          } else if (evt.type === "error") {
            toast.error("AI hatası", { description: evt.message });
          }
        }
      }
    } catch (e) {
      toast.error("Bağlantı hatası", { description: String(e) });
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="h-full flex flex-col bg-white" data-testid="chat-panel">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="max-w-2xl mx-auto space-y-8">
          {messages.map((m) => (
            <MessageBubble key={m.message_id} message={m} />
          ))}
          {streamingText && (
            <MessageBubble
              message={{ message_id: "streaming", role: "assistant", content: streamingText }}
              streaming
            />
          )}
          {sending && !streamingText && (
            <div className="flex items-center gap-2 text-zinc-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="font-mono uppercase tracking-widest text-xs">Asistan düşünüyor...</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {attachments.length > 0 && (
        <div className="border-t border-zinc-200 px-6 py-3 bg-zinc-50 space-y-2">
          <div className="flex gap-2 flex-wrap">
            {attachments.map((a) => (
              <div key={a.upload_id} className="flex items-center gap-2 bg-white border border-zinc-200 rounded-md px-3 py-1.5 text-sm" data-testid={`attachment-${a.upload_id}`}>
                <FileText className="w-3.5 h-3.5 text-zinc-500" />
                <span className="text-zinc-800 max-w-[200px] truncate">{a.filename}</span>
                <button onClick={() => removeAttachment(a.upload_id)} className="text-zinc-400 hover:text-zinc-950">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
          {chat.mode === "report" && attachments.some(a => /pdf|image\//i.test(a.content_type || "")) && (
            <button
              data-testid="autofill-btn"
              onClick={() => runAutofill(attachments.filter(a => /pdf|image\//i.test(a.content_type || "")).map(a => a.upload_id))}
              disabled={autofillLoading}
              className="text-xs bg-[var(--brand-navy)] text-white px-3 py-1.5 rounded-md hover:opacity-90 disabled:opacity-50 flex items-center gap-1.5"
            >
              {autofillLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              {autofillLoading ? "Analiz ediliyor..." : "Belgelerden Otomatik Doldur"}
            </button>
          )}
        </div>
      )}

      <div className="border-t border-zinc-200 p-4 bg-white">
        <div className="max-w-2xl mx-auto">
          <div className="border border-zinc-300 rounded-md focus-within:border-zinc-950 transition-colors bg-white">
            <Textarea
              data-testid="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={chat.mode === "faq" ? "Değerleme hakkında bir soru sorun..." : "Cevabınızı yazın ya da dosya yükleyin..."}
              className="border-0 resize-none focus-visible:ring-0 min-h-[60px] font-body"
              disabled={sending}
            />
            <div className="flex items-center justify-between px-2 pb-2">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.csv"
                className="hidden"
                onChange={handleUpload}
                data-testid="file-input"
              />
              <Button
                variant="ghost"
                size="sm"
                data-testid="upload-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || sending || chat.mode === "faq"}
                className="text-zinc-600 hover:text-zinc-950"
              >
                <Paperclip className="w-4 h-4 mr-1.5" />
                {uploading ? "Yükleniyor..." : "Dosya Ekle"}
              </Button>
              <Button
                data-testid="send-btn"
                onClick={send}
                disabled={sending || (!input.trim() && attachments.length === 0)}
                className="bg-zinc-950 text-white hover:bg-zinc-800"
                size="sm"
              >
                Gönder
                <Send className="w-4 h-4 ml-1.5" />
              </Button>
            </div>
          </div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-400 mt-2 text-center">
            Mesaj başı: {costPerMessage != null ? fmtTRY(costPerMessage) : "—"} · Claude Sonnet 5
          </div>
        </div>
      </div>

      {/* Autofill result dialog */}
      <Dialog open={!!autofillResult} onOpenChange={(v) => { if (!v) setAutofillResult(null); }}>
        <DialogContent className="max-w-2xl" data-testid="autofill-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[var(--brand-gold-2)]" />
              Otomatik Doldurma Sonuçları
            </DialogTitle>
          </DialogHeader>
          {autofillResult && (
            <div className="space-y-4 max-h-[500px] overflow-y-auto">
              <div className="flex items-center justify-between text-xs text-zinc-500 border-b border-zinc-100 pb-2">
                <div>{autofillResult.files_analyzed} belge analiz edildi · Alan: {Object.keys(autofillResult.fields || {}).length}</div>
                <div className="font-mono">Maliyet: ₺{autofillResult.cost_try} · {autofillResult.tokens?.input || 0} in / {autofillResult.tokens?.output || 0} out</div>
              </div>
              {(autofillResult.out_of_scope || []).length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 space-y-1">
                  <div className="flex items-center gap-2 text-amber-900 font-medium text-sm"><AlertCircle className="w-4 h-4" />Kapsam Dışı Belgeler</div>
                  {autofillResult.out_of_scope.map((o, i) => (
                    <div key={i} className="text-xs text-amber-800">
                      <b>{o.filename}:</b> {o.reason}
                    </div>
                  ))}
                </div>
              )}
              {(autofillResult.duplicates || []).length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-mono uppercase tracking-widest text-zinc-500">Mükerrer Alanlar (birini seçin)</div>
                  {autofillResult.duplicates.map((d, i) => (
                    <div key={i} className="bg-zinc-50 border border-zinc-200 rounded-md p-3" data-testid={`duplicate-${d.field}`}>
                      <div className="text-sm font-medium text-zinc-900 mb-2">{d.field}</div>
                      <div className="space-y-1">
                        {d.values.map((opt, j) => (
                          <label key={j} className="flex items-start gap-2 text-sm cursor-pointer hover:bg-zinc-100 p-1.5 rounded">
                            <input
                              type="radio"
                              name={`dup_${d.field}`}
                              checked={resolvedDuplicates[d.field] === opt.value}
                              onChange={() => setResolvedDuplicates((p) => ({ ...p, [d.field]: opt.value }))}
                              className="mt-1"
                              data-testid={`dup-opt-${d.field}-${j}`}
                            />
                            <div className="flex-1">
                              <div className="text-xs text-zinc-500">{opt.source}</div>
                              <div className="text-zinc-900">{opt.value}</div>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {Object.keys(autofillResult.fields || {}).length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs font-mono uppercase tracking-widest text-zinc-500">Çıkarılan Alanlar</div>
                  <div className="border border-zinc-200 rounded-md divide-y divide-zinc-100">
                    {Object.entries(autofillResult.fields).map(([k, v]) => (
                      <div key={k} className="flex justify-between px-3 py-2 text-sm" data-testid={`field-${k}`}>
                        <span className="font-mono text-xs text-zinc-500">{k}</span>
                        <span className="text-zinc-900 max-w-[60%] text-right">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {autofillResult.notes && (
                <div className="text-xs text-zinc-500 italic border-l-2 border-zinc-300 pl-2">{autofillResult.notes}</div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAutofillResult(null)}>Vazgeç</Button>
            <Button
              data-testid="autofill-accept-btn"
              onClick={acceptAutofill}
              className="bg-[var(--brand-navy)] text-white"
              disabled={!autofillResult || Object.keys(autofillResult.fields || {}).length + Object.keys(resolvedDuplicates).length === 0}
            >
              <Check className="w-4 h-4 mr-1" />
              Onayla ve Doldur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MessageBubble({ message, streaming }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-4 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-8 h-8 rounded-md flex-shrink-0 flex items-center justify-center text-xs font-mono ${
        isUser ? "bg-[var(--brand-navy)] text-white" : "bg-[var(--brand-navy)] text-[var(--brand-gold-2)] ring-1 ring-[var(--brand-gold)]/30"
      }`}>
        {isUser ? "SEN" : "AI"}
      </div>
      <div className={`max-w-[80%] ${isUser ? "text-right" : ""}`}>
        <div className={`inline-block text-left rounded-md px-4 py-3 ${
          isUser
            ? "bg-[var(--brand-navy)] text-white"
            : "bg-zinc-50 border border-zinc-200 text-zinc-900"
        }`}>
          <div className="whitespace-pre-wrap text-sm leading-relaxed font-body">
            {stripUpdateMarker(message.content)}
            {streaming && <span className="inline-block w-1.5 h-4 ml-0.5 bg-zinc-400 align-middle animate-pulse" />}
          </div>
          {message.attachments?.length > 0 && (
            <div className="mt-2 pt-2 border-t border-white/20 flex flex-wrap gap-1">
              {message.attachments.map((a) => (
                <span key={a.upload_id} className="text-[10px] font-mono uppercase tracking-widest opacity-70">
                  <FileText className="w-3 h-3 inline mr-1" />{a.filename}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
