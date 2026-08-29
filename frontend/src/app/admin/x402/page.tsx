"use client";

import { useCallback, useEffect, useState } from "react";
import {
  x402Info,
  x402Sign,
  x402Usage,
  type X402Bucket,
  type X402Info,
  type X402SignResponse,
} from "@/lib/api";

const SAMPLE_PAYLOAD = `{
  "sender_id": "11111111-2222-3333-4444-555555555555",
  "receiver_id": "66666666-7777-8888-9999-000000000000",
  "amount": "100.00"
}`;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    hour12: false,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function truncateKey(key: string): string {
  if (key.length <= 18) return key;
  return `${key.slice(0, 14)}…`;
}

export default function X402AdminPage() {
  const [info, setInfo] = useState<X402Info | null>(null);
  const [buckets, setBuckets] = useState<X402Bucket[]>([]);
  const [signPayload, setSignPayload] = useState(SAMPLE_PAYLOAD);
  const [signResult, setSignResult] = useState<X402SignResponse | null>(null);
  const [signError, setSignError] = useState<string | null>(null);
  const [signing, setSigning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [i, u] = await Promise.all([x402Info(), x402Usage()]);
      setInfo(i);
      setBuckets(u.buckets);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach /x402 endpoints");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInfo();
  }, [fetchInfo]);

  // Auto-refresh bucket snapshot every 3s so the dashboard feels alive.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const u = await x402Usage();
        setBuckets(u.buckets);
      } catch {
        /* keep last value */
      }
    }, 3000);
    return () => clearInterval(id);
  }, []);

  async function handleSign() {
    setSigning(true);
    setSignError(null);
    setSignResult(null);
    try {
      const body = signPayload.trim().length ? signPayload : "{}";
      const parsed = JSON.parse(body);
      const res = await x402Sign(parsed);
      setSignResult(res);
    } catch (e) {
      setSignError(e instanceof Error ? e.message : "Sign failed");
    } finally {
      setSigning(false);
    }
  }

  const burst = info?.rateLimit.burst ?? 0;
  const maxBucket = Math.max(burst, ...buckets.map((b) => b.tokensRemaining), 1);

  return (
    <>
      <header>
        <h1 className="text-headline-lg-mobile md:text-headline-lg text-primary">
          x402 Admin Panel
        </h1>
        <p className="text-body-lg text-on-surface-variant mt-[4px]">
          Defence-in-depth: HMAC-SHA256 request signing + token-bucket rate limiting.
        </p>
      </header>

      {error && (
        <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-3">
          <span className="material-symbols-outlined">error</span>
          <p className="text-body-md">{error}</p>
        </div>
      )}

      {/* Capabilities */}
      <section className="glass-panel p-[24px]">
        <div className="flex items-center justify-between mb-[16px]">
          <h2 className="text-headline-md text-primary flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary">
              verified_user
            </span>
            Capabilities
          </h2>
          <button
            onClick={fetchInfo}
            className="text-label-md text-secondary hover:underline flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">refresh</span>
            Refresh
          </button>
        </div>
        {loading && !info ? (
          <div className="h-10 bg-surface-container animate-pulse rounded" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-[16px]">
            {info?.capabilities.map((cap) => (
              <div
                key={cap}
                className="bg-surface-container rounded-xl px-[16px] py-[12px] flex items-center gap-3"
              >
                <span className="material-symbols-outlined text-on-tertiary-container">
                  check_circle
                </span>
                <span className="text-body-md text-primary font-medium">
                  {cap.replace(/-/g, " ")}
                </span>
              </div>
            ))}
            {info && (
              <div className="bg-surface-container rounded-xl px-[16px] py-[12px] flex items-center gap-3">
                <span className="material-symbols-outlined text-secondary">
                  schedule
                </span>
                <span className="text-body-md text-primary">
                  {info.rateLimit.refillPerSecond} tok/s · {info.rateLimit.burst} burst
                </span>
              </div>
            )}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-[24px]">
        {/* HMAC signing demo */}
        <section className="glass-panel p-[24px] space-y-[16px]">
          <h2 className="text-headline-md text-primary flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary">draw</span>
            Sign a request
          </h2>
          <p className="text-body-sm text-on-surface-variant">
            POST any JSON body to <code className="text-data-md">/x402/sign</code> to mint
            a replay-proof HMAC-SHA256 timestamp.
          </p>

          <label className="text-label-md text-on-surface-variant uppercase tracking-wider block">
            Payload (JSON)
          </label>
          <textarea
            value={signPayload}
            onChange={(e) => setSignPayload(e.target.value)}
            className="w-full bg-surface-container border border-outline-variant rounded-xl p-[12px] text-data-md text-primary focus:ring-2 focus:ring-secondary focus:outline-none min-h-[140px] resize-y"
            spellCheck={false}
          />

          <button
            onClick={handleSign}
            disabled={signing}
            className="w-full bg-primary text-on-primary text-label-md py-3 rounded-full hover:opacity-90 transition-all shadow-[0_4px_14px_rgba(0,0,0,0.15)] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {signing ? (
              <div className="animate-spin w-5 h-5 border-2 border-on-primary border-t-transparent rounded-full" />
            ) : (
              <>
                <span className="material-symbols-outlined text-[18px]">lock</span>
                Mint Signature
              </>
            )}
          </button>

          {signError && (
            <div className="bg-error-container text-on-error-container px-4 py-3 rounded-xl flex items-center gap-2">
              <span className="material-symbols-outlined">error</span>
              <p className="text-body-sm">{signError}</p>
            </div>
          )}

          {signResult && (
            <div className="bg-surface-container rounded-xl p-[16px] space-y-3">
              <div>
                <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
                  Timestamp
                </span>
                <p className="text-data-md text-primary">{formatTime(signResult.timestamp)}</p>
              </div>
              <div>
                <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
                  {signResult.algorithm}
                </span>
                <p className="text-data-md text-secondary break-all">
                  {signResult.signature}
                </p>
              </div>
              <div className="flex justify-between">
                <span className="text-label-md text-on-surface-variant uppercase tracking-wider">
                  Body length
                </span>
                <span className="text-data-md text-primary">
                  {signResult.bodyLength} bytes
                </span>
              </div>
              <p className="text-body-sm text-on-tertiary-container bg-on-tertiary-container/10 rounded-lg p-[12px] flex gap-2">
                <span className="material-symbols-outlined text-[16px] shrink-0">
                  verified
                </span>
                Send this timestamp + signature in{" "}
                <code className="text-data-md">X-Timestamp</code> and{" "}
                <code className="text-data-md">X-Signature</code> headers.
              </p>
            </div>
          )}
        </section>

        {/* Rate limit snapshot */}
        <section className="glass-panel p-[24px] space-y-[16px]">
          <h2 className="text-headline-md text-primary flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary">speed</span>
            Live rate-limit buckets
          </h2>
          <p className="text-body-sm text-on-surface-variant">
            Per-client token buckets, refilled at{" "}
            <span className="text-data-md text-primary">
              {info?.rateLimit.refillPerSecond ?? "–"} tok/s
            </span>
            . Auto-refreshes every 3 s.
          </p>

          {buckets.length === 0 ? (
            <div className="bg-surface-container rounded-xl p-[24px] text-center text-on-surface-variant">
              <span className="material-symbols-outlined text-[32px] mb-2 block">
                hourglass_empty
              </span>
              <p className="text-body-sm">
                No active buckets yet. Trigger a request from the dashboard or
                <code className="text-data-md bg-surface px-1 rounded mx-1">/send</code>
                to populate one.
              </p>
            </div>
          ) : (
            <ul className="space-y-[12px] max-h-[420px] overflow-auto pr-1">
              {buckets.map((b) => {
                const pct = (b.tokensRemaining / maxBucket) * 100;
                const low = b.tokensRemaining < burst * 0.2;
                return (
                  <li
                    key={b.key}
                    className="bg-surface-container rounded-xl px-[16px] py-[12px]"
                  >
                    <div className="flex items-center justify-between mb-[6px]">
                      <span
                        className="text-data-md text-primary"
                        title={b.key}
                      >
                        {truncateKey(b.key)}
                      </span>
                      <span
                        className={`text-data-md font-medium ${
                          low ? "text-error" : "text-primary"
                        }`}
                      >
                        {b.tokensRemaining.toFixed(2)} / {burst}
                      </span>
                    </div>
                    <div className="h-2 bg-surface-container-low rounded-full overflow-hidden">
                      <div
                        style={{ width: `${Math.min(100, pct)}%` }}
                        className={`h-full rounded-full transition-all ${
                          low ? "bg-error" : "bg-on-tertiary-container"
                        }`}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="bg-secondary/10 border border-secondary/20 rounded-xl p-[12px] flex gap-3">
            <span className="material-symbols-outlined text-secondary shrink-0">
              info
            </span>
            <p className="text-body-sm text-on-surface-variant">
              Buckets refill smoothly so clients get burst capacity up to{" "}
              <span className="text-primary">{burst} tokens</span>, then sustain at{" "}
              <span className="text-primary">
                {info?.rateLimit.refillPerSecond ?? "1"} / s
              </span>
              . Empty buckets return <code className="text-data-md">429</code>.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}