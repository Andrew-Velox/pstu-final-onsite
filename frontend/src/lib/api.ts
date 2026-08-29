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
