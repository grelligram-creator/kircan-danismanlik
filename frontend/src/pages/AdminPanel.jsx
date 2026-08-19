import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Users, Wallet, ArrowLeft, Send, Building2, Copy, Trash2 } from "lucide-react";
import { InviteDialog } from "@/pages/SuperAdmin";

export default function AdminPanel() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [company, setCompany] = useState(null);
  const [invites, setInvites] = useState([]);
  const [showTopup, setShowTopup] = useState(null);
  const [showInvite, setShowInvite] = useState(false);

  const load = async () => {
    try {
      const [u, c, i] = await Promise.all([
        api.get("/admin/users"),
        api.get("/admin/companies"),
        api.get("/admin/invites"),
      ]);
      setUsers(u.data.users || []);
      setCompany((c.data.companies || [])[0] || null);
      setInvites(i.data.invites || []);
    } catch (e) {
      toast.error("Veri yüklenemedi");
    }
  };

  useEffect(() => {
    if (!user) return;
    if (user.role !== "admin" && user.role !== "super_admin") {
      navigate("/dashboard", { replace: true });
      return;
    }
    load();
  }, [user]);

  if (!user || (user.role !== "admin" && user.role !== "super_admin")) return null;
  const fmtTRY = (n) => `₺${Number(n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="admin-panel">
      <header className="border-b border-zinc-200 bg-white sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate("/dashboard")} className="text-zinc-500 hover:text-zinc-950" data-testid="admin-back-btn">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-[var(--brand-navy)] flex items-center justify-center ring-1 ring-[var(--brand-gold)]/40">
                <Building2 className="w-5 h-5 text-[var(--brand-gold-2)]" />
              </div>
              <div>
                <div className="text-xs font-mono uppercase tracking-[0.28em] text-[var(--brand-gold-2)]">Admin Paneli</div>
                <div className="text-lg font-medium text-[var(--brand-navy)]">{company?.name || "Şirket"}</div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {company && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white border border-zinc-200 rounded-lg p-4">
              <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2 flex items-center gap-2">
                <Wallet className="w-3.5 h-3.5" /> Şirket Bütçesi
              </div>
              <div className="text-3xl font-black text-[var(--brand-navy)]">{fmtTRY(company.budget_balance)}</div>
              <div className="text-xs text-zinc-500 mt-1">Kullanıcılara buradan aktarım yapabilirsiniz</div>
            </div>
            <div className="bg-white border border-zinc-200 rounded-lg p-4">
              <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2 flex items-center gap-2">
                <Users className="w-3.5 h-3.5" /> Kullanıcı
              </div>
              <div className="text-3xl font-black text-[var(--brand-navy)]">{users.length}</div>
              <div className="text-xs text-zinc-500 mt-1">Şirketinize bağlı kullanıcılar</div>
            </div>
            <div className="bg-white border border-zinc-200 rounded-lg p-4 flex flex-col justify-between">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">Hızlı İşlem</div>
                <div className="text-sm text-zinc-600">Yeni kullanıcı davet edin</div>
              </div>
              <Button onClick={() => setShowInvite(true)} className="mt-3 bg-[var(--brand-navy)] text-white" data-testid="admin-invite-btn">
                <Send className="w-4 h-4 mr-1" /> Davet Gönder
              </Button>
            </div>
          </div>
        )}

        <div className="bg-white border border-zinc-200 rounded-lg overflow-hidden">
          <div className="p-4 border-b border-zinc-200">
            <h2 className="text-lg font-medium text-[var(--brand-navy)]">Şirket Kullanıcıları</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="admin-users-table">
              <thead className="bg-zinc-50 border-b border-zinc-200">
                <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                  <th className="p-3">Kullanıcı</th>
                  <th className="p-3">Rol</th>
                  <th className="p-3">Cüzdan</th>
                  <th className="p-3">Sohbet</th>
                  <th className="p-3">Harcama</th>
                  <th className="p-3 text-right">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id} className="border-b border-zinc-100 hover:bg-zinc-50" data-testid={`admin-user-${u.user_id}`}>
                    <td className="p-3">
                      <div className="font-medium">{u.name || "-"}</div>
                      <div className="text-xs text-zinc-500">{u.email}</div>
                    </td>
                    <td className="p-3"><Badge variant="secondary" className="text-[10px]">{(u.role || "user").toUpperCase()}</Badge></td>
                    <td className="p-3 font-mono">{fmtTRY(u.wallet_balance)}</td>
                    <td className="p-3">{u.chat_count}</td>
                    <td className="p-3 font-mono">{fmtTRY(u.total_spent)}</td>
                    <td className="p-3 text-right">
                      <button
                        data-testid={`admin-topup-${u.user_id}`}
                        onClick={() => setShowTopup(u)}
                        className="text-[var(--brand-navy)] text-xs hover:underline"
                        disabled={u.user_id === user.user_id}
                      >
                        Bakiye Aktar
                      </button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr><td colSpan={6} className="p-8 text-center text-zinc-500">Henüz kullanıcı yok. Davet gönderin.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white border border-zinc-200 rounded-lg">
          <div className="p-4 border-b border-zinc-200 flex items-center justify-between">
            <h2 className="text-lg font-medium text-[var(--brand-navy)]">Davetler</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 border-b border-zinc-200">
              <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                <th className="p-3">Link</th>
                <th className="p-3">E-posta</th>
                <th className="p-3">Durum</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {invites.map((iv) => (
                <tr key={iv.code} className="border-b border-zinc-100">
                  <td className="p-3 text-xs">
                    <div className="flex items-center gap-2">
                      <code className="bg-zinc-100 px-2 py-1 rounded">{iv.code.substring(0, 18)}...</code>
                      <button onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/join/${iv.code}`); toast.success("Kopyalandı"); }}>
                        <Copy className="w-3.5 h-3.5 text-zinc-500" />
                      </button>
                    </div>
                  </td>
                  <td className="p-3 text-xs">{iv.email || "—"}</td>
                  <td className="p-3">
                    {iv.used ? <Badge variant="secondary" className="text-[10px]">Kullanıldı</Badge>
                      : <Badge className="text-[10px] bg-blue-100 text-blue-800 hover:bg-blue-100">Aktif</Badge>}
                  </td>
                  <td className="p-3 text-right">
                    {!iv.used && (
                      <button onClick={async () => { await api.delete(`/admin/invites/${iv.code}`); load(); toast.success("İptal edildi"); }}>
                        <Trash2 className="w-3.5 h-3.5 text-red-600" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {invites.length === 0 && (<tr><td colSpan={4} className="p-6 text-center text-zinc-500">Henüz davet yok</td></tr>)}
            </tbody>
          </table>
        </div>
      </main>

      <TopupDialog target={showTopup} onClose={() => setShowTopup(null)} onDone={load} maxAmount={company?.budget_balance} />
      <InviteDialog open={showInvite} companies={[]} onClose={() => setShowInvite(false)} onDone={load} isSuperAdmin={false} />
    </div>
  );
}

function TopupDialog({ target, onClose, onDone, maxAmount }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  if (!target) return null;
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/users/${target.user_id}/wallet/topup`, { amount: Number(amount), note });
      toast.success("Bakiye aktarıldı");
      setAmount(""); setNote(""); onDone(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!target} onOpenChange={onClose}>
      <DialogContent data-testid="admin-topup-dialog">
        <DialogHeader><DialogTitle>Kullanıcıya Bakiye Aktar</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="bg-zinc-50 p-3 rounded text-sm">
            <div className="text-zinc-500 text-xs">Hedef</div>
            <div className="font-medium">{target.email}</div>
            <div className="text-xs text-zinc-500">Mevcut cüzdan: ₺{Number(target.wallet_balance).toFixed(2)}</div>
          </div>
          <div>
            <Label>Tutar (TL) — Şirket bütçesi: ₺{Number(maxAmount || 0).toFixed(2)}</Label>
            <Input data-testid="admin-topup-amount" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div>
            <Label>Not (opsiyonel)</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>İptal</Button>
          <Button disabled={!amount || busy} onClick={submit} className="bg-[var(--brand-navy)] text-white" data-testid="admin-topup-submit">Aktar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
