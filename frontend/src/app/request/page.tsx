"use client";

import { useState, useEffect, useCallback } from "react";
import { useUser } from "@/lib/UserContext";
import {
  createMoneyRequest,
  listMoneyRequests,
  approveRequest,
  declineRequest,
  type MoneyRequestResponse,
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

export default function RequestPage() {
  const { activeUser, users } = useUser();
  const [targetId, setTargetId] = useState("");
  const [amount, setAmount] = useState("");
  const [creating, setCreating] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [requests, setRequests] = useState<MoneyRequestResponse[]>([]);
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const otherUsers = users.filter((u) => u.id !== activeUser?.id);

  const fetchRequests = useCallback(async () => {
    if (!activeUser) return;
    setLoadingRequests(true);
    try {
      const data = await listMoneyRequests(activeUser.id);
      setRequests(data);
    } catch {
      console.error("Failed to fetch requests");
    } finally {
      setLoadingRequests(false);
    }
  }, [activeUser]);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  async function handleCreateRequest(e: React.FormEvent) {
    e.preventDefault();
    if (!activeUser || !targetId || !amount) return;

    setCreating(true);
    setError(null);
    setSuccess(null);

    try {
      await createMoneyRequest({
        requester_id: activeUser.id,
        target_id: targetId,
        amount: parseFloat(amount).toFixed(2),
      });
      setSuccess("Money request sent successfully!");
      setAmount("");
      setTargetId("");
      fetchRequests();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create request");
    } finally {
      setCreating(false);
    }
  }

  async function handleApprove(reqId: string) {
    if (!activeUser) return;
    setActionLoading(reqId);
    try {
      await approveRequest(reqId, activeUser.id);
      fetchRequests();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Approval failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDecline(reqId: string) {
    if (!activeUser) return;
    setActionLoading(reqId);
    try {
      await declineRequest(reqId, activeUser.id);
      fetchRequests();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Decline failed");
    } finally {
      setActionLoading(null);
    }
  }

  if (!activeUser) {
    return (
      <div className="glass-panel p-[32px] text-center text-on-surface-variant">
        No active user selected.
      </div>
    );
  }

  // Split requests into incoming (target is me) and outgoing (requester is me)
  const incoming = requests.filter((r) => r.target_id === activeUser.id);
  const outgoing = requests.filter((r) => r.requester_id === activeUser.id);

  function getUserName(id: string): string {
    return users.find((u) => u.id === id)?.name || "Unknown";
  }

  return (
    <>
      <header>
        <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
          Request Money
        </h1>
        <p className="text-body-lg text-on-surface-variant mt-[4px]">
          Ask someone to send you money. They'll approve or decline.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-[24px]">
        {/* Form */}
        <div className="lg:col-span-2 space-y-[24px]">
          <form
            onSubmit={handleCreateRequest}
            className="glass-panel p-[32px] space-y-[24px]"
          >
            <h3 className="text-headline-md text-primary">New Request</h3>

            {/* From (you — the requester) */}
            <div>
              <label className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-2">
                Request From
              </label>
              <select
                className="w-full bg-surface-container border border-outline-variant rounded-xl px-4 py-3 text-body-md text-on-surface focus:ring-2 focus:ring-secondary focus:outline-none appearance-none cursor-pointer"
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                required
              >
                <option value="">Select who to request from...</option>
                {otherUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} ({u.email})
                  </option>
                ))}
              </select>
            </div>

            {/* Amount */}
            <div>
              <label className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-2">
                Amount
              </label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-headline-md text-on-surface-variant">
                  ৳
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  className="w-full bg-surface-container border border-outline-variant rounded-xl pl-10 pr-4 py-3 text-data-lg text-primary focus:ring-2 focus:ring-secondary focus:outline-none"
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
              </div>
            </div>

            {/* Feedback */}
            {error && (
              <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-2">
                <span className="material-symbols-outlined">error</span>
                <p className="text-body-md">{error}</p>
              </div>
            )}
            {success && (
              <div className="bg-on-tertiary-container/10 text-on-tertiary-container px-4 py-3 rounded-xl flex items-center gap-2">
                <span className="material-symbols-outlined">check_circle</span>
                <p className="text-body-md">{success}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={creating || !targetId || !amount}
              className="w-full bg-secondary text-on-secondary text-label-md py-4 rounded-full hover:opacity-90 transition-all shadow-[0_4px_14px_rgba(75,65,225,0.3)] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {creating ? (
                <div className="animate-spin w-5 h-5 border-2 border-on-secondary border-t-transparent rounded-full" />
              ) : (
                <>
                  <span className="material-symbols-outlined text-[18px]">
                    payments
                  </span>
                  Send Request
                </>
              )}
            </button>
          </form>

          {/* Incoming Requests (I need to approve/decline) */}
          <section className="glass-panel p-0">
            <div className="p-[16px] border-b border-outline-variant">
              <h3 className="text-headline-md text-primary flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary">
                  inbox
                </span>
                Requests Waiting on You
                {incoming.length > 0 && (
                  <span className="bg-secondary text-on-secondary text-[12px] px-2 py-0.5 rounded-full font-bold">
                    {incoming.length}
                  </span>
                )}
              </h3>
            </div>
            <div className="flex flex-col">
              {loadingRequests ? (
                <div className="p-[16px] text-center">
                  <div className="animate-spin w-6 h-6 border-2 border-secondary border-t-transparent rounded-full mx-auto" />
                </div>
              ) : incoming.length === 0 ? (
                <div className="p-[32px] text-center text-on-surface-variant">
                  <span className="material-symbols-outlined text-[32px] mb-2 block">
                    check_circle
                  </span>
                  <p className="text-body-md">No pending requests</p>
                </div>
              ) : (
                incoming.map((req) => (
                  <div
                    key={req.id}
                    className="flex items-center justify-between p-[16px] border-b border-outline-variant last:border-b-0"
                  >
                    <div className="flex items-center gap-[16px]">
                      <div className="w-12 h-12 rounded-full bg-secondary/10 flex items-center justify-center text-secondary">
                        <span className="material-symbols-outlined">
                          person
                        </span>
                      </div>
                      <div>
                        <p className="text-body-md text-primary font-medium">
                          {getUserName(req.requester_id)} requests
                        </p>
                        <p className="text-body-sm text-on-surface-variant">
                          {timeAgo(req.created_at)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-data-lg text-primary font-medium">
                        ৳{formatAmount(req.amount)}
                      </span>
                      <button
                        onClick={() => handleDecline(req.id)}
                        disabled={actionLoading === req.id}
                        className="px-4 py-2 rounded-full border border-outline-variant text-on-surface-variant text-label-md hover:bg-error-container hover:text-on-error-container hover:border-error transition-colors disabled:opacity-50"
                      >
                        Decline
                      </button>
                      <button
                        onClick={() => handleApprove(req.id)}
                        disabled={actionLoading === req.id}
                        className="px-4 py-2 rounded-full bg-on-tertiary-container text-on-tertiary text-label-md hover:opacity-90 transition-colors disabled:opacity-50 flex items-center gap-1"
                      >
                        {actionLoading === req.id ? (
                          <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                        ) : (
                          "Approve"
                        )}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Outgoing Requests sidebar */}
        <div className="space-y-[24px]">
          <aside className="glass-panel p-0">
            <div className="p-[16px] border-b border-outline-variant">
              <h3 className="text-headline-md text-primary flex items-center gap-2">
                <span className="material-symbols-outlined text-on-surface-variant">
                  outbox
                </span>
                Requests You Sent
              </h3>
            </div>
            <div className="flex flex-col">
              {loadingRequests ? (
                <div className="p-[16px] text-center">
                  <div className="animate-spin w-6 h-6 border-2 border-secondary border-t-transparent rounded-full mx-auto" />
                </div>
              ) : outgoing.length === 0 ? (
                <div className="p-[24px] text-center text-on-surface-variant">
                  <p className="text-body-sm">No pending outgoing requests</p>
                </div>
              ) : (
                outgoing.map((req) => (
                  <div
                    key={req.id}
                    className="p-[16px] border-b border-outline-variant last:border-b-0"
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="text-body-md text-primary font-medium">
                          To: {getUserName(req.target_id)}
                        </p>
                        <p className="text-body-sm text-on-surface-variant">
                          {timeAgo(req.created_at)}
                        </p>
                      </div>
                      <span className="text-data-md text-primary">
                        ৳{formatAmount(req.amount)}
                      </span>
                    </div>
                    <div className="mt-2 inline-flex items-center px-2 py-0.5 rounded-full bg-secondary/10 text-secondary">
                      <span className="text-[10px] uppercase tracking-wider font-medium">
                        Pending
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}
