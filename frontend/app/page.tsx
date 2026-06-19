"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type FloatPoint = { date: string; float_paise: number; float_display: string };
type Exception = {
  id: number; txn_id: number | null; status: string;
  amount_paise: number | null; amount_display: string | null; note: string;
};
type Balance = {
  accounts: Record<string, number>;
  total: number; balanced: boolean;
};
type Summary = Record<string, number>;

const STATUS_BADGE: Record<string, string> = {
  MISSING: "badge-missing",
  DUPLICATE: "badge-duplicate",
  FEE_DRIFT: "badge-fee-drift",
  AMOUNT_MISMATCH: "badge-amount-mismatch",
  MATCHED: "badge-matched",
  ORPHAN: "badge-orphan",
};

function formatPaise(paise: number): string {
  const rupees = paise / 100;
  const abs = Math.abs(rupees);
  const sign = rupees < 0 ? "-" : "";
  if (abs >= 10000000) return `${sign}₹${(abs / 10000000).toFixed(2)}Cr`;
  if (abs >= 100000) return `${sign}₹${(abs / 100000).toFixed(2)}L`;
  return `${sign}₹${abs.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};
const ease = [0.22, 1, 0.36, 1] as const;
const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease } },
};

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="card" style={{ padding: "12px 16px", border: "1px solid var(--hairline)" }}>
      <p className="text-xs" style={{ color: "var(--mute)" }}>{label}</p>
      <p className="mono text-sm font-semibold" style={{ color: val < 0 ? "var(--danger)" : "var(--primary)" }}>
        {formatPaise(val)}
      </p>
    </div>
  );
}

export default function Dashboard() {
  const [floatData, setFloatData] = useState<FloatPoint[]>([]);
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [summary, setSummary] = useState<Summary>({});
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);

  const fetchData = useCallback(async () => {
    const [f, e, b, s] = await Promise.all([
      fetch(`${API}/float/daily`).then(r => r.json()),
      fetch(`${API}/recon/exceptions`).then(r => r.json()),
      fetch(`${API}/ledger/balance`).then(r => r.json()),
      fetch(`${API}/recon/summary`).then(r => r.json()),
    ]);
    setFloatData(f);
    setExceptions(e);
    setBalance(b);
    setSummary(s);
    setReady(true);
  }, []);

  const runPipeline = async () => {
    setLoading(true);
    setReady(false);
    await fetch(`${API}/pipeline`, { method: "POST" });
    await fetchData();
    setLoading(false);
  };

  useEffect(() => {
    fetchData().catch(() => {});
  }, [fetchData]);

  const minFloat = floatData.length ? Math.min(...floatData.map(d => d.float_paise)) : 0;

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8 md:px-12 md:py-12">
      {/* Header — Voltagent hero-band style */}
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease }}
        className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-10"
      >
        <div>
          <p className="text-xs font-semibold tracking-[2.5px] uppercase mb-2" style={{ color: "var(--primary)" }}>
            SETTLEMENT RECONCILIATION
          </p>
          <h1 className="text-4xl md:text-5xl font-normal tracking-tight" style={{ color: "var(--ink-strong)", letterSpacing: "-0.65px" }}>
            tplus
          </h1>
          <p className="mt-2 text-sm" style={{ color: "var(--body)" }}>
            T+1 / T+2 settlement float gap · modeled scenario
          </p>
        </div>
        <button
          onClick={runPipeline}
          disabled={loading}
          className="h-11 px-6 text-sm font-semibold rounded-md transition-all duration-200 cursor-pointer disabled:opacity-50"
          style={{ background: "var(--primary)", color: "var(--canvas)" }}
        >
          {loading ? "Running pipeline…" : "Run Pipeline"}
        </button>
      </motion.header>

      {/* Trial Balance Strip */}
      <AnimatePresence>
        {balance && (
          <motion.div
            variants={stagger} initial="hidden" animate="show"
            className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8"
          >
            {Object.entries(balance.accounts).map(([name, val]) => (
              <motion.div key={name} variants={fadeUp} className="card card-glow">
                <p className="text-[10px] font-semibold tracking-[2px] uppercase mb-2" style={{ color: "var(--mute)" }}>
                  {name.replace(/_/g, " ")}
                </p>
                <p className="mono text-lg font-semibold" style={{ color: val < 0 ? "var(--danger)" : "var(--ink)" }}>
                  {formatPaise(val)}
                </p>
              </motion.div>
            ))}
            <motion.div variants={fadeUp}
              className={`card ${balance.balanced ? "pulse-green" : ""}`}
              style={{ borderColor: balance.balanced ? "var(--primary)" : "var(--danger)" }}
            >
              <p className="text-[10px] font-semibold tracking-[2px] uppercase mb-2" style={{ color: "var(--mute)" }}>
                INVARIANT
              </p>
              <p className="mono text-lg font-semibold" style={{ color: balance.balanced ? "var(--primary)" : "var(--danger)" }}>
                {balance.balanced ? "Balanced ✓" : `Off by ${formatPaise(balance.total)}`}
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Float Curve — the money shot */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={ready ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7, delay: 0.2, ease }}
        className="card card-glow mb-8"
      >
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-[10px] font-semibold tracking-[2px] uppercase" style={{ color: "var(--mute)" }}>
              DAILY FLOAT EXPOSURE
            </p>
            <p className="text-2xl font-normal mt-1 tracking-tight" style={{ color: "var(--ink-strong)" }}>
              PINE_FLOAT Balance
            </p>
          </div>
          {floatData.length > 0 && (
            <div className="text-right">
              <p className="text-xs" style={{ color: "var(--mute)" }}>Peak exposure</p>
              <p className="mono text-lg font-semibold" style={{ color: "var(--danger)" }}>
                {formatPaise(minFloat)}
              </p>
            </div>
          )}
        </div>
        <div style={{ height: 360 }}>
          {floatData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={floatData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="floatGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="50%" stopColor="#ef4444" stopOpacity={0.05} />
                    <stop offset="100%" stopColor="#00d992" stopOpacity={0.1} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(61,58,57,0.5)" />
                <XAxis
                  dataKey="date" tick={{ fill: "#8b949e", fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(5)}
                  stroke="var(--hairline)"
                />
                <YAxis
                  tick={{ fill: "#8b949e", fontSize: 11 }}
                  tickFormatter={(v: number) => formatPaise(v)}
                  stroke="var(--hairline)" width={90}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="var(--primary)" strokeDasharray="4 4" strokeOpacity={0.5} />
                <Area
                  type="monotone" dataKey="float_paise"
                  stroke="#ef4444" strokeWidth={2}
                  fill="url(#floatGrad)"
                  animationDuration={1200}
                  animationEasing="ease-out"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center">
              <p style={{ color: "var(--mute)" }}>Run pipeline to see float curve</p>
            </div>
          )}
        </div>
      </motion.div>

      <div className="section-divider mb-8" />

      {/* Recon Summary Chips */}
      <AnimatePresence>
        {Object.keys(summary).length > 0 && (
          <motion.div
            variants={stagger} initial="hidden" animate="show"
            className="flex flex-wrap gap-3 mb-6"
          >
            {Object.entries(summary).map(([status, count]) => (
              <motion.div key={status} variants={fadeUp}
                className="flex items-center gap-2 px-4 py-2 rounded-full"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <span className={`badge ${STATUS_BADGE[status] || ""}`}>{status}</span>
                <span className="mono text-sm font-semibold" style={{ color: "var(--ink)" }}>{count}</span>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Exceptions Table */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={ready ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7, delay: 0.4, ease }}
        className="card card-glow"
      >
        <div className="mb-6">
          <p className="text-[10px] font-semibold tracking-[2px] uppercase" style={{ color: "var(--mute)" }}>
            RECONCILIATION EXCEPTIONS
          </p>
          <p className="text-2xl font-normal mt-1 tracking-tight" style={{ color: "var(--ink-strong)" }}>
            Unresolved Items
          </p>
        </div>

        {exceptions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
                  {["Txn ID", "Status", "Amount", "Note"].map(h => (
                    <th key={h} className="text-left py-3 px-4 text-[10px] font-semibold tracking-[2px] uppercase"
                      style={{ color: "var(--mute)", background: "var(--canvas-soft)" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {exceptions.slice(0, 50).map((ex, i) => (
                  <motion.tr
                    key={ex.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + i * 0.02, duration: 0.3 }}
                    style={{ borderBottom: "1px solid var(--hairline)" }}
                    className="hover:bg-[var(--canvas-soft)] transition-colors"
                  >
                    <td className="py-3 px-4 mono" style={{ color: "var(--body)" }}>
                      {ex.txn_id ?? "—"}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`badge ${STATUS_BADGE[ex.status] || ""}`}>{ex.status}</span>
                    </td>
                    <td className="py-3 px-4 mono" style={{ color: "var(--ink)" }}>
                      {ex.amount_display ?? "—"}
                    </td>
                    <td className="py-3 px-4 text-xs" style={{ color: "var(--mute)" }}>
                      {ex.note}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
            {exceptions.length > 50 && (
              <p className="text-xs text-center py-4" style={{ color: "var(--mute)" }}>
                Showing 50 of {exceptions.length} exceptions
              </p>
            )}
          </div>
        ) : (
          <div className="py-12 text-center">
            <p style={{ color: "var(--mute)" }}>
              {ready ? "No exceptions — all transactions matched" : "Run pipeline to see exceptions"}
            </p>
          </div>
        )}
      </motion.div>

      {/* Footer */}
      <footer className="mt-12 py-6 text-center section-divider">
        <p className="text-xs" style={{ color: "var(--mute)" }}>
          tplus · settlement reconciliation engine · modeled scenario, not disclosed data
        </p>
      </footer>
    </div>
  );
}
