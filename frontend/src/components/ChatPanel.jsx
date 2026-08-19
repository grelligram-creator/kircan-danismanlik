import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Paperclip, X, FileText, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ChatPanel({ chat, messages, onMessageSent, onLowCredits }) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
      toast.success(`${files.length} dosya yüklendi. Göndermek için mesaj yazın.`);
    } catch {
      toast.error("Dosya yüklenemedi");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeAttachment = (id) => setAttachments((prev) => prev.filter((a) => a.upload_id !== id));

  const send = async () => {
    if (!input.trim() && attachments.length === 0) return;
    setSending(true);
    const attachment_ids = attachments.map((a) => a.upload_id);
    const content = input.trim() || "(Ekli dosyaları analiz et)";
    setInput("");
    setAttachments([]);
    try {
      const { data } = await api.post(`/chats/${chat.chat_id}/message`, { content, attachment_ids });
      onMessageSent?.(data);
      if (data.low_credit_warning) onLowCredits?.(data.credits);
    } catch (err) {
      if (err.response?.status === 402) {
        toast.error("Kredi bakiyeniz yetersiz", { description: "Kredi paketi satın alarak devam edebilirsiniz." });
        onLowCredits?.(0);
      } else {
        toast.error("Mesaj gönderilemedi");
      }
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
          {sending && (
            <div className="flex items-center gap-2 text-zinc-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="font-mono uppercase tracking-widest text-xs">Asistan yazıyor...</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className="border-t border-zinc-200 px-6 py-3 bg-zinc-50 flex gap-2 flex-wrap">
          {attachments.map((a) => (
            <div key={a.upload_id} className="flex items-center gap-2 bg-white border border-zinc-200 rounded-md px-3 py-1.5 text-sm">
              <FileText className="w-3.5 h-3.5 text-zinc-500" />
              <span className="text-zinc-800 max-w-[200px] truncate">{a.filename}</span>
              <button onClick={() => removeAttachment(a.upload_id)} className="text-zinc-400 hover:text-zinc-950">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
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
                disabled={uploading || chat.mode === "faq"}
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
            {chat.mode === "faq" ? "5 kredi / mesaj" : "10 kredi / mesaj"} · Claude Sonnet 5
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-4 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-8 h-8 rounded-md flex-shrink-0 flex items-center justify-center text-xs font-mono ${
        isUser ? "bg-zinc-950 text-white" : "bg-[#0055FF]/10 text-[#0055FF]"
      }`}>
        {isUser ? "SEN" : "AI"}
      </div>
      <div className={`max-w-[80%] ${isUser ? "text-right" : ""}`}>
        <div className={`inline-block text-left rounded-md px-4 py-3 ${
          isUser
            ? "bg-zinc-950 text-white"
            : "bg-zinc-50 border border-zinc-200 text-zinc-900"
        }`}>
          <div className="whitespace-pre-wrap text-sm leading-relaxed font-body">{message.content}</div>
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
