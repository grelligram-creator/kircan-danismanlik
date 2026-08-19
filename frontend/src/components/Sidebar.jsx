import { Button } from "@/components/ui/button";
import { Plus, MessageSquare, HelpCircle, LogOut, Wallet, Building2, Trash2, BarChart3, FileStack, Shield, DatabaseZap, UserCog } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { tr } from "date-fns/locale";

export default function Sidebar({ chats, activeChatId, onNewChat, onSelect, onDelete, onOpenUpsell }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const lowBalance = (user?.wallet_balance ?? 0) < 30;
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const isSuper = user?.role === "super_admin";
  const fmtTRY = (n) => `₺${Number(n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

  return (
    <aside className="w-72 border-r border-zinc-200 bg-zinc-50 flex flex-col flex-shrink-0" data-testid="sidebar">
      <div className="p-4 border-b border-zinc-200">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-9 h-9 rounded-md overflow-hidden bg-[var(--brand-navy)] ring-1 ring-[var(--brand-gold)]/40">
            <img src="/kircan-mark.png" alt="KırCan" className="w-full h-full object-cover" />
          </div>
          <div>
            <div className="text-xs font-mono uppercase tracking-[0.25em] text-[var(--brand-navy)]">KırCan Report AI</div>
            <div className="text-[10px] text-zinc-500">{user?.company_name || "Değerleme Asistanı"}</div>
          </div>
        </div>
        <Button
          data-testid="new-chat-btn"
          onClick={onNewChat}
          className="w-full text-white rounded-md"
          style={{ backgroundColor: "var(--brand-navy)" }}
        >
          <Plus className="w-4 h-4 mr-2" /> Yeni Sohbet
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 px-2 py-2">Geçmiş</div>
        <div className="space-y-1">
          {chats.length === 0 && (
            <div className="px-2 py-6 text-sm text-zinc-500 italic">Henüz sohbet yok.</div>
          )}
          {chats.map((c) => (
            <div
              key={c.chat_id}
              data-testid={`chat-item-${c.chat_id}`}
              className={`group flex items-center gap-2 px-2.5 py-2 rounded-md cursor-pointer transition-colors ${
                activeChatId === c.chat_id ? "bg-white border border-zinc-200" : "hover:bg-white"
              }`}
              onClick={() => onSelect(c.chat_id)}
            >
              {c.mode === "faq" ? (
                <HelpCircle className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
              ) : (
                <MessageSquare className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-sm text-zinc-900 truncate">{c.title}</div>
                <div className="text-[10px] text-zinc-500 font-mono">
                  {c.status === "completed" ? "Tamamlandı" : "Devam ediyor"}
                </div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(c.chat_id); }}
                className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-red-600 transition-opacity"
                data-testid={`delete-chat-${c.chat_id}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="p-3 border-t border-zinc-200 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <button
            data-testid="templates-btn"
            onClick={() => navigate("/templates")}
            className="flex items-center gap-1.5 justify-center px-2 py-2 rounded-md border border-zinc-200 bg-white hover:border-zinc-950 transition-colors text-xs text-zinc-900"
          >
            <FileStack className="w-3.5 h-3.5 text-zinc-500" />
            <span>Şablonlar</span>
          </button>
          <button
            data-testid="analytics-btn"
            onClick={() => navigate("/analytics")}
            className="flex items-center gap-1.5 justify-center px-2 py-2 rounded-md border border-zinc-200 bg-white hover:border-zinc-950 transition-colors text-xs text-zinc-900"
          >
            <BarChart3 className="w-3.5 h-3.5 text-zinc-500" />
            <span>Analitik</span>
          </button>
        </div>

        {isAdmin && (
          <div className="grid grid-cols-2 gap-2">
            <button
              data-testid="kb-nav-btn"
              onClick={() => navigate("/knowledge-base")}
              className="flex items-center gap-1.5 justify-center px-2 py-2 rounded-md border border-[var(--brand-gold)]/40 bg-[var(--brand-gold)]/10 hover:bg-[var(--brand-gold)]/20 transition-colors text-xs text-[var(--brand-navy)]"
            >
              <DatabaseZap className="w-3.5 h-3.5" />
              <span>Bilgi Bankası</span>
            </button>
            <button
              data-testid="admin-nav-btn"
              onClick={() => navigate(isSuper ? "/admin/super" : "/admin")}
              className="flex items-center gap-1.5 justify-center px-2 py-2 rounded-md border border-[var(--brand-navy)]/40 bg-[var(--brand-navy)]/5 hover:bg-[var(--brand-navy)]/10 transition-colors text-xs text-[var(--brand-navy)]"
            >
              <Shield className="w-3.5 h-3.5" />
              <span>{isSuper ? "Süper Panel" : "Admin"}</span>
            </button>
          </div>
        )}

        <button
          data-testid="credits-btn"
          onClick={onOpenUpsell}
          className={`w-full text-left p-3 rounded-md border transition-colors ${
            lowBalance
              ? "border-amber-300 bg-amber-50 hover:bg-amber-100"
              : "border-zinc-200 bg-white hover:border-zinc-950"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <Wallet className={`w-3.5 h-3.5 ${lowBalance ? "text-amber-600" : "text-zinc-500"}`} />
              <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">Cüzdan</span>
            </div>
            <span className="text-[10px] font-mono text-zinc-500">Yükle</span>
          </div>
          <div className={`font-black text-2xl tracking-tight ${lowBalance ? "text-amber-700" : "text-zinc-950"}`}>
            {fmtTRY(user?.wallet_balance)}
          </div>
        </button>

        <div className="flex items-center justify-between px-1">
          <button
            onClick={() => navigate("/profile")}
            data-testid="profile-btn"
            className="flex items-center gap-2 min-w-0 flex-1 text-left hover:opacity-80 transition-opacity"
            title="Profil ayarları"
          >
            {user?.picture ? (
              <img src={user.picture} alt="" className="w-7 h-7 rounded-full" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-zinc-950 text-white flex items-center justify-center text-xs">
                {user?.name?.[0] || "?"}
              </div>
            )}
            <div className="min-w-0">
              <div className="text-xs font-medium text-zinc-900 truncate">{user?.name}</div>
              <div className="text-[10px] text-zinc-500 truncate">{user?.email}</div>
            </div>
          </button>
          <button
            data-testid="logout-btn"
            onClick={logout}
            className="text-zinc-500 hover:text-zinc-950 p-1"
            title="Çıkış"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="pt-2 mt-2 border-t border-zinc-200 text-center">
          <div className="text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-400">
            Powered by <span className="text-[var(--brand-gold-2)] font-medium">Algorisma</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
