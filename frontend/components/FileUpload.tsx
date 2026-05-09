"use client";

import { useState, useRef, useId } from "react";
import { Upload, FileText, Loader2, CheckCircle, XCircle, Lock, ShieldCheck, Eye, EyeOff, X } from "lucide-react";

const ACCEPTED_TYPES = ".md,.txt,.pdf";

function FileIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText size={20} className="text-rose-400" />;
  if (ext === "txt") return <FileText size={20} className="text-amber-400" />;
  return <FileText size={20} className="text-indigo-400" />;
}

function FileBadge({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toUpperCase();
  const colors: Record<string, string> = {
    PDF: "bg-rose-500/20 text-rose-400",
    TXT: "bg-amber-500/20 text-amber-400",
    MD: "bg-indigo-500/20 text-indigo-400",
  };
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${colors[ext ?? ""] ?? "bg-white/10 text-white/50"}`}>
      {ext}
    </span>
  );
}

// ── Passcode Modal ──────────────────────────────────────────────────────
function PasscodeModal({
  onConfirm,
  onCancel,
}: {
  onConfirm: (code: string) => void;
  onCancel: () => void;
}) {
  const [code, setCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [error, setError] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) {
      setError(true);
      return;
    }
    setError(false);
    onConfirm(code.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* Modal */}
      <div
        className="relative w-full max-w-sm rounded-2xl border border-white/10 shadow-2xl"
        style={{ background: "hsl(220 20% 7%)" }}
      >
        {/* Close button */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-white/30 hover:text-white/70 transition-colors"
        >
          <X size={18} />
        </button>

        <div className="p-6">
          {/* Icon + Title */}
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center">
              <ShieldCheck size={20} className="text-indigo-400" />
            </div>
            <div>
              <h3 className="text-white font-semibold text-[15px]">Admin Verification</h3>
              <p className="text-white/40 text-xs mt-0.5">Enter the upload passcode to continue</p>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Password input */}
            <div className="relative mb-4">
              <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                type={showCode ? "text" : "password"}
                value={code}
                onChange={(e) => { setCode(e.target.value); setError(false); }}
                placeholder="Enter passcode..."
                autoFocus
                className={`w-full bg-black/30 border ${
                  error ? "border-red-500/60" : "border-white/10"
                } rounded-xl pl-10 pr-10 py-2.5 text-sm text-white placeholder:text-white/30 outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all`}
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
                <XCircle size={13} /> Passcode cannot be empty.
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
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
              >
                Confirm Upload
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

// ── Main FileUpload Component ────────────────────────────────────────────
export function FileUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setStatusMessage(null);
    }
  };

  // Triggered when user clicks "Upload Document" — opens the modal
  const handleUploadClick = () => {
    if (!file) return;
    setShowModal(true);
  };

  // Triggered when user confirms their passcode in the modal
  const handlePasscodeConfirm = async (passcode: string) => {
    setShowModal(false);
    setIsUploading(true);
    setStatusMessage(null);

    const formData = new FormData();
    formData.append("file", file!);

    try {
      const response = await fetch("http://127.0.0.1:8000/upload", {
        method: "POST",
        headers: { "X-Upload-Passcode": passcode },
        body: formData,
      });
      const result = await response.json();

      if (response.ok) {
        setStatusMessage({ type: "success", text: result.message });
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      } else {
        setStatusMessage({
          type: "error",
          text: result.detail || "Upload failed.",
        });
      }
    } catch {
      setStatusMessage({
        type: "error",
        text: "Network error. Could not connect to the backend.",
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <>
      {showModal && (
        <PasscodeModal
          onConfirm={handlePasscodeConfirm}
          onCancel={() => setShowModal(false)}
        />
      )}

      <div className="glass p-5 rounded-2xl border border-white/10 w-full max-w-sm mb-6 shadow-xl">
        <h3 className="text-white/90 font-medium mb-3 flex items-center gap-2 text-sm">
          <Upload size={16} className="text-indigo-400" /> Upload Policy Document
        </h3>

        <div className="flex items-center gap-3 mb-3">
          <input
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileChange}
            className="hidden"
            ref={fileInputRef}
            id={inputId}
          />
          <label
            htmlFor={inputId}
            className="flex-1 cursor-pointer bg-black/40 hover:bg-black/60 transition-colors border border-dashed border-white/20 rounded-xl p-3 flex flex-col items-center justify-center gap-2"
          >
            {file ? (
              <>
                <FileIcon name={file.name} />
                <div className="flex items-center gap-2">
                  <span className="text-xs text-white/80 font-mono truncate max-w-[160px]">
                    {file.name}
                  </span>
                  <FileBadge name={file.name} />
                </div>
              </>
            ) : (
              <>
                <span className="text-xs text-white/50 font-medium">Click to select a file</span>
                <div className="flex gap-1.5">
                  {["PDF", "TXT", "MD"].map((t) => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/30 font-semibold">
                      {t}
                    </span>
                  ))}
                </div>
              </>
            )}
          </label>
        </div>

        <button
          onClick={handleUploadClick}
          disabled={!file || isUploading}
          className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-white/5 disabled:text-white/30 text-white text-sm font-medium rounded-xl transition-colors flex items-center justify-center gap-2"
        >
          {isUploading ? (
            <><Loader2 size={16} className="animate-spin" /> Uploading...</>
          ) : (
            <><Lock size={14} /> Upload Document</>
          )}
        </button>

        {statusMessage && (
          <div
            className={`mt-3 p-3 rounded-xl text-xs flex items-start gap-2 ${
              statusMessage.type === "success"
                ? "bg-green-500/10 text-green-400 border border-green-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}
          >
            {statusMessage.type === "success" ? (
              <CheckCircle size={14} className="shrink-0 mt-0.5" />
            ) : (
              <XCircle size={14} className="shrink-0 mt-0.5" />
            )}
            <span>{statusMessage.text}</span>
          </div>
        )}
      </div>
    </>
  );
}
