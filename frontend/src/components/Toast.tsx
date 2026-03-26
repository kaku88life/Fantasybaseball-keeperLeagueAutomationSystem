"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

interface ToastItem {
  id: number;
  message: string;
  type: "success" | "info" | "error";
}

interface ToastContextType {
  showToast: (message: string, type?: "success" | "info" | "error") => void;
}

const ToastContext = createContext<ToastContextType>({
  showToast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

let nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback(
    (message: string, type: "success" | "info" | "error" = "info") => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 3500);
    },
    [],
  );

  const contextValue = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      {/* Toast container */}
      <div className="fixed top-16 right-4 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`animate-slide-in rounded-lg px-4 py-3 text-sm font-medium shadow-lg ${
              t.type === "success"
                ? "bg-green-600 text-white"
                : t.type === "error"
                  ? "bg-red-600 text-white"
                  : "bg-gray-800 text-white"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
