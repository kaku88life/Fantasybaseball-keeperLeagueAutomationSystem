"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getYears } from "@/lib/api";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [years, setYears] = useState<number[]>([]);

  useEffect(() => {
    getYears().then(setYears).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (!user) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002";
    return (
      <div className="mx-auto max-w-lg py-20 text-center">
        <h1 className="mb-4 text-3xl font-bold">5-Man Keeper League</h1>
        <p className="mb-8 text-gray-600">
          Fantasy Baseball Keeper League Automation System
        </p>
        <a
          href={`${apiBase}/api/auth/yahoo/login`}
          className="rounded-lg bg-indigo-600 px-6 py-3 text-white hover:bg-indigo-500"
        >
          Login with Yahoo
        </a>
      </div>
    );
  }

  // Redirect to current year or latest available year
  const currentYear = new Date().getFullYear();
  const targetYear = years.includes(currentYear)
    ? currentYear
    : years.length > 0
      ? years[years.length - 1]
      : null;

  if (targetYear) {
    router.push(`/${targetYear}`);
    return null;
  }

  return (
    <div className="py-10 text-center">
      <h1 className="mb-4 text-2xl font-bold">Welcome{user.yahoo_nickname ? `, ${user.yahoo_nickname}` : ""}!</h1>
      {user.manager_name && (
        <p className="text-gray-600">
          Team: {user.manager_name}
          {user.team_name && ` (${user.team_name})`}
        </p>
      )}
      <p className="mt-6 text-gray-500">
        No league data imported yet.
        {user.is_commissioner && " Go to Commissioner panel to import Excel data."}
      </p>
    </div>
  );
}
