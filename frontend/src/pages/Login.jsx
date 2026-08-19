import { Button } from "@/components/ui/button";
import { ArrowRight, ScanLine, FileText, Building2 } from "lucide-react";
import { PoweredBy } from "@/components/BrandLogo";

export default function Login() {
  const handleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="h-screen w-full flex flex-col lg:flex-row bg-white overflow-hidden">
      {/* Left / Hero — KırCan brand navy + gold */}
      <div
        className="hidden lg:flex lg:w-7/12 h-full relative text-white p-14 flex-col justify-between"
        style={{
          background: "linear-gradient(135deg, #081a30 0%, #0b2340 45%, #0e2a4d 100%)",
        }}
      >
        <div className="absolute inset-0 opacity-[0.06]" style={{
          backgroundImage: "radial-gradient(#d4af37 1px, transparent 1px)",
          backgroundSize: "22px 22px",
        }} />

        <div className="relative flex items-center gap-3">
          <img src="/kircan-logo.jpg" alt="KırCan" className="h-14 w-auto rounded-md ring-1 ring-white/10" />
          <div>
            <div className="text-sm font-mono uppercase tracking-[0.28em] text-[#d4af37]">KırCan</div>
            <div className="text-[10px] text-white/60 tracking-widest uppercase">Danışmanlık · Eğitim · Değerleme</div>
          </div>
        </div>

        <div className="relative max-w-2xl">
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-[#d4af37]/80 mb-6">
            Gayrimenkul Değerleme AI
          </div>
          <h1 className="font-light text-5xl xl:text-6xl leading-[0.95] tracking-tighter mb-8">
            Raporlarınızı<br />
            <span className="italic font-serif text-[#d4af37]">konuşarak</span> hazırlayın.
          </h1>
          <p className="text-white/70 text-lg leading-relaxed max-w-lg">
            SPK standartlarında değerleme raporlarını AI ile sırayla doldurun. Word şablonlarınızı yükleyin —
            sistem KırCan Danışmanlık için özel olarak hazırlandı.
          </p>
        </div>

        <div className="relative grid grid-cols-3 gap-6 text-white/80 max-w-2xl">
          <FeatureItem icon={<ScanLine className="w-4 h-4" />} title="Doküman Analizi" text="PDF · Excel · Word" />
          <FeatureItem icon={<FileText className="w-4 h-4" />} title="40+ Rapor Türü" text="Konut · Ticari · Arsa" />
          <FeatureItem icon={<Building2 className="w-4 h-4" />} title="Anlık Önizleme" text="Yazarken şekillenir" />
        </div>
      </div>

      {/* Right / Auth */}
      <div className="w-full lg:w-5/12 h-full flex flex-col justify-center px-8 sm:px-16 lg:px-20 xl:px-28 bg-white relative">
        <div className="lg:hidden flex items-center gap-3 mb-10">
          <img src="/kircan-logo.jpg" alt="KırCan" className="h-10 w-auto rounded" />
          <span className="text-sm font-mono uppercase tracking-[0.25em] text-[var(--brand-navy)]">KırCan</span>
        </div>

        <div className="text-xs font-mono uppercase tracking-[0.3em] text-[var(--brand-gold-2)] mb-4">Giriş</div>
        <h2 className="text-3xl sm:text-4xl tracking-tight font-light text-[var(--brand-navy)] leading-tight mb-4">
          Değerleme uzmanları için<br />
          <span className="text-zinc-500">yapay zeka asistanı</span>
        </h2>
        <p className="text-zinc-600 text-sm leading-relaxed mb-10 max-w-md">
          Google hesabınızla giriş yaparak dakikalar içinde profesyonel değerleme raporları oluşturmaya başlayın.
          Yeni kullanıcılar 50 TL cüzdan bakiyesiyle başlar.
        </p>

        <Button
          data-testid="google-login-btn"
          onClick={handleLogin}
          size="lg"
          className="w-full max-w-md h-14 text-white rounded-md group transition-colors"
          style={{ backgroundColor: "var(--brand-navy)" }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#0e2a4d")}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--brand-navy)")}
        >
          <span className="flex-1 text-left text-base">Google ile devam et</span>
          <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
        </Button>

        <div className="mt-10 flex items-center gap-4 text-xs font-mono uppercase tracking-[0.2em] text-zinc-400">
          <div className="w-8 h-px bg-zinc-300" />
          Emergent Google Auth
        </div>

        <div className="absolute bottom-6 left-0 right-0 flex justify-center">
          <PoweredBy />
        </div>
      </div>
    </div>
  );
}

function FeatureItem({ icon, title, text }) {
  return (
    <div>
      <div className="w-8 h-8 rounded-md bg-[#d4af37]/15 text-[#d4af37] flex items-center justify-center mb-2">{icon}</div>
      <div className="text-xs font-mono uppercase tracking-widest text-white/90">{title}</div>
      <div className="text-xs text-white/60 mt-1">{text}</div>
    </div>
  );
}
