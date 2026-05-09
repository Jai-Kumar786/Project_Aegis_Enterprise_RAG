import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { FileUpload } from "@/components/FileUpload";
import { PolicyManager } from "@/components/PolicyManager";
import { MobileNav } from "@/components/MobileNav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Project Aegis | Enterprise RAG",
  description: "Advanced RAG system for corporate policy retrieval.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        {/* Mobile top bar + slide-out drawer (hidden on md+) */}
        <MobileNav />

        <div className="flex h-screen overflow-hidden">
          {/* Desktop Sidebar (hidden below md) */}
          <aside className="w-64 glass-panel border-r border-white/5 flex-col items-center py-8 hidden md:flex z-10">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 mb-4">
              <span className="text-white font-bold text-xl tracking-tighter">A</span>
            </div>
            <h1 className="text-lg font-semibold tracking-wide text-white/90">Project Aegis</h1>
            <p className="text-xs text-white/40 mt-1 uppercase tracking-widest font-medium">Enterprise RAG</p>
            <div className="mt-12 px-4 w-full flex flex-col gap-4 overflow-y-auto">
              <FileUpload />
              <PolicyManager />
            </div>
          </aside>

          {/* Main Content — pt-14 on mobile to clear the fixed header */}
          <main className="flex-1 relative flex flex-col pt-14 md:pt-0">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
