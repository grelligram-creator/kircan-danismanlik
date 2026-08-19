import { useEffect, useState, useCallback } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import ReportPreviewPanel from "@/components/ReportPreviewPanel";
import TemplateSelectorDialog from "@/components/TemplateSelectorDialog";
import UpsellDialog from "@/components/UpsellDialog";
import { toast } from "sonner";

export default function Dashboard() {
  const { user, loading, updateCredits } = useAuth();
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showUpsell, setShowUpsell] = useState(false);

  const loadChats = useCallback(async () => {
    try {
      const { data } = await api.get("/chats");
      setChats(data.chats);
    } catch {}
  }, []);

  useEffect(() => {
    if (user) loadChats();
  }, [user, loadChats]);

  const openChat = async (chatId) => {
    try {
      const { data } = await api.get(`/chats/${chatId}`);
      setActiveChat(data.chat);
      setMessages(data.messages);
    } catch {
      toast.error("Sohbet açılamadı");
    }
  };

  const handleTemplateSelect = async (t) => {
    setShowTemplates(false);
    try {
      const payload = t?.id ? { mode: "report", template_id: t.id } : { mode: "faq" };
      const { data } = await api.post("/chats", payload);
      setChats((prev) => [data.chat, ...prev]);
      setActiveChat(data.chat);
      setMessages([data.message]);
    } catch {
      toast.error("Sohbet oluşturulamadı");
    }
  };

  const handleMessageSent = (data) => {
    setMessages((prev) => [...prev, data.user_message, data.assistant_message]);
    setActiveChat(data.chat);
    setChats((prev) => prev.map((c) => (c.chat_id === data.chat.chat_id ? data.chat : c)));
    updateCredits(data.credits);
    if (data.chat.status === "completed") {
      toast.success("Rapor tamamlandı!", { description: "Sağ panelden PDF/DOCX indirebilir veya e-posta ile gönderebilirsiniz." });
    }
  };

  const handleLowCredits = () => setShowUpsell(true);

  const handlePurchased = (credits) => updateCredits(credits);

  const deleteChat = async (chatId) => {
    try {
      await api.delete(`/chats/${chatId}`);
      setChats((prev) => prev.filter((c) => c.chat_id !== chatId));
      if (activeChat?.chat_id === chatId) {
        setActiveChat(null);
        setMessages([]);
      }
    } catch {}
  };

  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-zinc-50">
        <div className="text-zinc-500 text-sm font-mono uppercase tracking-widest">Yükleniyor...</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/" replace />;

  return (
    <div className="h-screen w-full flex overflow-hidden bg-zinc-50 font-body" data-testid="dashboard">
      <Sidebar
        chats={chats}
        activeChatId={activeChat?.chat_id}
        onNewChat={() => setShowTemplates(true)}
        onSelect={openChat}
        onDelete={deleteChat}
        onOpenUpsell={() => setShowUpsell(true)}
      />

      <div className="flex-1 flex overflow-hidden">
        {!activeChat ? (
          <EmptyState onNewChat={() => setShowTemplates(true)} />
        ) : (
          <ResizablePanelGroup direction="horizontal">
            <ResizablePanel defaultSize={50} minSize={30}>
              <ChatPanel
                chat={activeChat}
                messages={messages}
                onMessageSent={handleMessageSent}
                onLowCredits={handleLowCredits}
              />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={50} minSize={25}>
              <ReportPreviewPanel chat={activeChat} />
            </ResizablePanel>
          </ResizablePanelGroup>
        )}
      </div>

      <TemplateSelectorDialog
        open={showTemplates}
        onOpenChange={setShowTemplates}
        onSelect={handleTemplateSelect}
      />
      <UpsellDialog open={showUpsell} onOpenChange={setShowUpsell} onPurchased={handlePurchased} />
    </div>
  );
}

function EmptyState({ onNewChat }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-white p-8">
      <div className="max-w-md text-center">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-4">
          Başlangıç
        </div>
        <h1 className="text-4xl tracking-tighter font-light text-zinc-950 mb-4">
          Hangi <span className="italic">raporu</span> hazırlayalım?
        </h1>
        <p className="text-zinc-600 leading-relaxed mb-8">
          AI asistanınız size gerekli bilgileri sırayla soracak. Dilerseniz PDF, Excel veya Word dosyalarınızı yükleyerek analiz ettirebilirsiniz.
        </p>
        <button
          onClick={onNewChat}
          data-testid="empty-new-chat-btn"
          className="bg-zinc-950 text-white hover:bg-zinc-800 rounded-md px-6 py-3 text-sm font-medium transition-colors"
        >
          Yeni Sohbet Başlat
        </button>
      </div>
    </div>
  );
}
