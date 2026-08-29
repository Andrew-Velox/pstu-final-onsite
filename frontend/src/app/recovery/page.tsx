"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getRecoverySummary,
  getReplayImpact,
  replayTransfer,
  listUsers,
  getTransactions,
  type RecoverySummary,
  type ReplayImpact,
  type ReplayResponse,
  type User,
  type TransactionItem,
} from "@/lib/api";

function formatAmount(value: string | number): string {
  return Number(value).toLocaleString("en-BD", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function timeAgo(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface ReplayRow {
  transfer_id: string;
  amount: string;
  direction: "sent" | "received";
  counterparty_id: string;
  counterparty_name: string;
  timestamp: string;
}

export default function RecoveryPage() {
  const [summary, setSummary] = useState<RecoverySummary | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [rows, setRows] = useState<ReplayRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedTransferId, setSelectedTransferId] = useState<string | null>(
    null
  );
  const [impact, setImpact] = useState<ReplayImpact | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [replayResult, setReplayResult] = useState<ReplayResponse | null>(null);
  const [replaying, setReplaying] = useState(false);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, u] = await Promise.all([getRecoverySummary(), listUsers()]);
      setSummary(s);
      setUsers(u);

      // Build a flat list of recent transfers across all users so the
      // operator can pick one and replay it. Fetch all user transactions
      // in parallel instead of sequentially awaiting one user at a time.
      const userIds = u.slice(0, 6).map((user) => user.id);
      const perUserResults = await Promise.allSettled(
        userIds.map((id) => getTransactions(id, 8))
      );
      const recent: ReplayRow[] = [];
      perUserResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          for (const t of result.value.items) {
            recent.push({
              transfer_id: t.transfer_id,
              amount: t.amount,
              direction: t.direction,
              counterparty_id: t.counterparty_id,
              counterparty_name: t.counterparty_name,
              timestamp: t.timestamp,
            });
          }
        } else {
          console.warn(
            `[recovery] failed to load transactions for user ${userIds[idx]}:`,
            result.reason
          );
        }
      });
      // Sort by timestamp desc
      recent.sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      setRows(recent.slice(0, 25));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load recovery data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const selectTransfer = useCallback(async (transferId: string) => {
    setSelectedTransferId(transferId);
    setImpact(null);
    setReplayResult(null);
    setImpactLoading(true);
    try {
      const imp = await getReplayImpact(transferId);
      setImpact(imp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to compute impact");
    } finally {
      setImpactLoading(false);
    }
  }, []);

  const handleReplay = useCallback(async () => {
    if (!selectedTransferId) return;
    setReplaying(true);
    setReplayResult(null);
    try {
      const res = await replayTransfer(selectedTransferId);
      setReplayResult(res);
      // Refresh summary after replay
      const s = await getRecoverySummary();
      setSummary(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }, [selectedTransferId]);

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-secondary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <>
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-[16px]">
        <div>
          <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
            Money Movement Recovery Center
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            Inspect any transfer, dry-run the replay, then commit.
          </p>
        </div>
        <button
          onClick={fetchSummary}
          className="bg-surface-container text-secondary text-label-md px-6 py-3 rounded-full hover:bg-surface-container-high transition-colors flex items-center gap-2 self-start"
        >
          <span className="material-symbols-outlined text-[18px]">refresh</span>
          Refresh
        </button>
      </header>

      {error && (
        <div className="glass-panel p-[16px] border border-error-container bg-error-container/30 text-error">
          <span className="material-symbols-outlined mr-2 align-middle">
            error
          </span>
          {error}
        </div>
      )}

      {/* Summary cards */}
      <section className="grid grid-cols-2 md:grid-cols-5 gap-[16px]">
        <SummaryCard
          icon="receipt_long"
          label="Total transfers"
          value={summary?.total_transfers ?? 0}
        />
        <SummaryCard
          icon="check_circle"
          label="Completed"
          value={summary?.completed ?? 0}
          tone="positive"
        />
        <SummaryCard
          icon="error"
          label="Failed"
          value={summary?.failed ?? 0}
          tone="negative"
        />
        <SummaryCard
          icon="replay"
          label="Replayable"
          value={summary?.replayable ?? 0}
          tone="warning"
        />
        <SummaryCard
          icon="pending_actions"
          label="Pending requests"
          value={summary?.pending_requests ?? 0}
          tone="neutral"
        />
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-[24px]">
        {/* Transfer list */}
        <section className="glass-panel p-[24px] lg:col-span-3">
          <div className="flex items-center gap-2 mb-[16px]">
            <span className="material-symbols-outlined text-secondary">
              list_alt
            </span>
            <h2 className="text-headline-md text-primary">Recent Transfers</h2>
          </div>
          <p className="text-body-sm text-on-surface-variant mb-[16px]">
            Click a transfer to see its replay impact. Every replay is
            idempotent — re-running it twice will not double-debit the sender.
          </p>

          {rows.length === 0 ? (
            <div className="text-center py-12 text-on-surface-variant">
              <span className="material-symbols-outlined text-[48px] block mb-2">
                inbox
              </span>
              No transfers yet. Create one from{" "}
              <Link href="/send" className="text-secondary underline">
                /send
              </Link>
              .
            </div>
          ) : (
            <ul className="flex flex-col gap-[8px] max-h-[520px] overflow-y-auto">
              {rows.map((r) => {
                const isSelected = r.transfer_id === selectedTransferId;
                return (
                  <li key={r.transfer_id}>
                    <button
                      onClick={() => selectTransfer(r.transfer_id)}
                      disabled={impactLoading && isSelected}
                      className={`w-full text-left flex items-center justify-between gap-[16px] p-[12px] rounded-xl border transition-all disabled:opacity-60 disabled:cursor-not-allowed ${
                        isSelected
                          ? "bg-secondary-container/20 border-secondary"
                          : "bg-surface-container border-transparent hover:border-outline-variant"
                      }`}
                    >
                      <div className="flex items-center gap-[12px]">
                        <div
                          className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
                            r.direction === "sent"
                              ? "bg-error-container text-error"
                              : "bg-tertiary-container text-tertiary"
                          }`}
                        >
                          <span className="material-symbols-outlined">
                            {r.direction === "sent"
                              ? "arrow_upward"
                              : "arrow_downward"}
                          </span>
                        </div>
                        <div>
                          <p className="text-label-md text-primary">
                            {r.direction === "sent" ? "Sent to " : "Received from "}
                            {r.counterparty_name}
                          </p>
                          <p className="text-body-sm text-on-surface-variant">
                            {timeAgo(r.timestamp)}
                          </p>
                        </div>
                      </div>
                      <span
                        className={`text-headline-md ${
                          r.direction === "sent" ? "text-error" : "text-tertiary"
                        }`}
                      >
                        {r.direction === "sent" ? "−" : "+"}৳
                        {formatAmount(r.amount)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Impact + replay panel */}
        <section className="glass-panel p-[24px] lg:col-span-2 flex flex-col">
          <div className="flex items-center gap-2 mb-[16px]">
            <span className="material-symbols-outlined text-secondary">
              science
            </span>
            <h2 className="text-headline-md text-primary">Replay Impact</h2>
          </div>

          {!selectedTransferId ? (
            <div className="flex-1 flex items-center justify-center text-on-surface-variant text-body-md text-center py-12">
              Select a transfer on the left to dry-run its replay.
            </div>
          ) : impactLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="animate-spin w-6 h-6 border-2 border-secondary border-t-transparent rounded-full" />
            </div>
          ) : impact ? (
            <div className="flex flex-col gap-[16px]">
              <div
                className={`p-[16px] rounded-xl border ${
                  impact.sender_has_sufficient_funds
                    ? "bg-tertiary-container/30 border-tertiary-container"
                    : "bg-error-container/30 border-error-container"
                }`}
              >
                <div className="flex items-center gap-2 mb-[8px]">
                  <span className="material-symbols-outlined">
                    {impact.sender_has_sufficient_funds
                      ? "check_circle"
                      : "warning"}
                  </span>
                  <span className="text-label-md text-primary">
                    {impact.sender_has_sufficient_funds
                      ? "Replay will succeed"
                      : "Replay would overdraw sender"}
                  </span>
                </div>
                <p className="text-body-sm text-on-surface-variant">
                  {impact.note}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-[12px]">
                <div className="bg-surface-container p-[12px] rounded-xl">
                  <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
                    Sender after
                  </span>
                  <p className="text-headline-md text-primary mt-1">
                    ৳{formatAmount(impact.sender_balance_after)}
                  </p>
                </div>
                <div className="bg-surface-container p-[12px] rounded-xl">
                  <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
                    Receiver after
                  </span>
                  <p className="text-headline-md text-primary mt-1">
                    ৳{formatAmount(impact.receiver_balance_after)}
                  </p>
                </div>
              </div>

              <button
                onClick={handleReplay}
                disabled={!impact.sender_has_sufficient_funds || replaying}
                className="bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-[0_4px_14px_rgba(0,0,0,0.15)]"
              >
                <span className="material-symbols-outlined text-[18px]">
                  replay
                </span>
                {replaying ? "Replaying…" : "Commit Replay"}
              </button>

              {replayResult && (
                <div
                  className={`p-[16px] rounded-xl border ${
                    replayResult.replayed
                      ? "bg-tertiary-container/30 border-tertiary-container"
                      : "bg-error-container/30 border-error-container"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-[8px]">
                    <span className="material-symbols-outlined">
                      {replayResult.replayed ? "check_circle" : "error"}
                    </span>
                    <span className="text-label-md text-primary">
                      {replayResult.replayed ? "Replay OK" : "Replay Failed"}
                    </span>
                  </div>
                  <p className="text-body-sm text-on-surface-variant">
                    {replayResult.note}
                  </p>
                </div>
              )}
            </div>
          ) : null}
        </section>
      </div>
    </>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: string;
  label: string;
  value: number;
  tone?: "neutral" | "positive" | "negative" | "warning";
}) {
  const toneClass =
    tone === "positive"
      ? "text-tertiary"
      : tone === "negative"
        ? "text-error"
        : tone === "warning"
          ? "text-secondary"
          : "text-primary";
  return (
    <div className="glass-panel p-[20px]">
      <span className={`material-symbols-outlined ${toneClass} text-[24px]`}>
        {icon}
      </span>
      <p className={`text-headline-md ${toneClass} mt-[8px]`}>{value}</p>
      <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
        {label}
      </span>
    </div>
  );
}
