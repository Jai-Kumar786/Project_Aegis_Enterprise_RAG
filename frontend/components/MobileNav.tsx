"use client";

import { useState, useEffect } from "react";
import { Menu, X } from "lucide-react";
import { FileUpload } from "@/components/FileUpload";
import { PolicyManager } from "@/components/PolicyManager";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  // Close drawer on route change / resize to desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) setOpen(false);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Prevent body scroll when drawer is open
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  return (
    <>
      {/* ── Top bar (mobile only) ───────────────────────────── */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 py-3 border-b border-white/5"
        style={{ background: "hsl(220 20% 5% / 0.95)", backdropFilter: "blur(12px)" }}
      >
        {/* Logo + title */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center shadow-md shadow-indigo-500/30">
            <span className="text-white font-bold text-sm tracking-tighter">A</span>
          </div>
          <div>
            <p className="text-white font-semibold text-sm leading-tight">Project Aegis</p>
            <p className="text-white/30 text-[10px] uppercase tracking-widest">Enterprise RAG</p>
          </div>
        </div>

        {/* Hamburger */}
        <button
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
          className="w-9 h-9 rounded-xl border border-white/10 flex items-center justify-center text-white/60 hover:text-white hover:border-white/20 transition-all"
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </header>

      {/* ── Backdrop ────────────────────────────────────────── */}
      {open && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/60 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Slide-out drawer ────────────────────────────────── */}
      <div
        className={`md:hidden fixed top-0 left-0 h-full w-72 z-40 flex flex-col py-8 items-center border-r border-white/5 transition-transform duration-300 ease-in-out ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ background: "hsl(220 20% 5%)" }}
      >
        {/* Close button */}
        <button
          onClick={() => setOpen(false)}
          className="absolute top-4 right-4 text-white/30 hover:text-white/70 transition-colors"
        >
          <X size={18} />
        </button>

        {/* Branding */}
        <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 mb-4">
          <span className="text-white font-bold text-xl tracking-tighter">A</span>
        </div>
        <h2 className="text-lg font-semibold tracking-wide text-white/90">Project Aegis</h2>
        <p className="text-xs text-white/40 mt-1 uppercase tracking-widest font-medium">Enterprise RAG</p>

        {/* Tools */}
        <div className="mt-10 px-4 w-full flex flex-col gap-4 overflow-y-auto">
          <FileUpload />
          <PolicyManager />
        </div>
      </div>
    </>
  );
}
