"use client";

import { useState } from "react";
import { useUser } from "@/lib/UserContext";
import { createTransfer, type TransferResponse } from "@/lib/api";
import { v4 as uuidv4 } from "uuid";

function generateIdempotencyKey(): string {
  return `txn-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function SendPage() {
  const { activeUser, users } = useUser();
  const [receiverId, setReceiverId] = useState("");
  const [amount, setAmount] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<TransferResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const otherUsers = users.filter((u) => u.id !== activeUser?.id);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!activeUser || !receiverId || !amount) return;

    setSending(true);
    setError(null);
    setResult(null);

    try {
      const data = await createTransfer({
        sender_id: activeUser.id,
        receiver_id: receiverId,
        amount: parseFloat(amount).toFixed(2),
        idempotency_key: generateIdempotencyKey(),
      });
      setResult(data);
      setAmount("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Transfer failed");
    } finally {
      setSending(false);
    }
  }

  if (!activeUser) {
    return (
      <div className="glass-panel p-[32px] text-center text-on-surface-variant">
        No active user selected.
      </div>
    );
  }

  return (
    <>
      <header>
        <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
          Send Money
        </h1>
        <p className="text-body-lg text-on-surface-variant mt-[4px]">
          Transfer funds securely with double-entry bookkeeping.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-[24px]">
        {/* Form */}
        <div className="lg:col-span-2">
          <form onSubmit={handleSubmit} className="glass-panel p-[32px] space-y-[24px]">
            {/* From (read-only) */}
            <div>
              <label className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-2">
                From
              </label>
              <div className="flex items-center gap-3 bg-surface-container rounded-xl px-4 py-3">
                <div className="w-10 h-10 rounded-full bg-secondary-container flex items-center justify-center text-on-secondary-container font-bold">
                  {activeUser.name.charAt(0)}
                </div>
                <div>
                  <p className="text-body-md text-primary font-medium">
                    {activeUser.name}
                  </p>
                  <p className="text-body-sm text-on-surface-variant">
                    {activeUser.email}
                  </p>
                </div>
              </div>
            </div>

            {/* To */}
            <div>
              <label className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-2">
                To
              </label>
              <select
                className="w-full bg-surface-container border border-outline-variant rounded-xl px-4 py-3 text-body-md text-on-surface focus:ring-2 focus:ring-secondary focus:outline-none appearance-none cursor-pointer"
                value={receiverId}
                onChange={(e) => setReceiverId(e.target.value)}
                required
              >
                <option value="">Select recipient...</option>
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

            {/* Error */}
            {error && (
              <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-2">
                <span className="material-symbols-outlined">error</span>
                <p className="text-body-md">{error}</p>
              </div>
            )}

            {/* Success */}
            {result && (
              <div className="bg-on-tertiary-container/10 text-on-tertiary-container px-4 py-3 rounded-xl flex items-center gap-2">
                <span className="material-symbols-outlined">check_circle</span>
                <div>
                  <p className="text-body-md font-medium">Transfer successful!</p>
                  <p className="text-body-sm">
                    ৳{Number(result.amount).toFixed(2)} sent. New balance: ৳
                    {Number(result.sender_balance).toFixed(2)}
                  </p>
                </div>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={sending || !receiverId || !amount}
              className="w-full bg-primary text-on-primary text-label-md py-4 rounded-full hover:opacity-90 transition-all shadow-[0_4px_14px_rgba(0,0,0,0.15)] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {sending ? (
                <div className="animate-spin w-5 h-5 border-2 border-on-primary border-t-transparent rounded-full" />
              ) : (
                <>
                  <span className="material-symbols-outlined text-[18px]">
                    send
                  </span>
                  Send Money
                </>
              )}
            </button>
          </form>
        </div>

        {/* Info sidebar */}
        <div className="space-y-[24px]">
          <aside className="glass-panel p-[16px] border-t-4 border-t-secondary">
            <div className="flex items-center gap-2 mb-[16px]">
              <span className="material-symbols-outlined text-secondary">
                shield
              </span>
              <h3 className="text-headline-md text-primary">Transfer Safety</h3>
            </div>
            <ul className="space-y-[8px]">
              {[
                "Atomic transaction — all or nothing",
                "Idempotency key prevents double-sends",
                "Balance checked under database lock",
                "Full audit trail in ledger entries",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[14px] text-secondary mt-0.5">
                    check
                  </span>
                  <span className="text-body-sm text-on-surface-variant">
                    {item}
                  </span>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      </div>
    </>
  );
}
