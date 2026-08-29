"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { explainTransfer, type TransferExplain } from "@/lib/api";

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
    second: "2-digit",
  });
}

function truncateHash(hash: string, head = 10, tail = 6): string {
  if (hash.length <= head + tail + 3) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

export default function ExplainPage() {
  const params = useParams<{ id: string }>();
  const transferId = params.id;

  const [data, setData] = useState<TransferExplain | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchExplain = useCallback(async () => {
    if (!transferId) return;
    setLoading(true);
    setError(null);
    try {
      const d = await explainTransfer(transferId);
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to explain transfer");
    } finally {
      setLoading(false);
    }
  }, [transferId]);

  useEffect(() => {
    fetchExplain();
  }, [fetchExplain]);

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
          Could not explain transfer
        </h2>
        <p className="text-body-md text-on-surface-variant mb-6">
          {error ?? "Transfer not found."}
        </p>
        <Link
          href="/transactions"
          className="bg-primary text-on-primary text-label-md px-6 py-3 rounded-full hover:opacity-90 inline-flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          Back to Transactions
        </Link>
      </div>
    );
  }

  return (
    <>
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-[16px]">
        <div>
          <Link
            href="/transactions"
            className="text-label-md text-secondary inline-flex items-center gap-1 mb-[8px] hover:underline"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Back to Transactions
          </Link>
          <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
            Explainability Report
          </h1>
          <p className="text-body-lg text-on-surface-variant mt-[4px]">
            What the ledger actually recorded for transfer{" "}
            <code className="text-data-md text-secondary">
              {truncateHash(data.transfer_id, 8, 6)}
            </code>
            .
          </p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-tertiary-container text-tertiary text-label-md">
          <span className="material-symbols-outlined text-[18px]">verified</span>
          Chain position #{data.chain_position}
        </div>
      </header>

      {/* Headline: sender → receiver */}
      <section className="glass-panel p-[32px] grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] items-center gap-[24px]">
        <PartyCard
          name={data.sender_name}
          role="Sender"
          roleIcon="arrow_upward"
          balanceBefore={data.sender_balance_before}
          balanceAfter={data.sender_balance_after}
          delta={-Number(data.amount)}
        />
        <div className="flex flex-col items-center">
          <div className="text-headline-md text-secondary">৳{formatAmount(data.amount)}</div>
          <div className="material-symbols-outlined text-secondary text-[28px] mt-2">
            arrow_forward
          </div>
          <div className="text-label-md text-on-surface-variant uppercase tracking-wider mt-1">
            atomic
          </div>
        </div>
        <PartyCard
          name={data.receiver_name}
          role="Receiver"
          roleIcon="arrow_downward"
          balanceBefore={data.receiver_balance_before}
          balanceAfter={data.receiver_balance_after}
          delta={Number(data.amount)}
        />
      </section>

      {/* Narrative */}
      <section className="glass-panel p-[24px]">
        <div className="flex items-center gap-2 mb-[12px]">
          <span className="material-symbols-outlined text-secondary">auto_awesome</span>
          <h2 className="text-headline-md text-primary">Plain-English Narrative</h2>
        </div>
        <p className="text-body-lg text-on-surface leading-relaxed">
          {data.narrative}
        </p>
      </section>

      {/* Two ledger entries */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-[24px]">
        {data.entries.map((e) => (
          <div
            key={e.id}
            className={`glass-panel p-[24px] border-l-4 ${
              e.entry_type === "debit"
                ? "border-l-error"
                : "border-l-tertiary"
            }`}
          >
            <div className="flex items-center justify-between mb-[12px]">
              <span
                className={`text-label-md uppercase tracking-wider ${
                  e.entry_type === "debit" ? "text-error" : "text-tertiary"
                }`}
              >
                {e.entry_type === "debit" ? "Debit" : "Credit"}
              </span>
              <span className="text-headline-md text-primary">
                {e.entry_type === "debit" ? "−" : "+"}৳{formatAmount(e.amount)}
              </span>
            </div>
            <div className="space-y-[8px] text-body-sm">
              <KV label="Account" value={e.user_name} />
              <KV label="Created at" value={formatDateTime(e.created_at)} />
              <KV
                label="prev_hash"
                value={truncateHash(e.prev_hash)}
                mono
                full={e.prev_hash}
              />
              <KV
                label="entry_hash"
                value={truncateHash(e.entry_hash)}
                mono
                full={e.entry_hash}
              />
            </div>
          </div>
        ))}
      </section>

      {/* Hash chain visualization */}
      <section className="glass-panel p-[24px]">
        <div className="flex items-center gap-2 mb-[16px]">
          <span className="material-symbols-outlined text-secondary">link</span>
          <h2 className="text-headline-md text-primary">
            Tamper-Evident Hash Chain
          </h2>
        </div>
        <p className="text-body-md text-on-surface-variant mb-[16px]">
          Each ledger entry carries the SHA-256 of the previous entry plus
          its own canonical content. Any tampering with a prior row breaks
          the chain at that point and every subsequent entry.
        </p>
        <ChainVisualization
          entries={data.entries.map((e) => ({
            id: e.id,
            entry_hash: e.entry_hash,
            prev_hash: e.prev_hash,
          }))}
        />
      </section>

      {/* Metadata */}
      <section className="glass-panel p-[24px] grid grid-cols-1 md:grid-cols-3 gap-[16px]">
        <KV label="Status" value={data.status} />
        <KV label="Amount" value={`৳${formatAmount(data.amount)}`} />
        <KV label="Created at" value={formatDateTime(data.created_at)} />
        <KV
          label="Idempotency key"
          value={data.idempotency_key}
          mono
          full={data.idempotency_key}
        />
        <KV
          label="Transfer ID"
          value={truncateHash(data.transfer_id, 8, 6)}
          mono
          full={data.transfer_id}
        />
        <KV label="Chain position" value={`#${data.chain_position}`} />
      </section>
    </>
  );
}

function PartyCard({
  name,
  role,
  roleIcon,
  balanceBefore,
  balanceAfter,
  delta,
}: {
  name: string;
  role: string;
  roleIcon: string;
  balanceBefore: string;
  balanceAfter: string;
  delta: number;
}) {
  const positive = delta > 0;
  return (
    <div className="flex flex-col gap-[8px]">
      <div className="flex items-center gap-2 text-label-md text-on-surface-variant uppercase tracking-wider">
        <span className="material-symbols-outlined text-[18px]">{roleIcon}</span>
        {role}
      </div>
      <p className="text-headline-md text-primary">{name}</p>
      <div className="flex items-baseline gap-[8px] mt-[8px]">
        <span className="text-body-sm text-on-surface-variant">৳{formatAmount(balanceBefore)}</span>
        <span className="material-symbols-outlined text-on-surface-variant text-[16px]">arrow_forward</span>
        <span
          className={`text-headline-md ${
            positive ? "text-tertiary" : "text-error"
          }`}
        >
          ৳{formatAmount(balanceAfter)}
        </span>
      </div>
      <span
        className={`text-label-md ${
          positive ? "text-tertiary" : "text-error"
        }`}
      >
        {positive ? "+" : "−"}৳{formatAmount(Math.abs(delta))}
      </span>
    </div>
  );
}

function KV({
  label,
  value,
  mono,
  full,
}: {
  label: string;
  value: string;
  mono?: boolean;
  full?: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
        {label}
      </span>
      <span
        className={`text-body-md text-primary break-all ${mono ? "text-data-md" : ""}`}
        title={full}
      >
        {value}
      </span>
    </div>
  );
}

function ChainVisualization({
  entries,
}: {
  entries: { id: string; entry_hash: string; prev_hash: string }[];
}) {
  return (
    <div className="flex items-center gap-[8px] overflow-x-auto py-[8px]">
      <ChainNode label="GENESIS" hash={"0".repeat(64)} />
      {entries.map((e) => (
        <div key={e.id} className="flex items-center gap-[8px]">
          <span className="material-symbols-outlined text-secondary text-[24px]">
            arrow_forward
          </span>
          <ChainNode
            label={e.id.slice(0, 6)}
            hash={e.entry_hash}
          />
        </div>
      ))}
    </div>
  );
}

function ChainNode({ label, hash }: { label: string; hash: string }) {
  return (
    <div className="flex flex-col items-center bg-surface-container border border-outline-variant rounded-lg px-[12px] py-[8px] shrink-0">
      <span className="text-label-md text-secondary uppercase tracking-wider">
        {label}
      </span>
      <code className="text-data-md text-primary mt-[4px]" title={hash}>
        {truncateHash(hash, 6, 4)}
      </code>
    </div>
  );
}
