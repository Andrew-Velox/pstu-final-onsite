"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useUser } from "@/lib/UserContext";
import {
  createTransfer,
  getBalance,
  x402Sign,
  type TransferResponse,
  type User,
} from "@/lib/api";

type Step = 0 | 1 | 2;

function formatAmount(value: string | number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0.00";
  return n.toLocaleString("en-BD", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

function generateIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `txn-${crypto.randomUUID()}`;
  }
  return `txn-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const AVATAR_GRADIENTS = [
  "from-secondary to-primary",
  "from-on-tertiary-container to-secondary",
  "from-tertiary-fixed to-on-tertiary-container",
  "from-primary to-secondary",
];

function avatarGradient(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) | 0;
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

function StepIndicator({
  index,
  label,
  state,
}: {
  index: number;
  label: string;
  state: "done" | "active" | "pending";
}) {
  return (
    <div className="flex flex-col items-center gap-2 flex-1">
      <div
        className={`w-9 h-9 rounded-full flex items-center justify-center text-label-md transition-all ${
          state === "done"
            ? "bg-on-tertiary-container text-on-tertiary"
            : state === "active"
            ? "bg-secondary text-on-secondary shadow-[0_0_0_6px_rgba(75,65,225,0.12)]"
            : "bg-surface-container text-on-surface-variant border border-outline-variant"
        }`}
      >
        <span className="material-symbols-outlined text-[18px]">
          {state === "done" ? "check" : state === "active" ? "edit" : index + 1}
        </span>
      </div>
      <span
        className={`text-label-md uppercase tracking-wider ${
          state === "pending" ? "text-on-surface-variant" : "text-primary"
        }`}
      >
        {label}
      </span>
    </div>
  );
}

function StepConnector({ done }: { done: boolean }) {
  return (
    <div
      className={`flex-1 h-px -mt-7 ${
        done ? "bg-on-tertiary-container" : "bg-outline-variant"
      }`}
    />
  );
}

export default function SendPage() {
  const router = useRouter();
  const { activeUser, users, refreshUsers } = useUser();

  const [step, setStep] = useState<Step>(0);
  const [receiverId, setReceiverId] = useState<string>("");
  const [amount, setAmount] = useState<string>("");
  const [balance, setBalance] = useState<number>(0);
  const [loadingBalance, setLoadingBalance] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<TransferResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signedHeader, setSignedHeader] = useState<string | null>(null);

  const otherUsers = useMemo(
    () => users.filter((u) => u.id !== activeUser?.id),
    [users, activeUser]
  );

  const receiver: User | undefined = otherUsers.find((u) => u.id === receiverId);

  useEffect(() => {
    if (!activeUser) return;
    let cancelled = false;
    setLoadingBalance(true);
    getBalance(activeUser.id)
      .then((res) => {
        if (!cancelled) setBalance(Number(res.balance));
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Balance unavailable");
      })
      .finally(() => {
        if (!cancelled) setLoadingBalance(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeUser]);

  const numericAmount = Number(amount);
  const amountValid = Number.isFinite(numericAmount) && numericAmount > 0;
  const sufficient = amountValid && numericAmount <= balance;
  const newBalance = amountValid ? balance - numericAmount : balance;

  function handleCancel() {
    router.push("/");
  }

  function handleBack() {
    if (step === 0) {
      router.push("/");
    } else {
      setStep((s) => (s - 1) as Step);
    }
  }

  async function handleConfirm() {
    if (!activeUser || !receiver || !amountValid || !sufficient) return;
    setSubmitting(true);
    setError(null);
    try {
      // Demonstrate x402 signing — every transfer carries an HMAC-signed
      // timestamp so a downstream verifier can reject replays.
      const sig = await x402Sign({
        sender_id: activeUser.id,
        receiver_id: receiver.id,
        amount: numericAmount.toFixed(2),
      });
      setSignedHeader(`${sig.algorithm} @ ${sig.timestamp}`);

      const data = await createTransfer({
        sender_id: activeUser.id,
        receiver_id: receiver.id,
        amount: numericAmount.toFixed(2),
        idempotency_key: generateIdempotencyKey(),
      });
      setResult(data);
      setBalance(Number(data.sender_balance));
      await refreshUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Transfer failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (!activeUser) {
    return (
      <div className="glass-panel p-[32px] text-center text-on-surface-variant">
        No active user selected.
      </div>
    );
  }

  // ── Success view ──────────────────────────────────────────────────────────
  if (result) {
    return (
      <div className="max-w-xl mx-auto">
        <div className="glass-panel p-[40px] text-center space-y-[24px]">
          <div className="w-20 h-20 rounded-full bg-on-tertiary-container/10 mx-auto flex items-center justify-center">
            <span className="material-symbols-outlined text-on-tertiary-container text-[48px]">
              check_circle
            </span>
          </div>
          <div>
            <h2 className="text-headline-lg text-primary">Transfer complete</h2>
            <p className="text-body-md text-on-surface-variant mt-2">
              You sent ৳{formatAmount(result.amount)} to{" "}
              <span className="text-primary font-medium">{receiver?.name}</span>.
            </p>
          </div>
          <div className="bg-surface-container rounded-xl p-[16px] text-left space-y-2">
            <div className="flex justify-between">
              <span className="text-body-sm text-on-surface-variant">Reference</span>
              <span className="text-data-md text-primary">
                {result.idempotency_key}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-body-sm text-on-surface-variant">New balance</span>
              <span className="text-data-md text-primary">
                ৳{formatAmount(result.sender_balance)}
              </span>
            </div>
            {signedHeader && (
              <div className="flex justify-between">
                <span className="text-body-sm text-on-surface-variant">
                  x402 signature
                </span>
                <span className="text-data-md text-secondary">{signedHeader}</span>
              </div>
            )}
          </div>
          <div className="flex gap-[12px]">
            <Link
              href="/transactions"
              className="flex-1 border border-outline-variant text-on-surface text-label-md py-3 rounded-full hover:bg-surface-container transition-colors flex items-center justify-center"
            >
              View Transactions
            </Link>
            <button
              onClick={() => {
                setResult(null);
                setStep(0);
                setReceiverId("");
                setAmount("");
              }}
              className="flex-1 bg-primary text-on-primary text-label-md py-3 rounded-full hover:opacity-90 transition-colors"
            >
              Send Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto pb-[40px]">
      {/* Header bar — back / cancel / brand */}
      <header className="flex items-center justify-between mb-[24px]">
        <button
          onClick={handleBack}
          aria-label="Back"
          className="w-10 h-10 rounded-full hover:bg-surface-container transition-colors flex items-center justify-center text-primary"
        >
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <button
          onClick={handleCancel}
          className="text-label-md text-on-surface-variant hover:text-primary transition-colors"
        >
          Cancel
        </button>
      </header>

      <h1 className="text-headline-lg text-primary text-center mb-[24px]">
        Send Money
      </h1>

      {/* Step indicator */}
      <div className="flex items-start mb-[32px] px-[8px]">
        <StepIndicator
          index={0}
          label="Recipient"
          state={step > 0 ? "done" : step === 0 ? "active" : "pending"}
        />
        <StepConnector done={step > 0} />
        <StepIndicator
          index={1}
          label="Amount"
          state={step > 1 ? "done" : step === 1 ? "active" : "pending"}
        />
        <StepConnector done={step > 2} />
        <StepIndicator
          index={2}
          label="Review"
          state={step === 2 ? "active" : "pending"}
        />
      </div>

      {error && step !== 2 && (
        <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-2 mb-[24px]">
          <span className="material-symbols-outlined">error</span>
          <p className="text-body-md">{error}</p>
        </div>
      )}

      {/* Step 0 — Recipient */}
      {step === 0 && (
        <section className="glass-panel p-[24px] space-y-[16px]">
          <h2 className="text-headline-md text-primary">Who are you sending to?</h2>
          {otherUsers.length === 0 ? (
            <div className="p-[16px] text-center text-on-surface-variant">
              <p className="text-body-md">No other users available.</p>
              <Link
                href="/users"
                className="text-secondary text-label-md hover:underline mt-2 inline-block"
              >
                Register a user →
              </Link>
            </div>
          ) : (
            <div className="space-y-[8px]">
              {otherUsers.map((u) => {
                const selected = u.id === receiverId;
                return (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => setReceiverId(u.id)}
                    className={`w-full flex items-center gap-[16px] p-[12px] rounded-xl border transition-all text-left ${
                      selected
                        ? "border-secondary bg-secondary/5 shadow-[0_0_0_3px_rgba(75,65,225,0.08)]"
                        : "border-outline-variant hover:bg-surface-container-low"
                    }`}
                  >
                    <div
                      className={`w-12 h-12 rounded-full bg-gradient-to-br ${avatarGradient(
                        u.id
                      )} flex items-center justify-center text-on-primary font-semibold`}
                    >
                      {getInitials(u.name)}
                    </div>
                    <div className="flex-1">
                      <p className="text-body-md text-primary font-medium">{u.name}</p>
                      <p className="text-body-sm text-on-surface-variant">{u.email}</p>
                    </div>
                    <span
                      className={`material-symbols-outlined ${
                        selected ? "text-secondary" : "text-on-surface-variant"
                      }`}
                    >
                      {selected ? "radio_button_checked" : "radio_button_unchecked"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          <button
            type="button"
            disabled={!receiverId}
            onClick={() => setStep(1)}
            className="w-full bg-primary text-on-primary text-label-md py-4 rounded-full hover:opacity-90 transition-all shadow-[0_4px_14px_rgba(0,0,0,0.15)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Continue
          </button>
        </section>
      )}

      {/* Step 1 — Amount */}
      {step === 1 && (
        <section className="glass-panel p-[24px] space-y-[24px]">
          {receiver && (
            <div className="flex items-center gap-3 bg-surface-container rounded-xl px-4 py-3">
              <div
                className={`w-10 h-10 rounded-full bg-gradient-to-br ${avatarGradient(
                  receiver.id
                )} flex items-center justify-center text-on-primary font-semibold text-body-sm`}
              >
                {getInitials(receiver.name)}
              </div>
              <div className="flex-1">
                <p className="text-body-md text-primary font-medium">{receiver.name}</p>
                <p className="text-body-sm text-on-surface-variant">{receiver.email}</p>
              </div>
              <button
                onClick={() => setStep(0)}
                className="text-label-md text-secondary hover:underline"
              >
                Change
              </button>
            </div>
          )}

          <div>
            <label className="text-label-md text-on-surface-variant uppercase tracking-wider block mb-2">
              Amount
            </label>
            <div className="relative">
              <span className="absolute left-6 top-1/2 -translate-y-1/2 text-headline-lg text-on-surface-variant">
                ৳
              </span>
              <input
                inputMode="decimal"
                type="number"
                step="0.01"
                min="0.01"
                autoFocus
                className="w-full bg-surface-container border border-outline-variant rounded-2xl pl-14 pr-[16px] py-[24px] text-display text-primary focus:ring-2 focus:ring-secondary focus:outline-none"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            {amountValid && !sufficient && (
              <p className="text-body-sm text-error mt-2 flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">error</span>
                Insufficient balance — you only have ৳{formatAmount(balance)}.
              </p>
            )}
          </div>

          <div className="flex justify-center">
            <div className="inline-flex items-center gap-2 bg-surface-container border border-outline-variant rounded-full px-[16px] py-[8px]">
              <span className="material-symbols-outlined text-on-surface-variant text-[18px]">
                account_balance_wallet
              </span>
              <span className="text-body-sm text-on-surface-variant">
                Available balance:
              </span>
              {loadingBalance ? (
                <span className="h-4 w-20 bg-surface animate-pulse rounded" />
              ) : (
                <span className="text-data-md text-primary font-medium">
                  ৳{formatAmount(balance)}
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            disabled={!amountValid || !sufficient}
            onClick={() => setStep(2)}
            className="w-full bg-primary text-on-primary text-label-md py-4 rounded-full hover:opacity-90 transition-all shadow-[0_4px_14px_rgba(0,0,0,0.15)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Review Transfer
          </button>
        </section>
      )}

      {/* Step 2 — Review */}
      {step === 2 && receiver && (
        <section className="space-y-[24px]">
          <div className="glass-panel p-[24px] space-y-[20px]">
            <h2 className="text-headline-md text-primary">Review your transfer</h2>

            <div className="bg-surface-container rounded-2xl p-[20px] text-center">
              <p className="text-label-md text-on-surface-variant uppercase tracking-wider mb-2">
                You're sending
              </p>
              <p className="text-display text-primary leading-none">
                ৳{formatAmount(numericAmount)}
              </p>
              <p className="text-body-md text-on-surface-variant mt-3">
                to{" "}
                <span className="text-primary font-medium">{receiver.name}</span>
              </p>
            </div>

            <div className="bg-surface-container rounded-xl divide-y divide-outline-variant">
              <div className="flex justify-between px-[16px] py-[12px]">
                <span className="text-body-sm text-on-surface-variant">From</span>
                <span className="text-data-md text-primary">{activeUser.name}</span>
              </div>
              <div className="flex justify-between px-[16px] py-[12px]">
                <span className="text-body-sm text-on-surface-variant">To</span>
                <span className="text-data-md text-primary">{receiver.name}</span>
              </div>
              <div className="flex justify-between px-[16px] py-[12px]">
                <span className="text-body-sm text-on-surface-variant">Amount</span>
                <span className="text-data-md text-primary">
                  ৳{formatAmount(numericAmount)}
                </span>
              </div>
              <div className="flex justify-between px-[16px] py-[12px]">
                <span className="text-body-sm text-on-surface-variant">
                  Remaining balance
                </span>
                <span className="text-data-md text-on-tertiary-container">
                  ৳{formatAmount(newBalance)}
                </span>
              </div>
            </div>

            <div className="bg-on-tertiary-container/10 border border-on-tertiary-container/30 rounded-xl p-[16px] flex gap-3">
              <span className="material-symbols-outlined text-on-tertiary-container shrink-0">
                shield_lock
              </span>
              <p className="text-body-sm text-on-tertiary-container">
                Your transfer will be processed as one atomic transaction — the
                sender is debited and the receiver credited in the same ledger
                commit. No double-spend, no partial state.
              </p>
            </div>

            {error && (
              <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-2">
                <span className="material-symbols-outlined">error</span>
                <p className="text-body-md">{error}</p>
              </div>
            )}
          </div>

          <button
            type="button"
            disabled={submitting}
            onClick={handleConfirm}
            className="w-full bg-primary text-on-primary text-label-md py-4 rounded-full hover:opacity-90 transition-all shadow-[0_4px_14px_rgba(0,0,0,0.15)] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {submitting ? (
              <div className="animate-spin w-5 h-5 border-2 border-on-primary border-t-transparent rounded-full" />
            ) : (
              <>
                <span className="material-symbols-outlined text-[18px]">
                  check_circle
                </span>
                Confirm Transfer
              </>
            )}
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => setStep(1)}
            className="w-full border border-outline-variant text-on-surface text-label-md py-4 rounded-full hover:bg-surface-container transition-colors"
          >
            Back to Amount
          </button>
        </section>
      )}
    </div>
  );
}
