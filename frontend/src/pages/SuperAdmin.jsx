import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  Users, Building2, Wallet, Trash2, ShieldAlert, ShieldCheck, Ban, ArrowLeft, Send,
  MessagesSquare, Copy, Plus, DatabaseZap, Layers,
} from "lucide-react";

export default function SuperAdminPanel() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("users");
  const [users, setUsers] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [invites, setInvites] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [showTopup, setShowTopup] = useState(false);
  const [showRoleDialog, setShowRoleDialog] = useState(false);
  const [showCompanyDialog, setShowCompanyDialog] = useState(false);
  const [showInviteDialog, setShowInviteDialog] = useState(false);
  const [showCompanyTopup, setShowCompanyTopup] = useState(null); // company
  const [selectedChat, setSelectedChat] = useState(null);

  const loadAll = async () => {
    try {
      const [u, c, i, s] = await Promise.all([
        api.get("/admin/users"),
        api.get("/admin/companies"),
        api.get("/admin/invites"),
        api.get("/admin/system/summary"),
      ]);
      setUsers(u.data.users || []);
      setCompanies(c.data.companies || []);
      setInvites(i.data.invites || []);
      setSummary(s.data);
    } catch (e) {
      toast.error("Veri yüklenemedi");
    }
  };

  useEffect(() => {
    if (!user) return;
    if (user.role !== "super_admin") {
      navigate("/dashboard", { replace: true });
      return;
    }
    loadAll();
  }, [user]);

  const openUserDetail = async (u) => {
    try {
      const { data } = await api.get(`/admin/users/${u.user_id}`);
      setSelectedUser(data);
    } catch { toast.error("Detay yüklenemedi"); }
  };

  const openChatDetail = async (uid, cid) => {
    try {
      const { data } = await api.get(`/admin/users/${uid}/chat/${cid}`);
      setSelectedChat(data);
    } catch { toast.error("Sohbet açılamadı"); }
  };

  if (!user || user.role !== "super_admin") return null;

  const fmtTRY = (n) => `₺${Number(n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="super-admin-panel">
      <header className="border-b border-zinc-200 bg-white sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button data-testid="back-to-dashboard-btn" onClick={() => navigate("/dashboard")} className="text-zinc-500 hover:text-zinc-950 transition-colors">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-[var(--brand-navy)] flex items-center justify-center ring-1 ring-[var(--brand-gold)]/40">
                <ShieldAlert className="w-5 h-5 text-[var(--brand-gold-2)]" />
              </div>
              <div>
                <div className="text-xs font-mono uppercase tracking-[0.28em] text-[var(--brand-gold-2)]">Süper Admin</div>
                <div className="text-lg font-medium text-[var(--brand-navy)]">Sistem Yönetim Paneli</div>
              </div>
            </div>
          </div>
          <nav className="flex gap-1 text-sm">
            {[
              ["users", "Kullanıcılar", <Users className="w-3.5 h-3.5" />],
              ["companies", "Şirketler", <Building2 className="w-3.5 h-3.5" />],
              ["invites", "Davetler", <Send className="w-3.5 h-3.5" />],
              ["summary", "Özet", <Layers className="w-3.5 h-3.5" />],
            ].map(([k, l, ic]) => (
              <button
                key={k}
                data-testid={`tab-${k}`}
                onClick={() => setTab(k)}
                className={`px-3 py-2 rounded-md flex items-center gap-1.5 transition-colors ${
                  tab === k ? "bg-[var(--brand-navy)] text-white" : "text-zinc-600 hover:bg-zinc-100"
                }`}
              >
                {ic}
                <span>{l}</span>
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {tab === "summary" && summary && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard label="Toplam Kullanıcı" value={summary.total_users} icon={<Users className="w-4 h-4" />} />
            <StatCard label="Toplam Sohbet" value={summary.total_chats} icon={<MessagesSquare className="w-4 h-4" />} />
            <StatCard label="Toplam Harcama" value={fmtTRY(summary.total_spent)} icon={<Wallet className="w-4 h-4" />} />
            <StatCard label="Cüzdanlarda Bakiye" value={fmtTRY(summary.wallet_balance_sum)} icon={<Wallet className="w-4 h-4" />} />
            <StatCard label="Şirket Sayısı" value={summary.company_count} icon={<Building2 className="w-4 h-4" />} />
            <StatCard label="Şirket Bütçesi (Toplam)" value={fmtTRY(summary.company_budget_sum)} icon={<Wallet className="w-4 h-4" />} />
          </div>
        )}

        {tab === "users" && (
          <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
            <div className="p-4 border-b border-zinc-200 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-medium text-[var(--brand-navy)]">Kullanıcılar</h2>
                <p className="text-xs text-zinc-500">Rol, cüzdan ve chat geçmişini yönetin</p>
              </div>
              <div className="text-sm text-zinc-500">{users.length} kayıt</div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="users-table">
                <thead className="bg-zinc-50 border-b border-zinc-200">
                  <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                    <th className="p-3">Kullanıcı</th>
                    <th className="p-3">Rol</th>
                    <th className="p-3">Şirket</th>
                    <th className="p-3">Cüzdan</th>
                    <th className="p-3">Sohbet</th>
                    <th className="p-3">Harcama</th>
                    <th className="p-3">Durum</th>
                    <th className="p-3 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.user_id} className="border-b border-zinc-100 hover:bg-zinc-50" data-testid={`user-row-${u.user_id}`}>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          {u.picture ? (
                            <img src={u.picture} alt="" className="w-7 h-7 rounded-full" />
                          ) : (
                            <div className="w-7 h-7 rounded-full bg-[var(--brand-navy)] text-white text-xs flex items-center justify-center">
                              {(u.name || u.email)?.[0]?.toUpperCase()}
                            </div>
                          )}
                          <div>
                            <div className="font-medium text-zinc-900">{u.name || "-"}</div>
                            <div className="text-xs text-zinc-500">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="p-3">
                        <RoleBadge role={u.role} />
                      </td>
                      <td className="p-3 text-zinc-700">{u.company_name || <span className="text-zinc-400">—</span>}</td>
                      <td className="p-3 font-mono">{fmtTRY(u.wallet_balance)}</td>
                      <td className="p-3 text-zinc-700">{u.chat_count}</td>
                      <td className="p-3 font-mono text-zinc-700">{fmtTRY(u.total_spent)}</td>
                      <td className="p-3">
                        {u.blocked ? (
                          <Badge variant="destructive" className="text-[10px]">Engelli</Badge>
                        ) : (
                          <Badge className="text-[10px] bg-emerald-100 text-emerald-800 hover:bg-emerald-100">Aktif</Badge>
                        )}
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center gap-1 justify-end">
                          <button
                            data-testid={`view-user-${u.user_id}`}
                            onClick={() => openUserDetail(u)}
                            className="text-xs text-zinc-600 hover:text-[var(--brand-navy)] px-2 py-1"
                          >
                            Detay
                          </button>
                          <button
                            data-testid={`topup-user-${u.user_id}`}
                            onClick={() => setShowTopup(u)}
                            className="text-xs text-[var(--brand-navy)] hover:underline px-2 py-1"
                          >
                            Bakiye Ekle
                          </button>
                          <button
                            data-testid={`role-user-${u.user_id}`}
                            onClick={() => setShowRoleDialog(u)}
                            className="text-xs text-zinc-600 hover:text-[var(--brand-navy)] px-2 py-1"
                          >
                            Rol
                          </button>
                          <button
                            data-testid={`block-user-${u.user_id}`}
                            onClick={async () => {
                              await api.post(`/admin/users/${u.user_id}/block`, { blocked: !u.blocked });
                              loadAll();
                              toast.success(u.blocked ? "Kullanıcı aktifleştirildi" : "Kullanıcı engellendi");
                            }}
                            className={`text-xs px-2 py-1 ${u.blocked ? "text-emerald-700 hover:underline" : "text-amber-700 hover:underline"}`}
                          >
                            {u.blocked ? "Aç" : "Engelle"}
                          </button>
                          <button
                            data-testid={`delete-user-${u.user_id}`}
                            onClick={async () => {
                              if (!confirm(`${u.email} kullanıcısını silmek istediğinize emin misiniz?`)) return;
                              await api.delete(`/admin/users/${u.user_id}`);
                              toast.success("Silindi");
                              loadAll();
                            }}
                            className="text-red-600 hover:text-red-700 p-1"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "companies" && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-[var(--brand-navy)]">Şirketler</h2>
              <Button data-testid="new-company-btn" onClick={() => setShowCompanyDialog(true)} className="bg-[var(--brand-navy)] text-white">
                <Plus className="w-4 h-4 mr-1" /> Yeni Şirket
              </Button>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {companies.map((c) => (
                <div key={c.company_id} className="bg-white border border-zinc-200 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="font-medium text-[var(--brand-navy)]">{c.name}</div>
                      <div className="text-xs text-zinc-500 font-mono mt-0.5">{c.company_id}</div>
                    </div>
                    <Badge className="bg-[var(--brand-gold-2)]/15 text-[var(--brand-navy)] hover:bg-[var(--brand-gold-2)]/15">
                      {c.user_count} üye
                    </Badge>
                  </div>
                  <div className="text-xs text-zinc-500 mb-1">Şirket Bütçesi</div>
                  <div className="text-2xl font-black tracking-tight text-zinc-950 mb-3">{fmtTRY(c.budget_balance)}</div>
                  <button
                    data-testid={`topup-company-${c.company_id}`}
                    onClick={() => setShowCompanyTopup(c)}
                    className="w-full text-sm text-white bg-[var(--brand-navy)] hover:opacity-90 py-2 rounded-md"
                  >
                    Bütçe Ekle
                  </button>
                </div>
              ))}
              {companies.length === 0 && <div className="text-zinc-500">Henüz şirket yok.</div>}
            </div>
          </div>
        )}

        {tab === "invites" && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-[var(--brand-navy)]">Davet Kodları</h2>
              <Button data-testid="new-invite-btn" onClick={() => setShowInviteDialog(true)} className="bg-[var(--brand-navy)] text-white">
                <Send className="w-4 h-4 mr-1" /> Yeni Davet
              </Button>
            </div>
            <div className="bg-white border border-zinc-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-zinc-50 border-b border-zinc-200">
                  <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                    <th className="p-3">Kod / Link</th>
                    <th className="p-3">Rol</th>
                    <th className="p-3">Şirket</th>
                    <th className="p-3">E-posta</th>
                    <th className="p-3">Durum</th>
                    <th className="p-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {invites.map((iv) => (
                    <tr key={iv.code} className="border-b border-zinc-100" data-testid={`invite-row-${iv.code}`}>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <code className="text-xs bg-zinc-100 px-2 py-1 rounded">{iv.code}</code>
                          <button
                            onClick={() => {
                              const url = `${window.location.origin}/join/${iv.code}`;
                              navigator.clipboard.writeText(url);
                              toast.success("Davet linki kopyalandı");
                            }}
                            className="text-zinc-500 hover:text-[var(--brand-navy)]"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                      <td className="p-3"><RoleBadge role={iv.role} /></td>
                      <td className="p-3 text-zinc-700 text-xs">{iv.company_id || "—"}</td>
                      <td className="p-3 text-zinc-700 text-xs">{iv.email || "—"}</td>
                      <td className="p-3">
                        {iv.used ? (
                          <Badge variant="secondary" className="text-[10px]">Kullanıldı</Badge>
                        ) : (
                          <Badge className="text-[10px] bg-blue-100 text-blue-800 hover:bg-blue-100">Aktif</Badge>
                        )}
                      </td>
                      <td className="p-3 text-right">
                        {!iv.used && (
                          <button
                            onClick={async () => {
                              await api.delete(`/admin/invites/${iv.code}`);
                              toast.success("İptal edildi");
                              loadAll();
                            }}
                            className="text-red-600 hover:text-red-700"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {invites.length === 0 && (
                    <tr><td colSpan={6} className="p-8 text-center text-zinc-500">Henüz davet yok</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* User Detail Drawer */}
      {selectedUser && (
        <UserDetailDialog
          data={selectedUser}
          onClose={() => setSelectedUser(null)}
          onOpenChat={(cid) => openChatDetail(selectedUser.user.user_id, cid)}
        />
      )}
      {selectedChat && <ChatViewerDialog data={selectedChat} onClose={() => setSelectedChat(null)} />}

      {/* Topup */}
      <TopupDialog
        target={showTopup}
        onClose={() => setShowTopup(false)}
        onDone={loadAll}
        endpoint={(uid) => `/admin/users/${uid}/wallet/topup`}
      />
      {/* Role change */}
      <RoleDialog
        target={showRoleDialog}
        companies={companies}
        onClose={() => setShowRoleDialog(false)}
        onDone={loadAll}
      />
      {/* New Company */}
      <NewCompanyDialog
        open={showCompanyDialog}
        onClose={() => setShowCompanyDialog(false)}
        onDone={loadAll}
      />
      {/* Company topup */}
      <CompanyTopupDialog
        company={showCompanyTopup}
        onClose={() => setShowCompanyTopup(null)}
        onDone={loadAll}
      />
      {/* New invite */}
      <InviteDialog
        open={showInviteDialog}
        companies={companies}
        onClose={() => setShowInviteDialog(false)}
        onDone={loadAll}
        isSuperAdmin
      />
    </div>
  );
}

function StatCard({ label, value, icon }) {
  return (
    <div className="bg-white rounded-lg border border-zinc-200 p-4">
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-black tracking-tight text-[var(--brand-navy)]">{value}</div>
    </div>
  );
}

function RoleBadge({ role }) {
  const r = role || "user";
  if (r === "super_admin")
    return <Badge className="bg-[var(--brand-gold)]/20 text-[var(--brand-navy)] hover:bg-[var(--brand-gold)]/20 text-[10px]">SÜPER ADMIN</Badge>;
  if (r === "admin")
    return <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100 text-[10px]">ADMIN</Badge>;
  return <Badge variant="secondary" className="text-[10px]">KULLANICI</Badge>;
}

function TopupDialog({ target, onClose, onDone, endpoint }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  if (!target) return null;
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(endpoint(target.user_id), { amount: Number(amount), note });
      toast.success("Bakiye eklendi");
      setAmount(""); setNote("");
      onDone(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!target} onOpenChange={onClose}>
      <DialogContent data-testid="topup-dialog">
        <DialogHeader>
          <DialogTitle>Bakiye Ekle · {target.name || target.email}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Mevcut Bakiye</Label>
            <div className="text-xl font-black">₺{Number(target.wallet_balance ?? 0).toFixed(2)}</div>
          </div>
          <div>
            <Label>Eklenecek Tutar (TL)</Label>
            <Input data-testid="topup-amount-input" type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div>
            <Label>Not (opsiyonel)</Label>
            <Input data-testid="topup-note-input" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>İptal</Button>
          <Button data-testid="topup-submit-btn" disabled={!amount || busy} onClick={submit} className="bg-[var(--brand-navy)] text-white">
            {busy ? "Ekleniyor..." : "Ekle"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RoleDialog({ target, companies, onClose, onDone }) {
  const [role, setRole] = useState("user");
  const [companyId, setCompanyId] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (target) {
      setRole(target.role || "user");
      setCompanyId(target.company_id || "");
    }
  }, [target]);
  if (!target) return null;
  const submit = async () => {
    setBusy(true);
    try {
      const payload = { role };
      if (role === "admin") {
        if (companyId) payload.company_id = companyId;
        else if (companyName) payload.company_name = companyName;
      }
      await api.post(`/admin/users/${target.user_id}/role`, payload);
      toast.success("Rol güncellendi");
      onDone(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!target} onOpenChange={onClose}>
      <DialogContent data-testid="role-dialog">
        <DialogHeader><DialogTitle>Rol Değiştir · {target.email}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Rol</Label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full border border-zinc-300 rounded-md px-3 py-2" data-testid="role-select">
              <option value="user">Kullanıcı</option>
              <option value="admin">Admin (Şirket Yöneticisi)</option>
              <option value="super_admin">Süper Admin</option>
            </select>
          </div>
          {role === "admin" && (
            <>
              <div>
                <Label>Mevcut Şirket Seç (opsiyonel)</Label>
                <select value={companyId} onChange={(e) => setCompanyId(e.target.value)} className="w-full border border-zinc-300 rounded-md px-3 py-2">
                  <option value="">— Yeni şirket oluştur —</option>
                  {companies.map((c) => (<option key={c.company_id} value={c.company_id}>{c.name}</option>))}
                </select>
              </div>
              {!companyId && (
                <div>
                  <Label>Yeni Şirket Adı</Label>
                  <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="ör. Örnek Değerleme A.Ş." />
                </div>
              )}
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>İptal</Button>
          <Button data-testid="role-submit-btn" disabled={busy} onClick={submit} className="bg-[var(--brand-navy)] text-white">Kaydet</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewCompanyDialog({ open, onClose, onDone }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/admin/companies", { name });
      toast.success("Şirket oluşturuldu");
      setName(""); onDone(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader><DialogTitle>Yeni Şirket</DialogTitle></DialogHeader>
        <div>
          <Label>Şirket Adı</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Örnek Değerleme A.Ş." data-testid="company-name-input" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>İptal</Button>
          <Button disabled={!name || busy} onClick={submit} className="bg-[var(--brand-navy)] text-white" data-testid="company-create-btn">Oluştur</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompanyTopupDialog({ company, onClose, onDone }) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  if (!company) return null;
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/companies/${company.company_id}/budget/topup`, { amount: Number(amount) });
      toast.success("Şirket bütçesi güncellendi");
      setAmount(""); onDone(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!company} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader><DialogTitle>Bütçe Ekle · {company.name}</DialogTitle></DialogHeader>
        <div>
          <div className="text-sm text-zinc-500 mb-2">Mevcut bütçe: ₺{Number(company.budget_balance ?? 0).toFixed(2)}</div>
          <Label>Eklenecek (TL)</Label>
          <Input type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="company-topup-amount" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>İptal</Button>
          <Button disabled={!amount || busy} onClick={submit} className="bg-[var(--brand-navy)] text-white">Ekle</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function InviteDialog({ open, companies, onClose, onDone, isSuperAdmin }) {
  const [role, setRole] = useState("user");
  const [companyId, setCompanyId] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const submit = async () => {
    setBusy(true);
    try {
      const payload = { role, email: email || undefined, origin_url: window.location.origin };
      if (isSuperAdmin) {
        if (companyId) payload.company_id = companyId;
        else if (companyName) payload.company_name = companyName;
      }
      const { data } = await api.post("/admin/invites", payload);
      setResult({ ...data.invite, email_sent: data.email_sent, email_error: data.email_error });
      if (data.email_sent) toast.success("Davet e-postası gönderildi");
      else if (data.email_error) toast.warning("Davet oluşturuldu — e-posta gönderilemedi: " + data.email_error);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "İşlem başarısız");
    } finally { setBusy(false); }
  };
  const reset = () => { setRole("user"); setCompanyId(""); setCompanyName(""); setEmail(""); setResult(null); };
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { reset(); onClose(); } }}>
      <DialogContent data-testid="invite-dialog">
        <DialogHeader><DialogTitle>Yeni Davet Oluştur</DialogTitle></DialogHeader>
        {!result ? (
          <div className="space-y-3">
            <div>
              <Label>Rol</Label>
              <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full border border-zinc-300 rounded-md px-3 py-2" data-testid="invite-role-select">
                <option value="user">Kullanıcı</option>
                {isSuperAdmin && <option value="admin">Admin (Şirket Yöneticisi)</option>}
              </select>
            </div>
            {isSuperAdmin && (
              <>
                <div>
                  <Label>Şirket (opsiyonel)</Label>
                  <select value={companyId} onChange={(e) => setCompanyId(e.target.value)} className="w-full border border-zinc-300 rounded-md px-3 py-2">
                    <option value="">— Şirket yok / yeni oluştur —</option>
                    {companies.map((c) => (<option key={c.company_id} value={c.company_id}>{c.name}</option>))}
                  </select>
                </div>
                {!companyId && role === "admin" && (
                  <div>
                    <Label>Yeni Şirket Adı</Label>
                    <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
                  </div>
                )}
              </>
            )}
            <div>
              <Label>E-posta (opsiyonel · davet bu adrese kilitlensin)</Label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@company.com" data-testid="invite-email-input" />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-sm text-zinc-700">Davet bağlantısı oluşturuldu. Kopyalayıp gönderin:</div>
            <div className="bg-zinc-50 border border-zinc-200 rounded-md p-3 flex items-center gap-2">
              <code className="flex-1 text-xs break-all">{window.location.origin}/join/{result.code}</code>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/join/${result.code}`);
                  toast.success("Kopyalandı");
                }}
                className="text-[var(--brand-navy)]"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
            {result.email_sent && (
              <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-md p-2">
                ✓ Davet e-postası gönderildi
              </div>
            )}
            {result.email_error && (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
                E-posta gönderilemedi: {result.email_error}
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          {!result ? (
            <>
              <Button variant="outline" onClick={onClose}>İptal</Button>
              <Button disabled={busy} onClick={submit} className="bg-[var(--brand-navy)] text-white" data-testid="invite-submit-btn">Oluştur</Button>
            </>
          ) : (
            <Button onClick={() => { reset(); onClose(); }} className="bg-[var(--brand-navy)] text-white">Kapat</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UserDetailDialog({ data, onClose, onOpenChat }) {
  const { user, chats, wallet_transactions } = data;
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl" data-testid="user-detail-dialog">
        <DialogHeader>
          <DialogTitle>{user.name || user.email}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
          <div className="bg-zinc-50 p-3 rounded"><div className="text-xs text-zinc-500">Cüzdan</div><div className="text-lg font-bold">₺{Number(user.wallet_balance || 0).toFixed(2)}</div></div>
          <div className="bg-zinc-50 p-3 rounded"><div className="text-xs text-zinc-500">Rol</div><RoleBadge role={user.role} /></div>
        </div>
        <div className="grid grid-cols-2 gap-4 max-h-[500px] overflow-y-auto">
          <div>
            <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">Sohbetler ({chats.length})</div>
            <div className="space-y-1">
              {chats.map((c) => (
                <button
                  key={c.chat_id}
                  onClick={() => onOpenChat(c.chat_id)}
                  className="w-full text-left text-xs p-2 border border-zinc-200 rounded hover:bg-zinc-50"
                  data-testid={`user-chat-${c.chat_id}`}
                >
                  <div className="font-medium truncate">{c.title}</div>
                  <div className="text-zinc-500 flex justify-between">
                    <span>{c.mode === "faq" ? "FAQ" : (c.template_name || "Rapor")}</span>
                    <span>{c.status === "completed" ? "✓" : "..."}</span>
                  </div>
                </button>
              ))}
              {chats.length === 0 && <div className="text-xs text-zinc-500">Sohbet yok</div>}
            </div>
          </div>
          <div>
            <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">Cüzdan İşlemleri</div>
            <div className="space-y-1">
              {wallet_transactions.map((tx) => (
                <div key={tx.ledger_id} className="text-xs p-2 border border-zinc-200 rounded">
                  <div className="flex justify-between"><span className="text-emerald-700 font-bold">+₺{Number(tx.amount).toFixed(2)}</span><span className="text-zinc-500">{new Date(tx.created_at).toLocaleDateString("tr-TR")}</span></div>
                  <div className="text-zinc-500">{tx.note || tx.type}</div>
                </div>
              ))}
              {wallet_transactions.length === 0 && <div className="text-xs text-zinc-500">Kayıt yok</div>}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ChatViewerDialog({ data, onClose }) {
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl" data-testid="chat-viewer-dialog">
        <DialogHeader><DialogTitle>{data.chat.title}</DialogTitle></DialogHeader>
        <div className="max-h-[500px] overflow-y-auto space-y-3">
          {data.messages.map((m) => (
            <div key={m.message_id} className={`p-3 rounded text-sm ${m.role === "user" ? "bg-blue-50" : "bg-zinc-50"}`}>
              <div className="text-[10px] font-mono uppercase text-zinc-500 mb-1">{m.role}</div>
              <div className="whitespace-pre-wrap">{m.content}</div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
