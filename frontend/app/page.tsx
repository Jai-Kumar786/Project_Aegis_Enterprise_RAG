"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Bot, User, Loader2, Sparkles, FileSearch, Lightbulb } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Message = {
  id: string;
  role: "user" | "ai";
  content: string;
  citations?: string[];
  chunksUsed?: number;
};

const LOADING_PHRASES = [
  "Analyzing your query...",
  "Searching the enterprise policy database...",
  "Running Cohere ReRank...",
  "Synthesizing answer with DeepSeek...",
];

const SUGGESTED_PROMPTS = [
  "What is the remote work policy?",
  "How do I expense a client dinner?",
  "What are the security guidelines for personal devices?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingPhraseIndex, setLoadingPhraseIndex] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, loadingPhraseIndex]);

  // Cycle loading phrases
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isLoading) {
      interval = setInterval(() => {
        setLoadingPhraseIndex((prev) => (prev + 1) % LOADING_PHRASES.length);
      }, 2500);
    } else {
      setLoadingPhraseIndex(0);
    }
    return () => clearInterval(interval);
  }, [isLoading]);

  const submitQuery = async (query: string) => {
    if (!query.trim() || isLoading) return;

    // Snapshot history BEFORE adding the new user message.
    // Map "ai" → "assistant" to match the backend's expected role names.
    const historySnapshot = messages
      .filter((m) => m.content.trim()) // skip empty streaming placeholders
      .map((m) => ({
        role: m.role === "ai" ? "assistant" : "user",
        content: m.content,
      }));

    const userMessage: Message = { id: Date.now().toString(), role: "user", content: query };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    const aiMessageId = (Date.now() + 1).toString();
    setMessages((prev) => [...prev, { id: aiMessageId, role: "ai", content: "", citations: [] }]);

    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query, history: historySnapshot }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      setIsLoading(false); // Stop loading indicator, start streaming

      let done = false;
      let buffer = "";

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          
          // Split by newline, but keep the last incomplete chunk in the buffer
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // The last element is either an incomplete line or empty string

          for (const line of lines) {
            if (!line.trim()) continue;
            
            const cleanLine = line.startsWith('data:') ? line.slice(5).trim() : line;
            try {
              const data = JSON.parse(cleanLine);
              
              setMessages((prev) => 
                prev.map((msg) => {
                  if (msg.id !== aiMessageId) return msg;

                  if (data.type === "metadata") {
                    return { ...msg, citations: data.citations, chunksUsed: data.chunks_used };
                  }
                  if (data.type === "chunk") {
                    return { ...msg, content: msg.content + data.text };
                  }
                  return msg;
                })
              );
            } catch (e) {
              console.warn("Could not parse stream line:", line);
            }
          }
        }
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "ai", content: "Error: Could not reach the Aegis backend. Ensure uvicorn is running." },
      ]);
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuery(input);
    }
  };

  return (
    <div className="flex flex-col h-full relative">
      {/* Header (Mobile only) */}
      <header className="md:hidden glass border-b p-4 flex items-center justify-center sticky top-0 z-20">
        <h1 className="font-semibold text-white/90">Project Aegis</h1>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8 scroll-smooth" ref={scrollRef}>
        <div className="max-w-4xl mx-auto pb-32">
          
          {/* Empty State */}
          {messages.length === 0 && (
            <motion.div 
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} 
              className="flex flex-col items-center justify-center mt-20 text-center"
            >
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 flex items-center justify-center mb-6 shadow-[0_0_40px_rgba(99,102,241,0.2)]">
                <Sparkles size={32} className="text-indigo-400" />
              </div>
              <h2 className="text-3xl font-bold text-white mb-3">How can Aegis help?</h2>
              <p className="text-white/50 max-w-md mb-10">
                Ask any question regarding our corporate policies. DeepSeek will retrieve the exact clauses and synthesize an answer.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-3xl">
                {SUGGESTED_PROMPTS.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => submitQuery(prompt)}
                    className="glass hover:bg-white/5 text-left p-4 rounded-xl border border-white/10 transition-all hover:border-indigo-500/50 group flex flex-col gap-3"
                  >
                    <Lightbulb size={18} className="text-purple-400 group-hover:text-indigo-400 transition-colors" />
                    <span className="text-sm text-white/80 font-medium leading-relaxed">{prompt}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          <AnimatePresence initial={false}>
            {messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`flex gap-4 mb-6 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
              >
                {/* Avatar */}
                <div
                  className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center shadow-lg ${
                    msg.role === "user"
                      ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30"
                      : "glass-panel text-purple-400"
                  }`}
                >
                  {msg.role === "user" ? <User size={20} /> : <Bot size={20} />}
                </div>

                {/* Bubble */}
                <div
                  className={`max-w-[85%] rounded-2xl p-5 ${
                    msg.role === "user"
                      ? "bg-indigo-600/90 text-white shadow-[0_0_20px_rgba(79,70,229,0.15)] rounded-tr-sm"
                      : "glass text-white/80 rounded-tl-sm border border-white/10 prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-black/50 prose-pre:border-white/10 prose-td:border-white/10 prose-th:border-white/10"
                  }`}
                >
                  {msg.role === "user" ? (
                    <p className="whitespace-pre-wrap text-[15px]">{msg.content}</p>
                  ) : (
                    <>
                      {msg.content === "" && !isLoading && <span className="animate-pulse">...</span>}
                      <ReactMarkdown 
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({node, ...props}) => <p className="mb-4 leading-relaxed text-[15px]" {...props} />,
                          ul: ({node, ...props}) => <ul className="list-disc pl-6 mb-4 space-y-2" {...props} />,
                          ol: ({node, ...props}) => <ol className="list-decimal pl-6 mb-4 space-y-2" {...props} />,
                          li: ({node, ...props}) => <li className="marker:text-white/40" {...props} />,
                          strong: ({node, ...props}) => <strong className="font-semibold text-white" {...props} />,
                          h3: ({node, ...props}) => <h3 className="text-lg font-semibold text-white mt-6 mb-3" {...props} />,
                          h4: ({node, ...props}) => <h4 className="text-base font-semibold text-white mt-4 mb-2" {...props} />,
                          blockquote: ({node, ...props}) => <blockquote className="border-l-2 border-indigo-500/50 pl-4 italic text-white/70 mb-4" {...props} />
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </>
                  )}
                  
                  {/* Citations Tooltips */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-5 pt-4 border-t border-white/10 flex flex-wrap gap-2 items-center">
                      <FileSearch size={14} className="text-white/40 mr-1" />
                      <span className="text-xs text-white/40 uppercase tracking-wider font-semibold mr-1">Sources:</span>
                      {msg.citations.map((doc, idx) => (
                        <div key={idx} className="relative group">
                          <span className="text-xs bg-black/40 border border-white/10 px-2 py-1 rounded-md text-purple-300 font-medium cursor-help hover:bg-white/10 transition-colors">
                            [{idx + 1}]
                          </span>
                          {/* Tooltip */}
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-max max-w-[200px] bg-zinc-800 text-white/90 text-[11px] font-mono px-3 py-2 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-xl border border-white/10 z-50">
                            {doc}
                          </div>
                        </div>
                      ))}
                      {msg.chunksUsed && (
                        <span className="text-[10px] text-white/30 ml-auto flex items-center">
                          Derived from {msg.chunksUsed} chunks
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Loading Indicator */}
          {isLoading && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4">
              <div className="w-10 h-10 rounded-full glass-panel flex items-center justify-center text-purple-400">
                <Loader2 size={20} className="animate-spin" />
              </div>
              <div className="glass rounded-2xl rounded-tl-sm px-5 py-4 flex items-center w-fit">
                <span className="text-[15px] font-medium text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400 animate-pulse">
                  {LOADING_PHRASES[loadingPhraseIndex]}
                </span>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Input Area */}
      <div className="absolute bottom-0 left-0 right-0 p-4 md:p-8 bg-gradient-to-t from-[hsl(var(--background))] via-[hsl(var(--background))] to-transparent z-10 pointer-events-none">
        <div className="max-w-4xl mx-auto pointer-events-auto">
          <form
            onSubmit={(e) => { e.preventDefault(); submitQuery(input); }}
            className="glass rounded-2xl flex items-end p-2 focus-within:ring-2 focus-within:ring-indigo-500/50 transition-all shadow-[0_0_40px_rgba(0,0,0,0.5)]"
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about corporate policies... (Shift+Enter for new line)"
              className="flex-1 bg-transparent border-none outline-none px-4 py-3 min-h-[50px] max-h-[200px] resize-none text-white/90 placeholder:text-white/30 text-[15px]"
              rows={1}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="p-3 mb-1 mr-1 bg-indigo-600 hover:bg-indigo-500 disabled:bg-white/5 disabled:text-white/20 text-white rounded-xl transition-colors flex-shrink-0"
            >
              <Send size={18} />
            </button>
          </form>
          <p className="text-center text-[11px] text-white/30 mt-3 font-medium tracking-wide">
            Project Aegis can make mistakes. Verify important policy details with HR.
          </p>
        </div>
      </div>
    </div>
  );
}
