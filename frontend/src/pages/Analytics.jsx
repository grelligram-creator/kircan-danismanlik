import { useEffect, useState, useCallback } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { api, API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ArrowLeft, TrendingUp, FileText, MessageSquare, Wallet, Target, Building2, Download, CalendarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { toast } from "sonner";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

const fmtTRY = (n) =>
  `₺${Number(n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

const toIsoDate = (d) => {
  if (!d) return null;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

const RANGE_PRESETS = [
  { id: "7", label: "7 Gün" },
  { id: "30", label: "30 Gün" },
  { id: "90", label: "90 Gün" },
  { id: "custom", label: "Özel" },
];

export default function Analytics() {
  const { user, loading } = useAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [rangeId, setRangeId] = useState("30");
  const [customRange, setCustomRange] = useState({ from: undefined, to: undefined });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [exporting, setExporting] = useState(false);
  const navigate = useNavigate();

  const buildQuery = useCallback(() => {
    if (rangeId === "custom" && customRange.from && customRange.to) {
      return { date_from: toIsoDate(customRange.from), date_to: toIsoDate(customRange.to) };
    }
    if (rangeId !== "custom") return { days: rangeId };
    return null; // custom without picks yet
  }, [rangeId, customRange]);

  const fetchData = useCallback(async () => {
    const q = buildQuery();
    if (!q) return;
    setFetching(true);
    setErr(null);
    try {
      const { data } = await api.get("/analytics/summary", { params: q });
      setData(data);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Analitik yüklenemedi");
    } finally {
      setFetching(false);
    }
  }, [buildQuery]);

  useEffect(() => {
    if (!user) return;
    fetchData();
  }, [user, fetchData]);

  const downloadCsv = () => {
    const q = buildQuery();
    if (!q) {
      toast.error("Önce bir tarih aralığı seçin");
      return;
    }
    setExporting(true);
    const params = new URLSearchParams(q).toString();
    // Open in new tab so browser handles the download; credentials sent via cookie
    const url = `${API}/analytics/export.csv?${params}`;
    const a = document.createElement("a");
    a.href = url;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => setExporting(false), 800);
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-zinc-50">
        <div className="text-zinc-500 text-sm font-mono uppercase tracking-widest">Yükleniyor...</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/" replace />;

  const rangeLabel = () => {
    if (rangeId === "custom") {
      if (customRange.from && customRange.to)
        return `${toIsoDate(customRange.from)} → ${toIsoDate(customRange.to)}`;
      return "Tarih aralığı seçin";
    }
    return `Son ${rangeId} Gün`;
  };

  return (
    <div className="min-h-screen bg-zinc-50 font-body" data-testid="analytics-page">
      {/* Header */}
      <div className="border-b border-zinc-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/dashboard")}
              data-testid="back-to-dashboard-btn"
              className="text-zinc-600 hover:text-zinc-950"
            >
              <ArrowLeft className="w-4 h-4 mr-1.5" /> Panel
            </Button>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500">Kullanım Analitiği</div>
              <h1 className="text-xl tracking-tight font-medium text-zinc-950">{rangeLabel()}</h1>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">Mevcut Bakiye</div>
            <div className="font-black text-xl tracking-tight text-zinc-950">
              {fmtTRY(data?.wallet_balance ?? user?.wallet_balance)}
            </div>
          </div>
        </div>

        {/* Toolbar */}
        <div className="max-w-6xl mx-auto px-6 pb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex border border-zinc-200 rounded-md overflow-hidden bg-white" data-testid="range-selector">
            {RANGE_PRESETS.map((p) => (
              <button
                key={p.id}
                data-testid={`range-${p.id}`}
                onClick={() => setRangeId(p.id)}
                className={`px-4 py-1.5 text-sm border-r border-zinc-200 last:border-r-0 transition-colors ${
                  rangeId === p.id ? "bg-zinc-950 text-white" : "hover:bg-zinc-50 text-zinc-700"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {rangeId === "custom" && (
              <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" data-testid="date-range-picker">
                    <CalendarIcon className="w-3.5 h-3.5 mr-1.5" />
                    {customRange.from && customRange.to
                      ? `${toIsoDate(customRange.from)} — ${toIsoDate(customRange.to)}`
                      : "Tarih Aralığı Seç"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="end">
                  <Calendar
                    mode="range"
                    selected={customRange}
                    onSelect={(r) => {
                      setCustomRange(r || { from: undefined, to: undefined });
                      if (r?.from && r?.to) {
                        setPickerOpen(false);
                      }
                    }}
                    numberOfMonths={2}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={downloadCsv}
              disabled={exporting || fetching || !data}
              data-testid="csv-export-btn"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              {exporting ? "İndiriliyor..." : "CSV İndir"}
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {err && (
          <div className="border border-red-200 bg-red-50 text-red-700 rounded-md px-4 py-3 text-sm">{err}</div>
        )}
        {fetching && !data && (
          <div className="text-zinc-500 text-sm font-mono uppercase tracking-widest">Veriler getiriliyor...</div>
        )}
        {!data && !fetching && !err && rangeId === "custom" && (
          <div className="text-zinc-500 text-sm italic">
            Devam etmek için yukarıdan bir tarih aralığı seçin.
          </div>
        )}

        {data && (
          <>
            {/* KPI Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="kpi-grid">
              <KpiCard
                icon={<Wallet className="w-3.5 h-3.5" />}
                label="Toplam Harcama"
                value={fmtTRY(data.totals.spent)}
                sub={data.totals.topped_up ? `Yüklenen: ${fmtTRY(data.totals.topped_up)}` : "yükleme yok"}
              />
              <KpiCard
                icon={<FileText className="w-3.5 h-3.5" />}
                label="Tamamlanan Rapor"
                value={data.totals.reports_completed}
                sub={`${data.totals.reports_total} toplam · %${data.kpis.completion_rate_pct} tamamlama`}
              />
              <KpiCard
                icon={<MessageSquare className="w-3.5 h-3.5" />}
                label="AI Mesajı"
                value={data.totals.messages}
                sub={`${data.totals.faq_conversations} FAQ sohbeti`}
              />
              <KpiCard
                icon={<Target className="w-3.5 h-3.5" />}
                label="Rapor Başı Ort."
                value={fmtTRY(data.kpis.avg_spend_per_report)}
                sub="tamamlanan rapor başına"
              />
            </div>

            {/* Chart */}
            <section className="bg-white border border-zinc-200 rounded-md p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">Grafik</div>
                  <h2 className="text-lg font-medium tracking-tight text-zinc-950">Günlük Harcama</h2>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                  <TrendingUp className="w-3.5 h-3.5" />
                  <span className="font-mono">TL · {data.window_days}g</span>
                </div>
              </div>
              <div className="h-64" data-testid="daily-chart">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={200}>
                  <AreaChart data={data.daily_spend} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="gSpend" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#0055FF" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#0055FF" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(d) => d.slice(5)}
                      stroke="#a1a1aa"
                      fontSize={11}
                      interval={Math.max(0, Math.floor(data.daily_spend.length / 8))}
                    />
                    <YAxis stroke="#a1a1aa" fontSize={11} width={40} />
                    <Tooltip
                      contentStyle={{ borderRadius: 6, border: "1px solid #e4e4e7", fontSize: 12 }}
                      formatter={(v) => [fmtTRY(v), "Harcama"]}
                      labelFormatter={(l) => new Date(l).toLocaleDateString("tr-TR")}
                    />
                    <Area type="monotone" dataKey="amount" stroke="#0055FF" strokeWidth={2} fill="url(#gSpend)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Two column */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <section className="lg:col-span-1 bg-white border border-zinc-200 rounded-md p-6">
                <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-1">
                  Tercih Edilen
                </div>
                <h2 className="text-lg font-medium tracking-tight text-zinc-950 mb-4">En Çok Kullanılan Şablon</h2>
                {data.preferred_template ? (
                  <div>
                    <div className="w-10 h-10 rounded-md bg-zinc-950 text-white flex items-center justify-center mb-3">
                      <Building2 className="w-5 h-5" />
                    </div>
                    <div className="font-medium text-zinc-950 text-lg">{data.preferred_template.name}</div>
                    <div className="mt-4 space-y-2 text-sm">
                      <Metric label="Tamamlanan Rapor" value={data.preferred_template.reports_completed} />
                      <Metric label="Toplam Mesaj" value={data.preferred_template.messages} />
                      <Metric label="Harcama" value={fmtTRY(data.preferred_template.spent)} />
                    </div>
                  </div>
                ) : (
                  <div className="text-zinc-500 text-sm italic">Bu dönemde veri yok.</div>
                )}
              </section>

              <section className="lg:col-span-2 bg-white border border-zinc-200 rounded-md p-6">
                <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-1">Dağılım</div>
                <h2 className="text-lg font-medium tracking-tight text-zinc-950 mb-4">Şablon Bazında Kullanım</h2>
                {data.template_breakdown.length === 0 ? (
                  <div className="text-zinc-500 text-sm italic">Bu dönemde kullanım kaydı yok.</div>
                ) : (
                  <div className="border border-zinc-200 rounded-md overflow-hidden" data-testid="template-breakdown">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-zinc-50 text-left text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                          <th className="px-3 py-2 border-b border-zinc-200">Şablon</th>
                          <th className="px-3 py-2 border-b border-zinc-200 text-right">Mesaj</th>
                          <th className="px-3 py-2 border-b border-zinc-200 text-right">Rapor</th>
                          <th className="px-3 py-2 border-b border-zinc-200 text-right">Harcama</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.template_breakdown.map((t) => (
                          <tr key={t.template_id} className="hover:bg-zinc-50 transition-colors">
                            <td className="px-3 py-2.5 border-b border-zinc-100 text-zinc-950">{t.name}</td>
                            <td className="px-3 py-2.5 border-b border-zinc-100 text-right font-mono text-zinc-700">
                              {t.messages}
                            </td>
                            <td className="px-3 py-2.5 border-b border-zinc-100 text-right font-mono text-zinc-700">
                              {t.reports_completed}/{t.reports_total}
                            </td>
                            <td className="px-3 py-2.5 border-b border-zinc-100 text-right font-mono font-medium text-zinc-950">
                              {fmtTRY(t.spent)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub }) {
  return (
    <div className="bg-white border border-zinc-200 rounded-md p-5" data-testid={`kpi-${label}`}>
      <div className="flex items-center gap-2 text-zinc-500 mb-3">
        {icon}
        <span className="text-[10px] font-mono uppercase tracking-[0.2em]">{label}</span>
      </div>
      <div className="font-black text-3xl tracking-tight text-zinc-950">{value}</div>
      <div className="text-xs text-zinc-500 mt-1.5">{sub}</div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="font-mono font-medium text-zinc-950">{value}</span>
    </div>
  );
}
