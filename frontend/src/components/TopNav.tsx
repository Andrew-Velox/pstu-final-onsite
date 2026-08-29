"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useUser } from "@/lib/UserContext";
import { listNotifications } from "@/lib/api";

export default function TopNav() {
  const { users, activeUser, setActiveUser } = useUser();
  const [unreadCount, setUnreadCount] = useState(0);

  const refreshUnread = useCallback(async () => {
    if (!activeUser) {
      setUnreadCount(0);
      return;
    }
    try {
      const res = await listNotifications(activeUser.id);
      setUnreadCount(res.unread_count);
    } catch (err) {
      // Silent — notification badge is decorative.
      console.warn("[TopNav] failed to load notifications:", err);
    }
  }, [activeUser]);

  useEffect(() => {
    refreshUnread();
    const interval = setInterval(refreshUnread, 30_000);
    return () => clearInterval(interval);
  }, [refreshUnread]);

  return (
    <nav className="fixed top-0 left-0 w-full z-50 flex justify-between items-center px-4 md:px-[40px] h-16 bg-surface/80 backdrop-blur-md border-b border-outline-variant">
      {/* Brand */}
      <div className="text-headline-md font-bold text-secondary">
        TrustLedger
      </div>

      {/* Right side */}
      <div className="flex items-center gap-[16px]">
        {/* Search bar (desktop) */}
        <div className="hidden md:flex items-center bg-surface-container rounded-full px-4 py-2 border border-outline-variant">
          <span className="material-symbols-outlined text-on-surface-variant text-body-sm mr-2">
            search
          </span>
          <input
            className="bg-transparent border-none outline-none text-body-sm text-on-surface w-48 placeholder:text-on-surface-variant"
            placeholder="Search transactions..."
            type="text"
          />
        </div>

        {/* User Switcher */}
        <div className="relative">
          <select
            className="appearance-none bg-surface-container border border-outline-variant rounded-full px-4 py-2 pr-8 text-body-sm text-on-surface cursor-pointer focus:ring-2 focus:ring-secondary focus:outline-none"
            value={activeUser?.id || ""}
            onChange={(e) => {
              const user = users.find((u) => u.id === e.target.value);
              if (user) setActiveUser(user);
            }}
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
            {users.length === 0 && (
              <option value="">No users</option>
            )}
          </select>
          <span className="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-[16px] pointer-events-none">
            expand_more
          </span>
        </div>

        {/* Notifications */}
        <Link
          href="/disputes"
          aria-label="Notifications"
          className="relative hover:bg-surface-container-low transition-colors p-2 rounded-full text-primary inline-flex items-center justify-center"
          onClick={refreshUnread}
        >
          <span className="material-symbols-outlined">notifications</span>
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-error text-on-error text-[10px] font-bold flex items-center justify-center">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Link>

        {/* Avatar */}
        <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center text-on-secondary-container text-body-sm font-bold">
          {activeUser?.name?.charAt(0) || "?"}
        </div>
      </div>
    </nav>
  );
}
