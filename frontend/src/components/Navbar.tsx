"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function Navbar() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className="bg-gray-900 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          {/* Logo + desktop nav links */}
          <div className="flex items-center gap-2 sm:gap-6">
            <Link href="/" className="text-base font-bold sm:text-lg whitespace-nowrap">
              5-Man Keeper
            </Link>
            {user && (
              <div className="hidden sm:flex items-center gap-4">
                <Link
                  href={`/${new Date().getFullYear()}`}
                  className="text-sm text-gray-300 hover:text-white"
                >
                  聯盟 League
                </Link>
                <Link
                  href="/rules"
                  className="text-sm text-gray-300 hover:text-white"
                >
                  規則 Rules
                </Link>
                {user.is_commissioner && (
                  <Link
                    href="/commissioner"
                    className="text-sm text-yellow-400 hover:text-yellow-300"
                  >
                    Commissioner
                  </Link>
                )}
              </div>
            )}
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
                  onClick={logout}
                  className="text-sm text-gray-400 hover:text-white"
                >
                  Logout
                </button>
              </>
            ) : (
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002"}/api/auth/yahoo/login`}
                className="rounded bg-indigo-600 px-3 py-1.5 text-sm hover:bg-indigo-500"
              >
                Login with Yahoo
              </a>
            )}
          </div>

          {/* Mobile: login button (when not logged in) or hamburger */}
          <div className="flex sm:hidden items-center">
            {user ? (
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
            ) : (
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002"}/api/auth/yahoo/login`}
                className="rounded bg-indigo-600 px-3 py-1.5 text-sm hover:bg-indigo-500"
              >
                Login
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Mobile dropdown menu */}
      {menuOpen && user && (
        <div className="border-t border-gray-700 sm:hidden">
          <div className="px-4 py-3 space-y-1">
            <Link
              href={`/${new Date().getFullYear()}`}
              className="block rounded px-3 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white"
              onClick={() => setMenuOpen(false)}
            >
              聯盟 League
            </Link>
            <Link
              href="/rules"
              className="block rounded px-3 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white"
              onClick={() => setMenuOpen(false)}
            >
              規則 Rules
            </Link>
            {user.is_commissioner && (
              <Link
                href="/commissioner"
                className="block rounded px-3 py-2 text-sm text-yellow-400 hover:bg-gray-800 hover:text-yellow-300"
                onClick={() => setMenuOpen(false)}
              >
                Commissioner
              </Link>
            )}
          </div>
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
              onClick={() => { logout(); setMenuOpen(false); }}
              className="mt-2 text-sm text-gray-400 hover:text-white"
            >
              Logout
            </button>
          </div>
        </div>
      )}
    </nav>
  );
}
