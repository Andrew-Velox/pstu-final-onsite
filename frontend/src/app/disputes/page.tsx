"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useUser } from "@/lib/UserContext";
import {
  listDisputes,
  markAllNotificationsRead,
  type DisputeListResponse,
  type DisputeStatus,
  type DisputeSummary,
} from "@/lib/api";

function formatAmount(value: string | number): string {
  return Number(value).toLocaleString("en-BD", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function statusInfo(status: DisputeStatus): {
  label: string;
  icon: string;
  pill: string;
} {
  switch (status) {
    case "filed":
      return {
        label: "Under review",
        icon: "hourglass_top",
        pill: "bg-secondary-container text-secondary",
      };
    case "under_review":
      return {
        label: "Negotiating",
        icon: "forum",
        pill: "bg-secondary-container text-secondary",
      };
    case "resolved_for_sender":
      return {
        label: "Refunded",
        icon: "check_circle",
        pill: "bg-tertiary-container text-on-tertiary-container",
      };
    case "resolved_for_receiver":
      return {
        label: "Released",
        icon: "verified",
        pill: "bg-tertiary-container text-on-tertiary-container",
      };
    case "auto_refunded":
      return {
        label: "Auto-refunded",
        icon: "auto_mode",
        pill: "bg-tertiary-container text-on-tertiary-container",
      };
    case "rejected":
      return {
        label: "Rejected",
        icon: "block",
        pill: "bg-error-container text-error",
      };
    default:
      return {
        label: status,
        icon: "help",
        pill: "bg-surface-container text-on-surface-variant",
      };
  }
}

function isActive(status: DisputeStatus): boolean {
  return status === "filed" || status === "under_review";
}

export default function DisputesPage() {
  const { activeUser, loading: userLoading } = useUser();
  const [data, setData] = useState<DisputeListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDisputes = useCallback(async () => {
    if (!activeUser) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [list] = await Promise.all([
        listDisputes(activeUser.id),
        markAllNotificationsRead(activeUser.id).catch(() => null),
      ]);
      setData(list);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to load disputes"
      );
    } finally {
      setLoading(false);
    }
  }, [activeUser]);

  useEffect(() => {
    fetchDisputes();
  }, [fetchDisputes]);

  const sorted = useMemo(() => {
    if (!data) return [];
    // Active disputes first, then by created_at desc.
    return [...data.items].sort((a, b) => {
      const aActive = isActive(a.status);
      const bActive = isActive(b.status);
      if (aActive !== bActive) return aActive ? -1 : 1;
      return (
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    });
  }, [data]);

  if (userLoading || loading) {
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
        </p>
      </div>
    );
  }

  const activeCount = data?.active_holds ?? 0;
  const pendingRefunds = data?.auto_refunds_pending ?? 0;

  return (
    <>
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-[16px]">
        <div>
          <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
            Dispute Center
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            Filed money-movement claims, live hold timers, and auto-refund
            tracking.
          </p>
        </div>
        <div className="flex gap-[8px]">
          <button
            onClick={fetchDisputes}
            className="bg-surface-container text-secondary text-label-md px-6 py-3 rounded-full hover:bg-surface-container-high transition-colors flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">refresh</span>
            Refresh
          </button>
          <Link
            href="/disputes/new"
            className="bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 transition-opacity flex items-center gap-2 shadow-[0_4px_14px_rgba(0,0,0,0.15)]"
          >
            <span className="material-symbols-outlined text-[18px]">gavel</span>
            File a Dispute
          </Link>
        </div>
      </header>

      {error && (
        <div className="glass-panel p-[16px] border border-error-container bg-error-container/30 text-error">
          <span className="material-symbols-outlined mr-2 align-middle">
            error
          </span>
          {error}
        </div>
      )}

      <section className="grid grid-cols-2 md:grid-cols-4 gap-[16px]">
        <SummaryCard
          icon="format_list_bulleted"
          label="Total disputes"
          value={data?.total ?? 0}
          tone="neutral"
        />
        <SummaryCard
          icon="hourglass_top"
          label="Active holds"
          value={activeCount}
          tone="warning"
        />
        <SummaryCard
          icon="auto_mode"
          label="Auto-refunds pending"
          value={pendingRefunds}
          tone="warning"
        />
        <SummaryCard
          icon="check_circle"
          label="Resolved"
          value={
            data
              ? data.items.filter(
                  (d) =>
                    d.status === "resolved_for_sender" ||
                    d.status === "resolved_for_receiver" ||
                    d.status === "auto_refunded"
                ).length
              : 0
          }
          tone="positive"
        />
      </section>

      <section className="glass-panel p-[24px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <span className="material-symbols-outlined text-secondary">
            gavel
          </span>
          <h2 className="text-headline-md text-primary">My Disputes</h2>
        </div>
        <p className="text-body-sm text-on-surface-variant mb-[16px]">
          Active holds appear first. Each dispute starts a 15-day hold on the
          receiver&apos;s available balance; if the receiver doesn&apos;t respond
          in time, the held amount is auto-refunded to you.
        </p>

        {sorted.length === 0 ? (
          <div className="text-center py-12 text-on-surface-variant">
            <span className="material-symbols-outlined text-[48px] block mb-2">
              balance
            </span>
            <p className="text-body-md mb-1">No disputes yet</p>
            <p className="text-body-sm">
              If you sent money to the wrong number, file a dispute from the
              Transactions page or below.
            </p>
            <Link
              href="/disputes/new"
              className="mt-4 inline-flex items-center gap-2 text-secondary hover:underline"
            >
              <span className="material-symbols-outlined text-[18px]">
                add_circle
              </span>
              File a new dispute
            </Link>
          </div>
        ) : (
          <ul className="flex flex-col gap-[8px]">
            {sorted.map((d) => (
              <DisputeRow key={d.id} d={d} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function DisputeRow({ d }: { d: DisputeSummary }) {
  const meta = statusInfo(d.status);
  const active = isActive(d.status);
  return (
    <li>
      <Link
        href={`/disputes/${d.id}`}
        className="flex items-center justify-between gap-[16px] p-[16px] rounded-xl border border-transparent hover:border-outline-variant bg-surface-container transition-colors"
      >
        <div className="flex items-center gap-[12px]">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
              d.role === "complainant"
                ? "bg-error-container text-error"
                : "bg-secondary-container text-secondary"
            }`}
          >
            <span className="material-symbols-outlined">
              {d.role === "complainant" ? "arrow_upward" : "arrow_downward"}
            </span>
          </div>
          <div>
            <p className="text-label-md text-primary">
              {d.role === "complainant" ? "Claimed from " : "Claimed by "}
              {d.counterparty_name}
            </p>
            <p className="text-body-sm text-on-surface-variant flex items-center gap-1">
              <span className="material-symbols-outlined text-[14px]">
                {meta.icon}
              </span>
              {meta.label}
              {active && d.days_until_hold_expires > 0 && (
                <span className="text-error">
                  · {d.days_until_hold_expires}d until auto-refund
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-[12px]">
          <span className="text-headline-md text-primary">
            ৳{formatAmount(d.amount)}
          </span>
          <span
            className={`text-[10px] uppercase tracking-wider font-medium px-2 py-1 rounded-full ${meta.pill}`}
          >
            {meta.label}
          </span>
          <span className="material-symbols-outlined text-on-surface-variant">
            chevron_right
          </span>
        </div>
      </Link>
    </li>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: string;
  label: string;
  value: number;
  tone: "neutral" | "positive" | "warning";
}) {
  const toneClass =
    tone === "positive"
      ? "text-on-tertiary-container"
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
