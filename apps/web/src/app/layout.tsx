import { AppFrame } from "@/components/app-frame";
import { QueryProvider } from "@/components/query-provider";
import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "PowerForge",
  description: "Electrical engineering data extraction platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <QueryProvider>
          <Suspense fallback={<main>{children}</main>}>
            <AppFrame>{children}</AppFrame>
          </Suspense>
        </QueryProvider>
      </body>
    </html>
  );
}
