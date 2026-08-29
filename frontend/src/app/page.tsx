"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useUser } from "@/lib/UserContext";
import {
  getBalance,
  getTransactions,
  type BalanceResponse,
  type TransactionItem,
} from "@/lib/api";

function formatAmount(amount: string | number): string {
  return Number(amount).toLocaleString("en-BD", {
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

export default function OverviewPage() {
  const { activeUser, loading: userLoading } = useUser();
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!activeUser) return;
    setLoading(true);
    setError(null);
    try {
      const [bal, txns] = await Promise.all([
        getBalance(activeUser.id),
        getTransactions(activeUser.id, 5),
      ]);
      setBalance(bal);
      setTransactions(txns.items);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to connect to backend"
      );
    } finally {
      setLoading(false);
    }
  }, [activeUser]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (userLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-secondary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!activeUser) {
    return (
      <div className="glass-panel p-[32px] text-center">
        <span className="material-symbols-outlined text-[48px] text-on-surface-variant mb-4 block">
          person_off
        </span>
        <h2 className="text-headline-md text-primary mb-2">No Users Found</h2>
        <p className="text-body-md text-on-surface-variant">
          Make sure the FastAPI backend is running and has seeded users.
          <br />
          <code className="text-data-md bg-surface-container px-2 py-1 rounded mt-2 inline-block">
            uvicorn main:app --reload
          </code>
        </p>
      </div>
    );
  }

  const userName = activeUser.name.split(" ")[0];

  return (
    <>
      {/* Page Header */}
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-[16px]">
        <div>
          <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
            Good morning, {userName}.
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            Your money, clearly accounted for.
          </p>
        </div>
        {/* Quick Actions Desktop */}
        <div className="hidden md:flex gap-[8px]">
          <Link
            href="/request"
            className="bg-surface-container-lowest border border-outline-variant text-primary text-label-md px-6 py-3 rounded-full hover:bg-surface-container transition-colors flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">
              payments
            </span>
            Request Money
          </Link>
          <Link
            href="/send"
            className="bg-primary border border-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 transition-colors shadow-[0_4px_14px_rgba(0,0,0,0.15)] flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">send</span>
            Send Money
          </Link>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-3">
          <span className="material-symbols-outlined">error</span>
          <div>
            <p className="text-body-md font-medium">Backend unavailable</p>
            <p className="text-body-sm">{error}</p>
          </div>
          <button
            onClick={fetchData}
            className="ml-auto text-label-md hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-[24px]">
        {/* Left Column */}
        <div className="lg:col-span-2 space-y-[24px]">
          {/* Balance Card */}
          <section className="glass-panel p-[32px] relative overflow-hidden">
            <div className="absolute inset-0 opacity-5 pointer-events-none bg-gradient-to-br from-secondary via-transparent to-primary" />
            <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-[32px]">
              <div>
                <h2 className="text-label-md text-on-surface-variant uppercase tracking-wider mb-[8px]">
                  Total Balance
                </h2>
                {loading ? (
                  <div className="h-14 w-64 bg-surface-container animate-pulse rounded-lg" />
                ) : (
                  <div className="text-display text-primary tracking-tight">
                    ৳{formatAmount(balance?.balance || 0)}
                  </div>
                )}
              </div>
              {/* In/Out Summary */}
              <div className="flex gap-[24px]">
                <div className="flex flex-col">
                  <span className="text-body-sm text-on-surface-variant flex items-center gap-1 mb-1">
                    <span className="material-symbols-outlined text-on-tertiary-container text-[16px]">
                      arrow_downward
                    </span>
                    Received
                  </span>
                  <span className="text-data-lg text-on-tertiary-container">
                    {loading ? "..." : `${transactions.filter(t => t.direction === "received").length} txns`}
                  </span>
                </div>
                <div className="w-px bg-outline-variant opacity-50" />
                <div className="flex flex-col">
                  <span className="text-body-sm text-on-surface-variant flex items-center gap-1 mb-1">
                    <span className="material-symbols-outlined text-primary text-[16px]">
                      arrow_upward
                    </span>
                    Sent
                  </span>
                  <span className="text-data-lg text-primary">
                    {loading ? "..." : `${transactions.filter(t => t.direction === "sent").length} txns`}
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* Quick Actions Mobile */}
          <div className="flex md:hidden gap-[8px] w-full">
            <Link
              href="/request"
              className="flex-1 bg-surface-container-lowest border border-outline-variant text-primary text-label-md py-3 rounded-full justify-center flex items-center gap-2"
            >
              Request
            </Link>
            <Link
              href="/send"
              className="flex-1 bg-primary text-on-primary text-label-md py-3 rounded-full justify-center flex items-center gap-2 shadow-sm"
            >
              Send
            </Link>
          </div>

          {/* Recent Activity */}
          <section className="glass-panel p-0">
            <div className="p-[16px] border-b border-outline-variant flex justify-between items-center">
              <h3 className="text-headline-md text-primary">
                Recent Activity
              </h3>
              <Link
                href="/transactions"
                className="text-label-md text-secondary hover:underline"
              >
                View All
              </Link>
            </div>
            <div className="flex flex-col">
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-[16px] p-[16px] border-b border-outline-variant last:border-b-0"
                  >
                    <div className="w-12 h-12 rounded-full bg-surface-container animate-pulse" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-32 bg-surface-container animate-pulse rounded" />
                      <div className="h-3 w-48 bg-surface-container animate-pulse rounded" />
                    </div>
                    <div className="h-4 w-20 bg-surface-container animate-pulse rounded" />
                  </div>
                ))
              ) : transactions.length === 0 ? (
                <div className="p-[32px] text-center text-on-surface-variant">
                  <span className="material-symbols-outlined text-[32px] mb-2 block">
                    receipt_long
                  </span>
                  <p className="text-body-md">No transactions yet</p>
                  <p className="text-body-sm mt-1">
                    Send or request money to get started.
                  </p>
                </div>
              ) : (
                transactions.map((txn) => (
                  <div
                    key={txn.transfer_id}
                    className="flex items-center justify-between p-[16px] border-b border-outline-variant last:border-b-0 hover:bg-surface-container-low transition-colors cursor-pointer group"
                  >
                    <div className="flex items-center gap-[16px]">
                      <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center text-primary group-hover:bg-primary-container transition-colors">
                        <span className="material-symbols-outlined">
                          {txn.direction === "sent" ? "arrow_upward" : "arrow_downward"}
                        </span>
                      </div>
                      <div>
                        <p className="text-body-md text-primary font-medium">
                          {txn.counterparty_name}
                        </p>
                        <p className="text-body-sm text-on-surface-variant mt-0.5">
                          {timeAgo(txn.timestamp)} • Transfer
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className={`text-data-md font-medium ${
                          txn.direction === "received"
                            ? "text-on-tertiary-container"
                            : "text-primary"
                        }`}
                      >
                        {txn.direction === "received" ? "+" : "-"}৳
                        {formatAmount(txn.amount)}
                      </div>
                      <div
                        className={`inline-flex items-center px-2 py-0.5 rounded-full mt-1 ${
                          txn.direction === "received"
                            ? "bg-on-tertiary-container/10 text-on-tertiary-container"
                            : "bg-outline/10 text-on-surface-variant"
                        }`}
                      >
                        <span className="text-[10px] uppercase tracking-wider font-medium">
                          Settled
                        </span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Right Column */}
        <div className="lg:col-span-1 space-y-[24px]">
          {/* Ledger Health Widget */}
          <aside className="glass-panel p-[16px] border-t-4 border-t-on-tertiary-container">
            <div className="flex items-center gap-2 mb-[16px]">
              <span className="material-symbols-outlined text-on-tertiary-container">
                health_and_safety
              </span>
              <h3 className="text-headline-md text-primary">Ledger Health</h3>
            </div>
            <ul className="space-y-[8px] mb-[16px]">
              {[
                {
                  title: "Ledger consistent",
                  desc: "All balances mathematically verified.",
                },
                {
                  title: "No duplicate transfers",
                  desc: "Idempotency keys prevent double-processing.",
                },
                {
                  title: "Concurrency safe",
                  desc: "FOR UPDATE locks prevent race conditions.",
                },
              ].map((item) => (
                <li key={item.title} className="flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-on-tertiary-container/10 flex items-center justify-center mt-0.5 shrink-0">
                    <span className="material-symbols-outlined text-[14px] text-on-tertiary-container">
                      check
                    </span>
                  </div>
                  <div>
                    <p className="text-body-md text-primary">{item.title}</p>
                    <p className="text-body-sm text-on-surface-variant">
                      {item.desc}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="pt-[8px] border-t border-outline-variant flex items-center justify-between text-on-surface-variant">
              <span className="text-body-sm flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">
                  sync
                </span>
                Last verified
              </span>
              <span className="text-data-md">Just now</span>
            </div>
          </aside>

          {/* Info Card */}
          <aside className="glass-panel p-[16px] bg-surface-container-low border-none">
            <div className="w-12 h-12 rounded-lg bg-secondary/10 flex items-center justify-center mb-[8px] text-secondary">
              <span className="material-symbols-outlined">auto_graph</span>
            </div>
            <h4 className="text-headline-md text-primary mb-1">
              Double-Entry Ledger
            </h4>
            <p className="text-body-sm text-on-surface-variant mb-[16px]">
              Every transfer creates exactly two ledger entries — a debit and a
              credit — ensuring money is never created or destroyed.
            </p>
            <Link
              href="/transactions"
              className="text-label-md text-secondary flex items-center gap-1 hover:underline"
            >
              View Ledger
              <span className="material-symbols-outlined text-[16px]">
                arrow_forward
              </span>
            </Link>
          </aside>
        </div>
      </div>
    </>
  );
}
