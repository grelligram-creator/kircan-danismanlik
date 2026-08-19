import { Button } from "@/components/ui/button";
import { ArrowRight, Building2, ScanLine, FileText } from "lucide-react";

export default function Login() {
  const handleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="h-screen w-full flex flex-col lg:flex-row bg-white overflow-hidden">
      {/* Left / Hero */}
      <div
        className="hidden lg:flex lg:w-7/12 h-full relative bg-zinc-950 text-white p-14 flex-col justify-between"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0,0,0,0.55), rgba(0,0,0,0.75)), url('https://images.pexels.com/photos/37853255/pexels-photo-37853255.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940')",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-white/10 backdrop-blur-sm flex items-center justify-center">
            <Building2 className="w-5 h-5" />
          </div>
          <span className="text-sm font-mono uppercase tracking-[0.25em]">Valura AI</span>
        </div>

        <div className="max-w-2xl">
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-white/60 mb-6">
            Gayrimenkul Değerleme Zekası
          </div>
          <h1 className="font-light text-5xl xl:text-6xl leading-[0.95] tracking-tighter mb-8">
            Raporlarınızı<br />
            <span className="italic font-serif">konuşarak</span> hazırlayın.
          </h1>
          <p className="text-white/70 text-lg leading-relaxed max-w-lg">
            SPK standartlarında değerleme raporlarını AI ile sırasıyla doldurun. PDF, Excel, Word yükleyin —
            sistem taslaklarınıza otomatik yerleştirsin.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-6 text-white/80 max-w-2xl">
          <FeatureItem icon={<ScanLine className="w-4 h-4" />} title="Doküman Analizi" text="PDF · Excel · Word" />
          <FeatureItem icon={<FileText className="w-4 h-4" />} title="Çoklu Rapor" text="Konut · Ticari · Arsa" />
          <FeatureItem icon={<Building2 className="w-4 h-4" />} title="Anlık Önizleme" text="Yazarken şekillenir" />
        </div>
      </div>

      {/* Right / Auth */}
      <div className="w-full lg:w-5/12 h-full flex flex-col justify-center px-8 sm:px-16 lg:px-20 xl:px-28 bg-white">
        <div className="lg:hidden flex items-center gap-3 mb-10">
          <div className="w-8 h-8 rounded-md bg-zinc-950 flex items-center justify-center">
            <Building2 className="w-4 h-4 text-white" />
          </div>
          <span className="text-sm font-mono uppercase tracking-[0.25em]">Valura AI</span>
        </div>

        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500 mb-4">Giriş</div>
        <h2 className="text-3xl sm:text-4xl tracking-tight font-light text-zinc-950 leading-tight mb-4">
          Değerleme uzmanları için<br />
          <span className="text-zinc-500">yapay zeka asistanı</span>
        </h2>
        <p className="text-zinc-600 text-sm leading-relaxed mb-10 max-w-md">
          Google hesabınızla giriş yaparak dakikalar içinde profesyonel değerleme raporları oluşturmaya başlayın.
          Yeni kullanıcılar 100 kredi ile başlar.
        </p>

        <Button
          data-testid="google-login-btn"
          onClick={handleLogin}
          size="lg"
          className="w-full max-w-md h-14 bg-zinc-950 text-white hover:bg-zinc-800 rounded-md group transition-colors"
        >
          <span className="flex-1 text-left text-base">Google ile devam et</span>
          <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
        </Button>

        <div className="mt-10 flex items-center gap-4 text-xs font-mono uppercase tracking-[0.2em] text-zinc-400">
          <div className="w-8 h-px bg-zinc-300" />
          Emergent Google Auth
        </div>
      </div>
    </div>
  );
}

function FeatureItem({ icon, title, text }) {
  return (
    <div>
      <div className="w-8 h-8 rounded-md bg-white/10 flex items-center justify-center mb-2">{icon}</div>
      <div className="text-xs font-mono uppercase tracking-widest">{title}</div>
      <div className="text-xs text-white/60 mt-1">{text}</div>
    </div>
  );
}
