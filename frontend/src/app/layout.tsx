import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import LineNamePrompt from "@/components/LineNamePrompt";

export const metadata: Metadata = {
  title: "5-Man Keeper League",
  description: "Fantasy Baseball Keeper League Automation System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <ToastProvider>
          <AuthProvider>
            <Navbar />
            <LineNamePrompt />
            <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
              {children}
            </main>
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
