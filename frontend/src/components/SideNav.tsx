"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const mainLinks = [
  { href: "/", icon: "dashboard", label: "Overview" },
  { href: "/send", icon: "send", label: "Send" },
  { href: "/request", icon: "payments", label: "Request" },
  { href: "/transactions", icon: "receipt_long", label: "Transactions" },
];

const footerLinks = [
  { href: "#", icon: "verified_user", label: "Safety Center" },
  { href: "#", icon: "settings", label: "Settings" },
];

export default function SideNav() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-16 h-[calc(100vh-4rem)] w-64 flex flex-col p-[16px] z-40 bg-surface-container-lowest border-r border-outline-variant hidden md:flex">
      {/* Brand block */}
      <div className="flex items-center gap-[8px] mb-[32px] px-2">
        <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-on-primary text-[20px]">
            account_balance
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-headline-md font-bold text-secondary leading-none">
            TrustLedger
          </span>
          <span className="text-label-md text-on-surface-variant leading-tight">
            Transaction Truth
          </span>
        </div>
      </div>

      {/* Main nav links */}
      <nav className="flex flex-col gap-[4px] flex-1">
        {mainLinks.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-[16px] px-4 py-3 rounded-xl transition-all duration-200 ${
                isActive
                  ? "bg-secondary-container/10 text-secondary font-bold translate-x-1"
                  : "text-on-surface-variant hover:text-secondary hover:bg-surface-container translate-x-0 hover:translate-x-1"
              }`}
            >
              <span className="material-symbols-outlined">{link.icon}</span>
              <span className="text-label-md">{link.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer links */}
      <nav className="flex flex-col gap-[4px] mt-auto pt-[16px] border-t border-outline-variant">
        {footerLinks.map((link) => (
          <Link
            key={link.label}
            href={link.href}
            className="flex items-center gap-[16px] text-on-surface-variant hover:text-secondary px-4 py-3 hover:bg-surface-container rounded-xl transition-all duration-200 hover:translate-x-1"
          >
            <span className="material-symbols-outlined">{link.icon}</span>
            <span className="text-label-md">{link.label}</span>
          </Link>
        ))}
      </nav>
    </aside>
  );
}
