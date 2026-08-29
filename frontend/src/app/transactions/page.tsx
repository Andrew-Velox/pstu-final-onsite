"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useUser } from "@/lib/UserContext";
import {
  getBalance,
  getTransactions,
  type BalanceResponse,
  type TransactionItem,
} from "@/lib/api";

type Filter = "all" | "sent" | "received";

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

const PAGE_SIZE = 20;

const FILTERS: { key: Filter; label: string; icon: string }[] = [
  { key: "all", label: "All", icon: "all_inclusive" },
  { key: "sent", label: "Sent", icon: "arrow_upward" },
  { key: "received", label: "Received", icon: "arrow_downward" },
];

export default function TransactionsPage() {
  const { activeUser } = useUser();
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [items, setItems] = useState<TransactionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!activeUser) return;
    setLoading(true);
    setError(null);
    try {
      const [bal, list] = await Promise.all([
        getBalance(activeUser.id),
        getTransactions(activeUser.id, PAGE_SIZE, page * PAGE_SIZE, filter),
      ]);
      setBalance(bal);
      setItems(list.items);
      setTotal(list.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch transactions");
    } finally {
      setLoading(false);
    }
  }, [activeUser, filter, page]);

  useEffect(() => {
    setPage(0);
  }, [filter, activeUser?.id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!activeUser) {
    return (
      <div className="glass-panel p-[32px] text-center text-on-surface-variant">
        No active user selected.
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const sentCount = items.filter((t) => t.direction === "sent").length;
  const receivedCount = items.filter((t) => t.direction === "received").length;

  return (
    <>
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-[16px]">
        <div>
          <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
            Transaction History
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            Every debit and credit — fully auditable.
          </p>
        </div>
        <Link
          href="/send"
          className="bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 transition-colors shadow-[0_4px_14px_rgba(0,0,0,0.15)] flex items-center gap-2 self-start"
        >
          <span className="material-symbols-outlined text-[18px]">send</span>
          New Transfer
        </Link>
      </header>

      {/* Balance summary */}
      <section className="glass-panel p-[24px] grid grid-cols-1 md:grid-cols-3 gap-[24px]">
        <div>
          <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
            Current balance
          </span>
          {loading && !balance ? (
            <div className="h-10 w-48 bg-surface-container animate-pulse rounded mt-2" />
          ) : (
            <p className="text-display text-primary mt-2">
              ৳{formatAmount(balance?.balance || 0)}
            </p>
          )}
        </div>
        <div className="md:border-l md:border-outline-variant md:pl-[24px]">
          <span className="text-label-md text-on-surface-variant uppercase tracking-wider flex items-center gap-1">
            <span className="material-symbols-outlined text-primary text-[16px]">
              arrow_upward
            </span>
            Sent (this page)
          </span>
          <p className="text-data-lg text-primary mt-2">{sentCount} txns</p>
        </div>
        <div className="md:border-l md:border-outline-variant md:pl-[24px]">
          <span className="text-label-md text-on-surface-variant uppercase tracking-wider flex items-center gap-1">
            <span className="material-symbols-outlined text-on-tertiary-container text-[16px]">
              arrow_downward
            </span>
            Received (this page)
          </span>
          <p className="text-data-lg text-on-tertiary-container mt-2">
            {receivedCount} txns
          </p>
        </div>
      </section>

      {error && (
        <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-3">
          <span className="material-symbols-outlined">error</span>
          <p className="text-body-md">{error}</p>
        </div>
      )}

      {/* Filter chips */}
      <div className="flex items-center gap-[8px]">
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`inline-flex items-center gap-2 px-[16px] py-[8px] rounded-full text-label-md transition-all ${
                active
                  ? "bg-secondary text-on-secondary shadow-[0_2px_8px_rgba(75,65,225,0.25)]"
                  : "bg-surface-container-lowest border border-outline-variant text-on-surface hover:bg-surface-container"
              }`}
            >
              <span className="material-symbols-outlined text-[16px]">{f.icon}</span>
              {f.label}
            </button>
          );
        })}
        <span className="ml-auto text-body-sm text-on-surface-variant">
          {total} total
        </span>
      </div>

      {/* Transactions list */}
      <section className="glass-panel p-0">
        {loading ? (
          <div className="flex flex-col">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-[16px] p-[16px] border-b border-outline-variant last:border-b-0"
              >
                <div className="w-12 h-12 rounded-full bg-surface-container animate-pulse" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-32 bg-surface-container animate-pulse rounded" />
                  <div className="h-3 w-48 bg-surface-container animate-pulse rounded" />
                </div>
                <div className="h-4 w-24 bg-surface-container animate-pulse rounded" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="p-[48px] text-center text-on-surface-variant">
            <span className="material-symbols-outlined text-[48px] mb-2 block">
              receipt_long
            </span>
            <p className="text-body-md">No transactions yet</p>
            <p className="text-body-sm mt-1">
              {filter === "all"
                ? "Send or receive money to see activity here."
                : `No ${filter} transactions on this page.`}
            </p>
            <Link
              href="/send"
              className="inline-block mt-4 bg-secondary text-on-secondary text-label-md px-6 py-2 rounded-full hover:opacity-90"
            >
              Send Money
            </Link>
          </div>
        ) : (
          <div className="flex flex-col">
            {items.map((txn) => (
              <div
                key={txn.transfer_id}
                className="flex items-center justify-between p-[16px] border-b border-outline-variant last:border-b-0 hover:bg-surface-container-low transition-colors"
              >
                <div className="flex items-center gap-[16px]">
                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center ${
                      txn.direction === "received"
                        ? "bg-on-tertiary-container/10 text-on-tertiary-container"
                        : "bg-surface-container text-primary"
                    }`}
                  >
                    <span className="material-symbols-outlined">
                      {txn.direction === "sent" ? "arrow_upward" : "arrow_downward"}
                    </span>
                  </div>
                  <div>
                    <p className="text-body-md text-primary font-medium">
                      {txn.counterparty_name}
                    </p>
                    <p className="text-body-sm text-on-surface-variant mt-0.5">
                      {timeAgo(txn.timestamp)} • Transfer • #{txn.transfer_id.slice(0, 8)}
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
                    {txn.direction === "received" ? "+" : "-"}৳{formatAmount(txn.amount)}
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
            ))}
          </div>
        )}
      </section>

      {/* Pagination */}
      {!loading && total > 0 && (
        <div className="flex items-center justify-between">
          <span className="text-body-sm text-on-surface-variant">
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex gap-[8px]">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-4 py-2 rounded-full border border-outline-variant text-label-md text-on-surface hover:bg-surface-container disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[16px]">chevron_left</span>
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-4 py-2 rounded-full border border-outline-variant text-label-md text-on-surface hover:bg-surface-container disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
            >
              Next
              <span className="material-symbols-outlined text-[16px]">chevron_right</span>
            </button>
          </div>
        </div>
      )}
    </>
  );
}