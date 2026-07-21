import type { ReactNode } from "react";
import { Manrope } from "next/font/google";

import AppShell from "@/components/AppShell";
import AuthSessionProvider from "@/components/AuthSessionProvider";

import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

/** Root layout with global styles and top navigation. */
export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en" className={manrope.variable}>
      <body className="min-h-screen font-sans text-slate-100 antialiased">
        <AuthSessionProvider>
          <AppShell>{children}</AppShell>
        </AuthSessionProvider>
      </body>
    </html>
  );
}
