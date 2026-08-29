"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useUser } from "@/lib/UserContext";
import {
  fileDispute,
  getBalance,
  getTransactions,
  type BalanceResponse,
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
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days >= 1) return `${days}d ago`;
  const hrs = Math.floor(diff / 3_600_000);
  if (hrs >= 1) return `${hrs}h ago`;
  const mins = Math.floor(diff / 60_000);
  if (mins >= 1) return `${mins}m ago`;
  return "Just now";
}

export default function NewDisputePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedId = searchParams.get("transfer_id") ?? null;
  const { activeUser } = useUser();

  const [outgoing, setOutgoing] = useState<TransactionItem[]>([]);
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(preselectedId);
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [claimedAmount, setClaimedAmount] = useState("");
  const [requestedAmount, setRequestedAmount] = useState("");
  const [narrative, setNarrative] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!activeUser) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [txns, bal] = await Promise.all([
        getTransactions(activeUser.id, 20),
        getBalance(activeUser.id),
      ]);
      setOutgoing(txns.items.filter((t) => t.direction === "sent"));
      setBalance(bal);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load transactions");
    } finally {
      setLoading(false);
    }
  }, [activeUser]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Pre-fill the form with the selected transfer's amount.
  useEffect(() => {
    if (!selectedId) return;
    const t = outgoing.find((x) => x.transfer_id === selectedId);
    if (t) {
      setClaimedAmount((prev) => (prev ? prev : t.amount));
      setRequestedAmount((prev) => (prev ? prev : t.amount));
    }
  }, [selectedId, outgoing]);

  const selected = useMemo(
    () => outgoing.find((t) => t.transfer_id === selectedId) ?? null,
    [outgoing, selectedId]
  );

  const ageDays = selected
    ? Math.floor(
        (Date.now() - new Date(selected.timestamp).getTime()) / 86_400_000
      )
    : 0;
  const ageOk = ageDays <= 15;

  const delta = useMemo(() => {
    const c = parseFloat(claimedAmount);
    const r = parseFloat(requestedAmount);
    if (Number.isNaN(c) || Number.isNaN(r)) return null;
    return Math.abs(c - r);
  }, [claimedAmount, requestedAmount]);

  const deltaOk = delta !== null && delta <= 3;
  const urlOk =
    screenshotUrl.trim().length > 0 &&
    (/^https?:\/\//i.test(screenshotUrl.trim()) ||
      /^data:image\//i.test(screenshotUrl.trim()));

  const canSubmit =
    !!activeUser &&
    !!selected &&
    ageOk &&
    urlOk &&
    deltaOk &&
    !submitting;

  const submit = useCallback(async () => {
    if (!activeUser || !selected) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const detail = await fileDispute({
        transfer_id: selected.transfer_id,
        complainant_id: activeUser.id,
        screenshot_url: screenshotUrl.trim(),
        claimed_amount: claimedAmount,
        requested_amount: requestedAmount,
        narrative: narrative.trim() || null,
      });
      router.push(`/disputes/${detail.id}`);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to file dispute");
    } finally {
      setSubmitting(false);
    }
  }, [
    activeUser,
    selected,
    screenshotUrl,
    claimedAmount,
    requestedAmount,
    narrative,
    router,
  ]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-secondary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!activeUser) {
    return (
      <div className="glass-panel p-[32px] text-center">
        <h2 className="text-headline-md text-primary">No active user</h2>
      </div>
    );
  }

  return (
    <>
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-[16px]">
        <div>
          <Link
            href="/disputes"
            className="text-label-md text-secondary inline-flex items-center gap-1 mb-[8px] hover:underline"
          >
            <span className="material-symbols-outlined text-[16px]">
              arrow_back
            </span>
            Back to Disputes
          </Link>
          <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
            File a Dispute
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            Money Movement Protection — claim a transfer you sent in error.
          </p>
        </div>
      </header>

      {error && (
        <div className="glass-panel p-[16px] border border-error-container bg-error-container/30 text-error">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-[24px]">
        {/* Step 1 — pick the transfer */}
        <section className="glass-panel p-[24px] lg:col-span-2">
          <div className="flex items-center gap-2 mb-[12px]">
            <span className="material-symbols-outlined text-secondary">
              format_list_numbered
            </span>
            <h2 className="text-headline-md text-primary">Step 1 — Pick transfer</h2>
          </div>
          <p className="text-body-sm text-on-surface-variant mb-[16px]">
            Only transfers you sent in the last 15 days are eligible. Current
            balance:{" "}
            <span className="text-primary font-medium">
              ৳{formatAmount(balance?.balance ?? 0)}
            </span>
            .
          </p>

          {outgoing.length === 0 ? (
            <div className="text-center py-12 text-on-surface-variant">
              <span className="material-symbols-outlined text-[48px] block mb-2">
                outgoing_mail
              </span>
              <p>No outgoing transfers yet.</p>
            </div>
          ) : (
            <ul className="flex flex-col gap-[8px] max-h-[520px] overflow-y-auto">
              {outgoing.map((t) => {
                const isSel = selectedId === t.transfer_id;
                const age = Math.floor(
                  (Date.now() - new Date(t.timestamp).getTime()) /
                    86_400_000
                );
                const eligible = age <= 15;
                return (
                  <li key={t.transfer_id}>
                    <button
                      onClick={() => setSelectedId(t.transfer_id)}
                      disabled={!eligible}
                      className={`w-full text-left flex items-center justify-between gap-[16px] p-[12px] rounded-xl border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                        isSel
                          ? "bg-secondary-container/20 border-secondary"
                          : "bg-surface-container border-transparent hover:border-outline-variant"
                      }`}
                    >
                      <div>
                        <p className="text-label-md text-primary">
                          To {t.counterparty_name}
                        </p>
                        <p
                          className={`text-body-sm ${
                            eligible
                              ? "text-on-surface-variant"
                              : "text-error"
                          }`}
                        >
                          {timeAgo(t.timestamp)}
                          {!eligible && " · outside 15-day window"}
                        </p>
                      </div>
                      <span className="text-headline-md text-primary">
                        ৳{formatAmount(t.amount)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Step 2 — claim */}
        <section className="glass-panel p-[24px] lg:col-span-3">
          <div className="flex items-center gap-2 mb-[12px]">
            <span className="material-symbols-outlined text-secondary">
              edit_note
            </span>
            <h2 className="text-headline-md text-primary">Step 2 — Claim details</h2>
          </div>

          {selected ? (
            <div className="mb-[16px] p-3 bg-surface-container rounded-xl flex items-center justify-between">
              <div>
                <p className="text-label-md text-on-surface-variant uppercase tracking-wider">
                  Selected transfer
                </p>
                <p className="text-body-md text-primary">
                  To {selected.counterparty_name} · ৳
                  {formatAmount(selected.amount)} · {timeAgo(selected.timestamp)}
                </p>
              </div>
              <span
                className={`px-3 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium ${
                  ageOk
                    ? "bg-tertiary-container text-on-tertiary-container"
                    : "bg-error-container text-error"
                }`}
              >
                {ageOk ? "eligible" : "expired"}
              </span>
            </div>
          ) : (
            <p className="mb-[16px] text-body-sm text-on-surface-variant">
              Pick a transfer from the list on the left to start.
            </p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-[16px]">
            <Field label="Claimed amount (৳)">
              <input
                type="number"
                step="0.01"
                min="0"
                value={claimedAmount}
                onChange={(e) => setClaimedAmount(e.target.value)}
                placeholder="e.g. 500"
                disabled={!selected}
                className="w-full p-3 bg-surface-container border border-outline-variant rounded-xl text-body-md text-primary focus:outline-none focus:ring-2 focus:ring-secondary disabled:opacity-50"
              />
            </Field>
            <Field label="Requested amount (৳)">
              <input
                type="number"
                step="0.01"
                min="0"
                value={requestedAmount}
                onChange={(e) => setRequestedAmount(e.target.value)}
                placeholder="e.g. 500"
                disabled={!selected}
                className="w-full p-3 bg-surface-container border border-outline-variant rounded-xl text-body-md text-primary focus:outline-none focus:ring-2 focus:ring-secondary disabled:opacity-50"
              />
            </Field>
          </div>

          {delta !== null && (
            <p
              className={`text-body-sm mt-2 ${
                deltaOk ? "text-on-tertiary-container" : "text-error"
              }`}
            >
              Mismatch = ৳{formatAmount(delta)}{" "}
              {deltaOk
                ? "· within the 3-digit tolerance"
                : "· must be ≤ 3 to qualify"}
            </p>
          )}

          <div className="mt-[16px]">
            <Field label="Screenshot / proof URL">
              <input
                type="url"
                value={screenshotUrl}
                onChange={(e) => setScreenshotUrl(e.target.value)}
                placeholder="https://i.imgur.com/… or data:image/png;base64,…"
                disabled={!selected}
                className="w-full p-3 bg-surface-container border border-outline-variant rounded-xl text-body-md text-primary focus:outline-none focus:ring-2 focus:ring-secondary disabled:opacity-50"
              />
              {screenshotUrl && !urlOk && (
                <p className="text-body-sm text-error mt-1">
                  Must be an http(s) URL or a data: image URI.
                </p>
              )}
            </Field>
          </div>

          <div className="mt-[16px]">
            <Field label="What happened? (optional)">
              <textarea
                rows={4}
                value={narrative}
                onChange={(e) => setNarrative(e.target.value)}
                placeholder="Type a short note for the receiver and any future reviewer."
                disabled={!selected}
                className="w-full p-3 bg-surface-container border border-outline-variant rounded-xl text-body-md text-primary focus:outline-none focus:ring-2 focus:ring-secondary resize-none disabled:opacity-50"
              />
            </Field>
          </div>

          {formError && (
            <div className="mt-4 p-3 rounded-lg bg-error-container/30 text-error text-body-sm">
              {formError}
            </div>
          )}

          <button
            onClick={submit}
            disabled={!canSubmit}
            className="mt-[16px] bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 shadow-[0_4px_14px_rgba(0,0,0,0.15)]"
          >
            <span className="material-symbols-outlined text-[18px]">gavel</span>
            {submitting ? "Filing…" : "File Dispute"}
          </button>
        </section>
      </div>
    </>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}
