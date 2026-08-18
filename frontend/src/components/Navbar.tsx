"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";

// Centralized nav links -- add/remove here to update both desktop & mobile
const PUBLIC_LINKS = [
  { href: "/rules", label: "規則 Rules" },
  { href: "/players", label: "球員 Players" },
  { href: "/draft-strategy", label: "選秀 Draft" },
];

const AUTH_LINKS = [
  { href: `/${new Date().getFullYear()}`, label: "聯盟 League" },
  { href: "/analytics", label: "統計 Stats" },
  { href: "/radar", label: "雷達 Radar" },
];

export default function Navbar() {
  const { user, logout } = useAuth();
  const { showToast } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    showToast("已登出，如需操作請先登入帳號", "info");
  };

  return (
    <nav className="bg-gray-900 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          {/* Logo + desktop nav links */}
          <div className="flex items-center gap-2 sm:gap-6">
            <Link href="/" className="text-base font-bold sm:text-lg whitespace-nowrap">
              5-Man Keepers
            </Link>
            <div className="hidden sm:flex items-center gap-4">
              {PUBLIC_LINKS.map((link) => (
                <Link key={link.href} href={link.href} className="text-sm text-gray-300 hover:text-white">
                  {link.label}
                </Link>
              ))}
              {user && (
                <>
                  {AUTH_LINKS.map((link) => (
                    <Link key={link.href} href={link.href} className="text-sm text-gray-300 hover:text-white">
                      {link.label}
                    </Link>
                  ))}
                  {user.is_commissioner && (
                    <Link
                      href="/commissioner"
                      className="text-sm text-yellow-400 hover:text-yellow-300"
                    >
                      Commissioner
                    </Link>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Desktop user info */}
          <div className="hidden sm:flex items-center gap-4">
            {user ? (
              <>
                <span className="text-sm text-gray-300">
                  {user.yahoo_nickname}
                  {user.manager_name && (
                    <span className="ml-1 text-gray-500">
                      ({user.manager_name})
                    </span>
                  )}
                  {user.is_commissioner && (
                    <span className="ml-1 rounded bg-yellow-600 px-1.5 py-0.5 text-xs">
                      CM
                    </span>
                  )}
                </span>
                <button
                  onClick={handleLogout}
                  className="text-sm text-gray-400 hover:text-white"
                >
                  Logout
                </button>
              </>
            ) : (
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002"}/api/auth/yahoo/login`}
                className="rounded bg-indigo-600 px-4 py-2 text-sm hover:bg-indigo-500"
              >
                Login with Yahoo
              </a>
            )}
          </div>

          {/* Mobile: hamburger menu */}
          <div className="flex sm:hidden items-center gap-2">
            {!user && (
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002"}/api/auth/yahoo/login`}
                className="rounded bg-indigo-600 px-4 py-2 text-sm hover:bg-indigo-500"
              >
                Login
              </a>
            )}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="p-2 text-gray-300 hover:text-white"
              aria-label="Toggle menu"
            >
              {menuOpen ? (
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile dropdown menu */}
      {menuOpen && (
        <div className="border-t border-gray-700 sm:hidden">
          <div className="px-4 py-3 space-y-1">
            {PUBLIC_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="block rounded px-3 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white"
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            {user && (
              <>
                {AUTH_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="block rounded px-3 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white"
                    onClick={() => setMenuOpen(false)}
                  >
                    {link.label}
                  </Link>
                ))}
                {user.is_commissioner && (
                  <Link
                    href="/commissioner"
                    className="block rounded px-3 py-2 text-sm text-yellow-400 hover:bg-gray-800 hover:text-yellow-300"
                    onClick={() => setMenuOpen(false)}
                  >
                    Commissioner
                  </Link>
                )}
              </>
            )}
          </div>
          {user && (
            <div className="border-t border-gray-700 px-4 py-3">
              <p className="text-sm text-gray-300">
                {user.yahoo_nickname}
                {user.manager_name && (
                  <span className="ml-1 text-gray-500">({user.manager_name})</span>
                )}
                {user.is_commissioner && (
                  <span className="ml-1 rounded bg-yellow-600 px-1.5 py-0.5 text-xs">CM</span>
                )}
              </p>
              <button
                onClick={() => { handleLogout(); setMenuOpen(false); }}
                className="mt-2 text-sm text-gray-400 hover:text-white"
              >
                Logout
              </button>
            </div>
          )}
        </div>
      )}
    </nav>
  );
}
