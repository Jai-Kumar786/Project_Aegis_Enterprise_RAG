"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BookOpen,
  Trash2,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Lock,
  Eye,
  EyeOff,
  X,
  XCircle,
  AlertTriangle,
} from "lucide-react";

interface Policy {
  document_id: string;
  category: string | null;
}

// ── Delete Confirmation Modal ────────────────────────────────────────────
function DeleteModal({
  docId,
  onConfirm,
  onCancel,
}: {
  docId: string;
  onConfirm: (passcode: string) => void;
  onCancel: () => void;
}) {
  const [code, setCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) { setError("Passcode cannot be empty."); return; }
    setError("");
    onConfirm(code.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
      <div
        className="relative w-full max-w-sm rounded-2xl border border-white/10 shadow-2xl"
        style={{ background: "hsl(220 20% 7%)" }}
      >
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-white/30 hover:text-white/70 transition-colors"
        >
          <X size={18} />
        </button>

        <div className="p-6">
          {/* Warning header */}
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-red-500/15 border border-red-500/30 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
            <div>
              <h3 className="text-white font-semibold text-[15px]">Delete Policy</h3>
              <p className="text-white/40 text-xs mt-0.5">This action cannot be undone</p>
            </div>
          </div>

          <p className="text-white/50 text-xs mb-5 leading-relaxed bg-red-500/5 border border-red-500/10 rounded-xl p-3">
            You are about to permanently delete{" "}
            <span className="text-white/80 font-mono font-semibold">{docId}</span>{" "}
            and all its indexed chunks from the database.
          </p>

          <form onSubmit={handleSubmit}>
            {/* Passcode input */}
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck size={13} className="text-white/30" />
              <span className="text-white/40 text-xs">Enter admin passcode to confirm</span>
            </div>
            <div className="relative mb-4">
              <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                type={showCode ? "text" : "password"}
                value={code}
                onChange={(e) => { setCode(e.target.value); setError(""); }}
                placeholder="Enter passcode..."
                autoFocus
                className={`w-full bg-black/30 border ${
                  error ? "border-red-500/60" : "border-white/10"
                } rounded-xl pl-10 pr-10 py-2.5 text-sm text-white placeholder:text-white/30 outline-none focus:border-red-500/60 focus:ring-1 focus:ring-red-500/20 transition-all`}
              />
              <button
                type="button"
                onClick={() => setShowCode((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors"
              >
                {showCode ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>

            {error && (
              <p className="text-red-400 text-xs mb-3 flex items-center gap-1.5">
                <XCircle size={13} /> {error}
              </p>
            )}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={onCancel}
                className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/50 hover:text-white hover:border-white/20 text-sm transition-all"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                <Trash2 size={14} /> Delete
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

// ── Main PolicyManager Component ─────────────────────────────────────────
export function PolicyManager() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchPolicies = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:8000/documents");
      const data = await res.json();
      setPolicies(data.documents ?? []);
    } catch {
      // Silently fail — backend may not be running yet
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchPolicies(); }, [fetchPolicies]);

  const handleDeleteConfirm = async (passcode: string) => {
    if (!deleteTarget) return;
    const docId = deleteTarget;
    setDeleteTarget(null);
    setDeletingId(docId);
    setStatusMsg(null);

    try {
      const res = await fetch(`http://127.0.0.1:8000/documents/${encodeURIComponent(docId)}`, {
        method: "DELETE",
        headers: { "X-Upload-Passcode": passcode },
      });
      const data = await res.json();

      if (res.ok) {
        setStatusMsg({ type: "success", text: data.message });
        setPolicies((prev) => prev.filter((p) => p.document_id !== docId));
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Deletion failed." });
      }
    } catch {
      setStatusMsg({ type: "error", text: "Network error. Could not connect to backend." });
    } finally {
      setDeletingId(null);
    }
  };

  if (policies.length === 0 && !isLoading) return null;

  return (
    <>
      {deleteTarget && (
        <DeleteModal
          docId={deleteTarget}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      <div className="glass p-4 rounded-2xl border border-white/10 w-full max-w-sm shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-white/90 font-medium flex items-center gap-2 text-sm">
            <BookOpen size={15} className="text-purple-400" />
            Indexed Policies
          </h3>
          <button
            onClick={fetchPolicies}
            disabled={isLoading}
            title="Refresh list"
            className="text-white/30 hover:text-white/70 transition-colors"
          >
            <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* Policy list */}
        <ul className="space-y-1.5 max-h-48 overflow-y-auto pr-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
          {policies.map((p) => (
            <li
              key={p.document_id}
              className="flex items-center justify-between gap-2 bg-black/30 border border-white/5 rounded-xl px-3 py-2 group"
            >
              <div className="min-w-0 flex-1">
                <p className="text-white/80 text-[13px] font-mono break-all leading-tight">{p.document_id}</p>
                <p className="text-white/30 text-[10px] mt-1">{p.category ?? "General"}</p>
              </div>
              <button
                onClick={() => setDeleteTarget(p.document_id)}
                disabled={deletingId === p.document_id}
                title={`Delete ${p.document_id}`}
                className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-white/20 hover:text-red-400 hover:bg-red-500/10 transition-all opacity-0 group-hover:opacity-100"
              >
                {deletingId === p.document_id ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Trash2 size={13} />
                )}
              </button>
            </li>
          ))}
        </ul>

        {/* Status message */}
        {statusMsg && (
          <div
            className={`mt-3 p-2.5 rounded-xl text-xs flex items-start gap-2 ${
              statusMsg.type === "success"
                ? "bg-green-500/10 text-green-400 border border-green-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}
          >
            <span>{statusMsg.text}</span>
          </div>
        )}
      </div>
    </>
  );
}
