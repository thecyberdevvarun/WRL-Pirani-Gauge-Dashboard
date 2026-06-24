import { createContext, useCallback, useContext, useRef, useState } from "react";
import { FiCheckCircle, FiAlertTriangle, FiXCircle, FiInfo } from "react-icons/fi";

const ToastContext = createContext(null);

const STYLES = {
  success: { bg: "bg-emerald-600", icon: FiCheckCircle },
  error: { bg: "bg-rose-600", icon: FiXCircle },
  warn: { bg: "bg-amber-500 text-ink-950", icon: FiAlertTriangle },
  info: { bg: "bg-sky-600", icon: FiInfo },
};

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timerRef = useRef(null);

  const showToast = useCallback((message, type = "success") => {
    clearTimeout(timerRef.current);
    setToast({ message, type, key: Date.now() });
    timerRef.current = setTimeout(() => setToast(null), 3000);
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="fixed top-5 right-5 z-[100] pointer-events-none">
        {toast && (
          <div
            key={toast.key}
            className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-xl text-sm font-semibold text-white animate-[fadeIn_.15s_ease-out] ${
              STYLES[toast.type]?.bg || STYLES.success.bg
            }`}
          >
            {(() => {
              const Icon = STYLES[toast.type]?.icon || FiCheckCircle;
              return <Icon className="text-base shrink-0" />;
            })()}
            {toast.message}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
