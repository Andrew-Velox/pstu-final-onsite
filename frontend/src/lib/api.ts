/**
 * FastAPI client — typed wrappers for all backend endpoints.
 *
 * The Next.js config proxies /api/* → http://localhost:8000/*,
 * so we call the backend via relative URLs.
 */

const API_BASE = "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  name: string;
  email: string;
}

export interface BalanceResponse {
  user_id: string;
  balance: number;
}

export interface TransferRequest {
  sender_id: string;
  receiver_id: string;
  amount: string;
  idempotency_key: string;
}

export interface TransferResponse {
  id: string;
  sender_id: string;
  receiver_id: string;
  amount: string;
  status: string;
  idempotency_key: string;
  created_at: string;
  sender_balance: string;
}

export interface MoneyRequestCreate {
  requester_id: string;
  target_id: string;
  amount: string;
}

export interface MoneyRequestResponse {
  id: string;
  requester_id: string;
  target_id: string;
  amount: string;
  status: string;
  created_at: string;
}

export interface TransactionItem {
  transfer_id: string;
  direction: "sent" | "received";
  amount: string;
  counterparty_id: string;
  counterparty_name: string;
  timestamp: string;
}

export interface TransactionListResponse {
  items: TransactionItem[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ─── Users ───────────────────────────────────────────────────────────────────

export async function listUsers(): Promise<User[]> {
  return apiFetch<User[]>("/users");
}

export async function getBalance(userId: string): Promise<BalanceResponse> {
  return apiFetch<BalanceResponse>(`/users/${userId}/balance`);
}

export async function getTransactions(
  userId: string,
  limit = 20,
  offset = 0,
  type: "all" | "sent" | "received" = "all"
): Promise<TransactionListResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    type,
  });
  return apiFetch<TransactionListResponse>(
    `/users/${userId}/transactions?${params}`
  );
}

// ─── Transfers ───────────────────────────────────────────────────────────────

export async function createTransfer(
  data: TransferRequest
): Promise<TransferResponse> {
  return apiFetch<TransferResponse>("/transfers", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ─── Money Requests ──────────────────────────────────────────────────────────

export async function createMoneyRequest(
  data: MoneyRequestCreate
): Promise<MoneyRequestResponse> {
  return apiFetch<MoneyRequestResponse>("/requests", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listMoneyRequests(
  userId: string
): Promise<MoneyRequestResponse[]> {
  return apiFetch<MoneyRequestResponse[]>(`/requests?user_id=${userId}`);
}

export async function approveRequest(
  requestId: string,
  userId: string
): Promise<MoneyRequestResponse> {
  return apiFetch<MoneyRequestResponse>(`/requests/${requestId}/approve`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function declineRequest(
  requestId: string,
  userId: string
): Promise<MoneyRequestResponse> {
  return apiFetch<MoneyRequestResponse>(`/requests/${requestId}/decline`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

// ─── User Registration ──────────────────────────────────────────────────────

export async function createUser(input: {
  name: string;
  email: string;
}): Promise<User> {
  return apiFetch<User>("/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// ─── x402 hardening ─────────────────────────────────────────────────────────

export interface X402Info {
  version: number;
  capabilities: string[];
  rateLimit: {
    burst: number;
    refillPerSecond: number;
    activeBuckets: number;
  };
}

export interface X402Bucket {
  key: string;
  tokensRemaining: number;
}

export interface X402Usage {
  buckets: X402Bucket[];
}

export interface X402SignResponse {
  timestamp: string;
  signature: string;
  algorithm: string;
  bodyLength: number;
}

export async function x402Info(): Promise<X402Info> {
  return apiFetch<X402Info>("/x402/info");
}

export async function x402Usage(): Promise<X402Usage> {
  return apiFetch<X402Usage>("/x402/usage");
}

export async function x402Sign(body: object): Promise<X402SignResponse> {
  return apiFetch<X402SignResponse>("/x402/sign", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ─── Transaction Explainability Engine ──────────────────────────────────────

export interface LedgerEntryExplain {
  id: string;
  user_id: string;
  user_name: string;
  entry_type: "debit" | "credit";
  amount: string;
  created_at: string;
  prev_hash: string;
  entry_hash: string;
}

export interface TransferExplain {
  transfer_id: string;
  sender_id: string;
  sender_name: string;
  receiver_id: string;
  receiver_name: string;
  amount: string;
  status: string;
  idempotency_key: string;
  created_at: string;
  sender_balance_before: string;
  sender_balance_after: string;
  receiver_balance_before: string;
  receiver_balance_after: string;
  entries: LedgerEntryExplain[];
  narrative: string;
  chain_position: number;
}

export async function explainTransfer(
  transferId: string
): Promise<TransferExplain> {
  return apiFetch<TransferExplain>(`/transfers/${transferId}/explain`);
}

// ─── Money Movement Recovery Center ─────────────────────────────────────────

export interface RecoverySummary {
  total_transfers: number;
  completed: number;
  failed: number;
  replayable: number;
  pending_requests: number;
}

export interface ReplayImpact {
  sender_balance_after: string;
  receiver_balance_after: string;
  sender_has_sufficient_funds: boolean;
  note: string;
}

export interface ReplayResponse {
  replayed: boolean;
  transfer_id: string;
  note: string;
  sender_balance: string | null;
}

export async function getRecoverySummary(): Promise<RecoverySummary> {
  return apiFetch<RecoverySummary>("/recovery/summary");
}

export async function getReplayImpact(
  transferId: string
): Promise<ReplayImpact> {
  return apiFetch<ReplayImpact>(`/recovery/replay/${transferId}/impact`);
}

export async function replayTransfer(
  transferId: string
): Promise<ReplayResponse> {
  return apiFetch<ReplayResponse>("/recovery/replay", {
    method: "POST",
    body: JSON.stringify({ transfer_id: transferId }),
  });
}

// ─── Money Movement Protection / Dispute Center ────────────────────────────────

export type DisputeStatus =
  | "filed"
  | "under_review"
  | "resolved_for_sender"
  | "resolved_for_receiver"
  | "auto_refunded"
  | "rejected";

export type DisputeRole = "complainant" | "respondent";

export interface DisputeTimelineEntry {
  at: string;
  actor: string;
  event: string;
  detail: string | null;
}

export interface DisputeCreateBody {
  transfer_id: string;
  complainant_id: string;
  screenshot_url: string;
  claimed_amount: string | number;
  requested_amount: string | number;
  narrative?: string | null;
}

export interface DisputeRespondBody {
  user_id: string;
  response: string;
  accept_refund: boolean;
}

export interface DisputeAdminResolveBody {
  admin_id: string;
  resolution: "refund_sender" | "release_receiver";
  note?: string | null;
}

export interface DisputeDetail {
  id: string;
  transfer_id: string;
  complainant_id: string;
  complainant_name: string;
  respondent_id: string;
  respondent_name: string;
  screenshot_url: string;
  claimed_amount: string;
  requested_amount: string;
  amount_delta: string;
  narrative: string | null;
  status: DisputeStatus;
  hold_expires_at: string;
  days_until_hold_expires: number;
  receiver_response: string | null;
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
  timeline: DisputeTimelineEntry[];
}

export interface DisputeSummary {
  id: string;
  transfer_id: string;
  counterparty_name: string;
  counterparty_id: string;
  role: DisputeRole;
  amount: string;
  status: DisputeStatus;
  hold_expires_at: string;
  days_until_hold_expires: number;
  created_at: string;
}

export interface DisputeListResponse {
  items: DisputeSummary[];
  total: number;
  active_holds: number;
  auto_refunds_pending: number;
}

export interface NotificationItem {
  id: string;
  kind: string;
  title: string;
  body: string;
  dispute_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  unread_count: number;
}

export interface AvailableBalanceResponse {
  user_id: string;
  balance: string;
  held: string;
  available: string;
}

export async function fileDispute(
  body: DisputeCreateBody
): Promise<DisputeDetail> {
  return apiFetch<DisputeDetail>("/disputes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listDisputes(userId: string): Promise<DisputeListResponse> {
  return apiFetch<DisputeListResponse>(
    `/disputes?user_id=${encodeURIComponent(userId)}`
  );
}

export async function getDispute(disputeId: string): Promise<DisputeDetail> {
  return apiFetch<DisputeDetail>(`/disputes/${disputeId}`);
}

export async function respondToDispute(
  disputeId: string,
  body: DisputeRespondBody
): Promise<DisputeDetail> {
  return apiFetch<DisputeDetail>(`/disputes/${disputeId}/respond`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function adminResolveDispute(
  disputeId: string,
  body: DisputeAdminResolveBody
): Promise<DisputeDetail> {
  return apiFetch<DisputeDetail>(`/disputes/${disputeId}/admin-resolve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listNotifications(
  userId: string
): Promise<NotificationListResponse> {
  return apiFetch<NotificationListResponse>(
    `/disputes/notifications?user_id=${encodeURIComponent(userId)}`
  );
}

export async function markAllNotificationsRead(
  userId: string
): Promise<{ marked_read: number }> {
  return apiFetch<{ marked_read: number }>(
    `/disputes/notifications/read-all?user_id=${encodeURIComponent(userId)}`,
    { method: "POST" }
  );
}

export async function getAvailableBalance(
  userId: string
): Promise<AvailableBalanceResponse> {
  return apiFetch<AvailableBalanceResponse>(
    `/users/${userId}/available-balance`
  );
}
