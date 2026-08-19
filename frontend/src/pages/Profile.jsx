import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowLeft, User as UserIcon, Wallet, Building2, Save } from "lucide-react";
import { toast } from "sonner";

export default function Profile() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  // Sync when auth resolves (name is empty on first render because user is null while /auth/me is pending)
  useEffect(() => {
    if (user?.name) setName(user.name);
  }, [user]);

  if (!user) return null;

  const save = async () => {
    setBusy(true);
    try {
      await api.patch("/auth/me", { name });
      await refreshUser();
      toast.success("Profil güncellendi");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Güncelleme başarısız");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="profile-page">
      <header className="border-b border-zinc-200 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-4">
          <button onClick={() => navigate("/dashboard")} className="text-zinc-500 hover:text-zinc-950" data-testid="profile-back-btn">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-[var(--brand-navy)] flex items-center justify-center ring-1 ring-[var(--brand-gold)]/40">
              <UserIcon className="w-5 h-5 text-[var(--brand-gold-2)]" />
            </div>
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.28em] text-[var(--brand-gold-2)]">Hesap</div>
              <div className="text-lg font-medium text-[var(--brand-navy)]">Profil Ayarları</div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-4">
        <div className="bg-white border border-zinc-200 rounded-lg p-6">
          <div className="flex items-center gap-4 mb-6">
            {user.picture ? (
              <img src={user.picture} alt="" className="w-16 h-16 rounded-full ring-2 ring-[var(--brand-gold)]/30" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-[var(--brand-navy)] text-white text-2xl flex items-center justify-center">
                {user.name?.[0] || "K"}
              </div>
            )}
            <div>
              <div className="text-sm text-zinc-500">Google hesabı ile giriş yaptınız</div>
              <div className="text-base font-medium">{user.email}</div>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <Label>Ad Soyad</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="profile-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>E-posta</Label>
                <Input value={user.email} disabled className="bg-zinc-50" />
                <div className="text-[10px] text-zinc-500 mt-1">Google Auth ile yönetilir</div>
              </div>
              <div>
                <Label>Rol</Label>
                <Input value={(user.role || "user").toUpperCase()} disabled className="bg-zinc-50 uppercase" />
              </div>
            </div>
            <div className="flex justify-end">
              <Button onClick={save} disabled={busy || !name.trim()} className="bg-[var(--brand-navy)] text-white" data-testid="profile-save-btn">
                <Save className="w-4 h-4 mr-1" />
                {busy ? "Kaydediliyor..." : "Kaydet"}
              </Button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white border border-zinc-200 rounded-lg p-4">
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">
              <Wallet className="w-3.5 h-3.5" /> Cüzdan
            </div>
            <div className="text-2xl font-black text-[var(--brand-navy)]">₺{Number(user.wallet_balance ?? 0).toFixed(2)}</div>
          </div>
          <div className="bg-white border border-zinc-200 rounded-lg p-4">
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-2">
              <Building2 className="w-3.5 h-3.5" /> Şirket
            </div>
            <div className="text-lg font-medium text-[var(--brand-navy)]">{user.company_name || "—"}</div>
          </div>
        </div>
      </main>
    </div>
  );
}
