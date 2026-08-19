import { Building2 } from "lucide-react";

/**
 * KırCan Danışmanlık brand mark.
 * variant: 'dark' shows the logo image; 'light' shows a compact wordmark.
 */
export default function BrandLogo({ variant = "compact", className = "" }) {
  if (variant === "full") {
    return (
      <div className={`inline-flex items-center gap-3 ${className}`}>
        <img src="/kircan-logo.jpg" alt="KırCan Danışmanlık" className="h-10 w-auto rounded" />
      </div>
    );
  }
  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <div className="w-8 h-8 rounded-md overflow-hidden flex items-center justify-center bg-[var(--brand-navy)] ring-1 ring-[var(--brand-gold)]/50">
        <img src="/kircan-logo.jpg" alt="KırCan" className="w-full h-full object-cover" />
      </div>
      <div className="leading-tight">
        <div className="text-xs font-mono uppercase tracking-[0.22em] text-[var(--brand-navy)]">KırCan</div>
        <div className="text-[9px] text-zinc-500 -mt-0.5">Danışmanlık · Değerleme</div>
      </div>
    </div>
  );
}

export function PoweredBy({ className = "" }) {
  return (
    <div className={`text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-400 ${className}`}>
      Powered by <span className="text-[var(--brand-gold-2)] font-medium">Algorisma</span>
    </div>
  );
}
