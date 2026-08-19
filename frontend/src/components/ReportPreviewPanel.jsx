import { Button } from "@/components/ui/button";
import { Download, Mail, FileText, CheckCircle2, Loader2 } from "lucide-react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { useState } from "react";

export default function ReportPreviewPanel({ chat }) {
  const [emailing, setEmailing] = useState(false);

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

  const download = (fmt) => {
    const url = `${API}/chats/${chat.chat_id}/download/${fmt}`;
    window.open(url, "_blank");
  };

  const sendEmail = async () => {
    setEmailing(true);
    try {
      const { data } = await api.post(`/chats/${chat.chat_id}/email`);
      toast.success(`Rapor e-posta ile gönderildi (MOCK)`, {
        description: `Alıcı: ${data.sent_to}`,
      });
    } catch {
      toast.error("E-posta gönderilemedi");
    } finally {
      setEmailing(false);
    }
  };

  const template = chat.template_name || "Değerleme Raporu";
  const fieldsList = Object.entries(chat.fields || {});
  const sectionsList = Object.entries(chat.sections || {});
  const completed = chat.status === "completed";
  const hasContent = fieldsList.length > 0 || sectionsList.length > 0;

  return (
    <div className="h-full flex flex-col bg-zinc-100/50" data-testid="preview-panel">
      {/* Sticky header */}
      <div className="border-b border-zinc-200 bg-white px-6 py-4 flex items-center justify-between flex-shrink-0">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">
            Rapor Önizleme · {chat.report_no || "-"}
          </div>
          <div className="text-sm font-medium text-zinc-900 mt-0.5 flex items-center gap-2">
            {template}
            {completed && (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                <CheckCircle2 className="w-3 h-3" /> Tamamlandı
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            data-testid="download-pdf-btn"
            variant="outline"
            size="sm"
            onClick={() => download("pdf")}
            disabled={!hasContent}
          >
            <Download className="w-3.5 h-3.5 mr-1.5" /> PDF
          </Button>
          <Button
            data-testid="download-docx-btn"
            variant="outline"
            size="sm"
            onClick={() => download("docx")}
            disabled={!hasContent}
          >
            <Download className="w-3.5 h-3.5 mr-1.5" /> DOCX
          </Button>
          <Button
            data-testid="email-report-btn"
            size="sm"
            className="bg-zinc-950 text-white hover:bg-zinc-800"
            onClick={sendEmail}
            disabled={!hasContent || emailing}
          >
            {emailing ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Mail className="w-3.5 h-3.5 mr-1.5" />}
            E-posta
          </Button>
        </div>
      </div>

      {/* Paper */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto bg-white shadow-sm ring-1 ring-zinc-200 p-10 min-h-full">
          <div className="border-b border-zinc-200 pb-6 mb-6">
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-2">
              Değerleme Raporu · {chat.report_no}
            </div>
            <h1 className="text-3xl tracking-tight font-light text-zinc-950">{template}</h1>
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
      </div>
    </div>
  );
}
