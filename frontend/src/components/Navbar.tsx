"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <nav className="bg-gray-900 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="text-lg font-bold">
              5-Man Keeper League
            </Link>
            {user && (
              <>
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
              </>
            )}
          </div>

          <div className="flex items-center gap-4">
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
        </div>
      </div>
    </nav>
  );
}
