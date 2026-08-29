"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useUser } from "@/lib/UserContext";
import {
  adminResolveDispute,
  getDispute,
  respondToDispute,
  type DisputeDetail,
  type DisputeStatus,
  type DisputeTimelineEntry,
} from "@/lib/api";

function formatAmount(value: string | number): string {
  return Number(value).toLocaleString("en-BD", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function truncateHash(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 3) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
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

export default function DisputeDetailPage() {
  const params = useParams<{ id: string }>();
  const disputeId = params.id;
  const { activeUser } = useUser();

  const [data, setData] = useState<DisputeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    if (!disputeId) {
      setLoading(false);
      setError("No dispute id was provided in the URL.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const d = await getDispute(disputeId);
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dispute");
    } finally {
      setLoading(false);
    }
  }, [disputeId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const role = useMemo<"complainant" | "respondent" | "observer">(() => {
    if (!data || !activeUser) return "observer";
    if (data.complainant_id === activeUser.id) return "complainant";
    if (data.respondent_id === activeUser.id) return "respondent";
    return "observer";
  }, [data, activeUser]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-secondary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="glass-panel p-[32px] text-center">
        <span className="material-symbols-outlined text-[48px] text-error mb-4 block">
          error
        </span>
        <h2 className="text-headline-md text-primary mb-2">
          Could not load dispute
        </h2>
        <p className="text-body-md text-on-surface-variant mb-6">
          {error ?? "Dispute not found."}
        </p>
        <Link
          href="/disputes"
          className="bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 inline-flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          Back to Disputes
        </Link>
      </div>
    );
  }

  const meta = statusInfo(data.status);
  const active = isActive(data.status);

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
            Dispute{" "}
            <code className="text-data-md text-secondary">
              {truncateHash(data.id)}
            </code>
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            Against transfer{" "}
            <Link
              href={`/explain/${data.transfer_id}`}
              className="text-secondary underline"
            >
              {truncateHash(data.transfer_id, 8, 6)}
            </Link>{" "}
            · filed {formatDateTime(data.created_at)}
          </p>
        </div>
        <div
          className={`flex items-center gap-2 px-4 py-2 rounded-full ${meta.pill}`}
        >
          <span className="material-symbols-outlined text-[18px]">
            {meta.icon}
          </span>
          <span className="text-label-md">{meta.label}</span>
        </div>
      </header>

      {/* Hold countdown */}
      {active && (
        <section
          className={`glass-panel p-[16px] border-l-4 ${
            data.days_until_hold_expires <= 3
              ? "border-l-error bg-error-container/20"
              : "border-l-secondary bg-secondary-container/20"
          }`}
        >
          <div className="flex items-center gap-2 mb-[8px]">
            <span className="material-symbols-outlined text-primary">
              hourglass_top
            </span>
            <span className="text-label-md text-primary uppercase tracking-wider">
              Hold timer
            </span>
          </div>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-headline-lg text-primary">
              {data.days_until_hold_expires}
            </span>
            <span className="text-body-md text-on-surface-variant">
              days until auto-refund
            </span>
            <span className="text-body-sm text-on-surface-variant ml-auto">
              expires {formatDateTime(data.hold_expires_at)}
            </span>
          </div>
          <p className="text-body-sm text-on-surface-variant mt-2">
            {data.days_until_hold_expires > 0
              ? `The receiver has until ${formatDateTime(
                  data.hold_expires_at
                )} to respond or accept the refund. If they do not, the held amount is automatically returned to the complainant via a clawback transfer.`
              : "Hold expired — the auto-refund sweep will run on the next list/refresh."}
          </p>
        </section>
      )}

      {/* Parties + claim */}
      <section className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] items-center gap-[24px] glass-panel p-[32px]">
        <PartyCard
          name={data.complainant_name}
          role="Complainant (sender)"
          roleIcon="arrow_upward"
          badgeColor="bg-error-container text-error"
        />
        <div className="flex flex-col items-center">
          <div className="text-headline-md text-secondary">
            ৳{formatAmount(data.amount_delta)}
          </div>
          <div className="material-symbols-outlined text-secondary text-[28px] mt-2">
            swap_horiz
          </div>
          <div className="text-label-md text-on-surface-variant uppercase tracking-wider mt-1">
            mismatch
          </div>
        </div>
        <PartyCard
          name={data.respondent_name}
          role="Respondent (receiver)"
          roleIcon="arrow_downward"
          badgeColor="bg-secondary-container text-secondary"
        />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-[24px]">
        {/* Claim */}
        <div className="glass-panel p-[24px]">
          <div className="flex items-center gap-2 mb-[12px]">
            <span className="material-symbols-outlined text-secondary">
              request_quote
            </span>
            <h2 className="text-headline-md text-primary">Claim Details</h2>
          </div>
          <dl className="space-y-[12px] text-body-md">
            <KV
              label="Claimed amount"
              value={`৳${formatAmount(data.claimed_amount)}`}
            />
            <KV
              label="Requested (intended) amount"
              value={`৳${formatAmount(data.requested_amount)}`}
            />
            <KV
              label="Mismatch (must be ≤ 3)"
              value={`৳${formatAmount(data.amount_delta)}`}
              accent={Number(data.amount_delta) > 3 ? "error" : "ok"}
            />
          </dl>
          {data.narrative && (
            <div className="mt-[16px] p-[16px] rounded-xl bg-surface-container">
              <span className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-[8px]">
                Complainant narrative
              </span>
              <p className="text-body-md text-primary whitespace-pre-wrap">
                {data.narrative}
              </p>
            </div>
          )}
        </div>

        {/* Screenshot */}
        <div className="glass-panel p-[24px]">
          <div className="flex items-center gap-2 mb-[12px]">
            <span className="material-symbols-outlined text-secondary">
              image
            </span>
            <h2 className="text-headline-md text-primary">
              Submitted Proof
            </h2>
          </div>
          {isImage(data.screenshot_url) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={data.screenshot_url}
              alt="Complainant proof screenshot"
              className="rounded-xl border border-outline-variant w-full max-h-[420px] object-contain bg-surface-container"
            />
          ) : (
            <a
              href={data.screenshot_url}
              target="_blank"
              rel="noreferrer"
              className="text-secondary underline break-all"
            >
              {data.screenshot_url}
            </a>
          )}
          <p className="text-body-sm text-on-surface-variant mt-[8px]">
            Provided by the complainant. The receiver can review and respond
            below.
          </p>
        </div>
      </section>

      {/* Receiver response */}
      {data.receiver_response && (
        <section className="glass-panel p-[24px]">
          <div className="flex items-center gap-2 mb-[12px]">
            <span className="material-symbols-outlined text-secondary">
              forum
            </span>
            <h2 className="text-headline-md text-primary">Receiver Response</h2>
          </div>
          <p className="text-body-md text-primary whitespace-pre-wrap">
            {data.receiver_response}
          </p>
        </section>
      )}

      {data.resolution_note && (
        <section className="glass-panel p-[24px] border-t-4 border-t-tertiary-container">
          <div className="flex items-center gap-2 mb-[12px]">
            <span className="material-symbols-outlined text-on-tertiary-container">
              task_alt
            </span>
            <h2 className="text-headline-md text-primary">Resolution</h2>
          </div>
          <p className="text-body-md text-primary">{data.resolution_note}</p>
          {data.resolved_at && (
            <p className="text-body-sm text-on-surface-variant mt-2">
              Resolved at {formatDateTime(data.resolved_at)}
            </p>
          )}
        </section>
      )}

      {/* Actions */}
      {role === "respondent" && active && (
        <RespondForm
          disputeId={data.id}
          userId={activeUser!.id}
          onDone={fetchDetail}
        />
      )}

      {role === "observer" && active && (
        <AdminPanel disputeId={data.id} onDone={fetchDetail} />
      )}

      {/* Timeline */}
      <section className="glass-panel p-[24px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <span className="material-symbols-outlined text-secondary">
            timeline
          </span>
          <h2 className="text-headline-md text-primary">Audit Trail</h2>
        </div>
        <Timeline entries={data.timeline} />
      </section>
    </>
  );
}

function RespondForm({
  disputeId,
  userId,
  onDone,
}: {
  disputeId: string;
  userId: string;
  onDone: () => Promise<void>;
}) {
  const [response, setResponse] = useState("");
  const [acceptRefund, setAcceptRefund] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    if (!response.trim()) {
      setError("Please write a short response.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await respondToDispute(disputeId, {
        user_id: userId,
        response,
        accept_refund: acceptRefund,
      });
      setResponse("");
      setAcceptRefund(false);
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to respond");
    } finally {
      setSubmitting(false);
    }
  }, [disputeId, userId, response, acceptRefund, onDone]);

  return (
    <section className="glass-panel p-[24px] border-l-4 border-l-secondary">
      <div className="flex items-center gap-2 mb-[12px]">
        <span className="material-symbols-outlined text-secondary">reply</span>
        <h2 className="text-headline-md text-primary">Your Response</h2>
      </div>
      <p className="text-body-sm text-on-surface-variant mb-[12px]">
        You are listed as the receiver of the disputed transfer. Submit your
        side of the story, and optionally accept the refund to close this
        immediately.
      </p>

      <textarea
        value={response}
        onChange={(e) => setResponse(e.target.value)}
        placeholder="Explain what happened from your side…"
        rows={4}
        className="w-full p-3 bg-surface-container border border-outline-variant rounded-xl text-body-md text-primary focus:outline-none focus:ring-2 focus:ring-secondary resize-none"
      />

      <label className="mt-[12px] flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={acceptRefund}
          onChange={(e) => setAcceptRefund(e.target.checked)}
          className="w-4 h-4 accent-secondary"
        />
        <span className="text-body-md text-primary">
          I accept the refund and consent to the clawback transfer.
        </span>
      </label>

      {error && (
        <div className="mt-3 p-3 rounded-lg bg-error-container/30 text-error text-body-sm">
          {error}
        </div>
      )}

      <button
        onClick={submit}
        disabled={submitting}
        className="mt-[16px] bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 shadow-[0_4px_14px_rgba(0,0,0,0.15)]"
      >
        <span className="material-symbols-outlined text-[18px]">send</span>
        {submitting
          ? "Submitting…"
          : acceptRefund
            ? "Accept Refund & Close"
            : "Submit Response"}
      </button>
    </section>
  );
}

function AdminPanel({
  disputeId,
  onDone,
}: {
  disputeId: string;
  onDone: () => Promise<void>;
}) {
  // Use the first user as the admin actor for demo purposes. In a real
  // deployment this would be the authenticated admin's id.
  const { users } = useUser();
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState<null | "refund" | "release">(null);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async (resolution: "refund_sender" | "release_receiver") => {
      if (users.length === 0) return;
      const adminId = users[0].id;
      setSubmitting(resolution === "refund_sender" ? "refund" : "release");
      setError(null);
      try {
        await adminResolveDispute(disputeId, {
          admin_id: adminId,
          resolution,
          note: note.trim() || null,
        });
        setNote("");
        await onDone();
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Failed to resolve dispute"
        );
      } finally {
        setSubmitting(null);
      }
    },
    [users, disputeId, note, onDone]
  );

  return (
    <section className="glass-panel p-[24px] border-l-4 border-l-on-tertiary-container bg-tertiary-container/10">
      <div className="flex items-center gap-2 mb-[12px]">
        <span className="material-symbols-outlined text-on-tertiary-container">
          admin_panel_settings
        </span>
        <h2 className="text-headline-md text-primary">Admin Override</h2>
      </div>
      <p className="text-body-sm text-on-surface-variant mb-[12px]">
        Neither party is this user, so the admin tools are available. Pick a
        resolution and (optionally) leave a note for the audit trail.
      </p>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Optional resolution note…"
        rows={2}
        className="w-full p-3 bg-surface-container border border-outline-variant rounded-xl text-body-md text-primary focus:outline-none focus:ring-2 focus:ring-secondary resize-none"
      />
      {error && (
        <div className="mt-3 p-3 rounded-lg bg-error-container/30 text-error text-body-sm">
          {error}
        </div>
      )}
      <div className="mt-[16px] flex flex-wrap gap-[8px]">
        <button
          onClick={() => submit("refund_sender")}
          disabled={submitting !== null}
          className="bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 shadow-[0_4px_14px_rgba(0,0,0,0.15)]"
        >
          <span className="material-symbols-outlined text-[18px]">
            undo
          </span>
          {submitting === "refund" ? "Refunding…" : "Force Refund Sender"}
        </button>
        <button
          onClick={() => submit("release_receiver")}
          disabled={submitting !== null}
          className="bg-surface-container text-secondary text-label-md px-6 py-3 rounded-full hover:bg-surface-container-high disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-[18px]">
            verified
          </span>
          {submitting === "release" ? "Releasing…" : "Release to Receiver"}
        </button>
      </div>
    </section>
  );
}

function PartyCard({
  name,
  role,
  roleIcon,
  badgeColor,
}: {
  name: string;
  role: string;
  roleIcon: string;
  badgeColor: string;
}) {
  return (
    <div className="flex flex-col gap-[8px]">
      <div className="flex items-center gap-2 text-label-md text-on-surface-variant uppercase tracking-wider">
        <span className="material-symbols-outlined text-[18px]">{roleIcon}</span>
        {role}
      </div>
      <div className="flex items-center gap-[12px]">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center ${badgeColor}`}>
          <span className="material-symbols-outlined">person</span>
        </div>
        <p className="text-headline-md text-primary">{name}</p>
      </div>
    </div>
  );
}

function KV({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "ok" | "error";
}) {
  const valueClass =
    accent === "error"
      ? "text-error"
      : accent === "ok"
        ? "text-on-tertiary-container"
        : "text-primary";
  return (
    <div className="flex items-center justify-between border-b border-outline-variant pb-2 last:border-b-0 last:pb-0">
      <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
        {label}
      </span>
      <span className={`text-data-md ${valueClass}`}>{value}</span>
    </div>
  );
}

function Timeline({ entries }: { entries: DisputeTimelineEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-body-sm text-on-surface-variant">No events yet.</p>
    );
  }
  return (
    <ol className="relative border-l-2 border-outline-variant pl-[16px] space-y-[12px]">
      {entries.map((e, idx) => (
        <li key={`${e.at}-${idx}`} className="relative">
          <span className="absolute -left-[24px] top-1 w-3 h-3 rounded-full bg-secondary" />
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-label-md text-primary">{e.event}</span>
            <span className="text-body-sm text-on-surface-variant">
              · {e.actor}
            </span>
            <span className="text-body-sm text-on-surface-variant ml-auto">
              {formatDateTime(e.at)}
            </span>
          </div>
          {e.detail && (
            <p className="text-body-sm text-on-surface-variant mt-1">
              {e.detail}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

function isImage(url: string): boolean {
  return (
    /^data:image\//i.test(url) ||
    /\.(png|jpe?g|gif|webp|bmp|svg)(\?.*)?$/i.test(url)
  );
}
