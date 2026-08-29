import type { Metadata } from "next";
import "./globals.css";
import TopNav from "@/components/TopNav";
import SideNav from "@/components/SideNav";
import { UserProvider } from "@/lib/UserContext";

export const metadata: Metadata = {
  title: "TrustLedger — Money Movement Dashboard",
  description:
    "Double-entry ledger system for peer-to-peer money transfers. Concurrent-safe, idempotent, auditable.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/* Google Fonts */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        {/* Material Symbols */}
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-background text-on-surface antialiased min-h-screen">
        <UserProvider>
          <TopNav />
          <SideNav />
          <main className="pt-16 md:pl-64 min-h-screen pb-[32px]">
            <div className="max-w-[1280px] mx-auto px-[16px] md:px-[40px] pt-[32px] space-y-[32px]">
              {children}
            </div>
          </main>
        </UserProvider>
      </body>
    </html>
  );
}
