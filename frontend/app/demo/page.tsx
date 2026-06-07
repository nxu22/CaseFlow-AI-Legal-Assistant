"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Zap, Scale } from "lucide-react";
import { demoChat } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCallsMade?: number;
}

const SUGGESTED = [
  "Show me all open cases",
  "Find cases for Maria Tremblay",
  "What does HTA s.95(1) cover?",
  "List in-progress cases",
  "Show me the most recent speeding case",
];

export default function DemoPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hi! I'm the CaseFlow demo assistant. I can search Manitoba traffic defense cases, look up HTA sections, and show case details. Try one of the suggestions below or ask me anything about the demo data.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setLoading(true);
    try {
      const data = await demoChat(msg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, toolCallsMade: data.tool_calls_made },
      ]);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 429) {
        setError("Rate limit reached — max 10 requests per hour. Try again later.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Scale className="h-6 w-6 text-blue-400" />
          <span className="font-semibold text-white text-lg">CaseFlow MB</span>
          <span className="text-xs bg-blue-500/20 text-blue-300 border border-blue-500/30 rounded-full px-2 py-0.5">
            Live Demo
          </span>
        </div>
        <a
          href="/login"
          className="text-sm text-slate-400 hover:text-white transition-colors"
        >
          Staff login →
        </a>
      </header>

      {/* Hero */}
      <div className="text-center px-6 pt-10 pb-6">
        <h1 className="text-2xl font-bold text-white mb-2">
          AI-Powered Case Assistant
        </h1>
        <p className="text-slate-400 text-sm max-w-md mx-auto">
          Ask about Manitoba HTA cases in plain language. The AI queries the demo
          database in real time using MCP tools.
        </p>
      </div>

      {/* Chat area */}
      <div className="flex-1 max-w-2xl w-full mx-auto px-4 pb-4 flex flex-col">
        <div className="flex-1 space-y-4 mb-4 overflow-y-auto max-h-[50vh] pr-1">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {m.role === "assistant" && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
                  <Bot className="h-4 w-4 text-white" />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-blue-600 text-white rounded-br-sm"
                    : "bg-slate-800 text-slate-100 rounded-bl-sm"
                }`}
              >
                {m.content}
                {m.toolCallsMade !== undefined && m.toolCallsMade > 0 && (
                  <div className="mt-2 flex items-center gap-1 text-xs text-slate-400">
                    <Zap className="h-3 w-3" />
                    {m.toolCallsMade} tool call{m.toolCallsMade > 1 ? "s" : ""}
                  </div>
                )}
              </div>
              {m.role === "user" && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
                  <User className="h-4 w-4 text-slate-300" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
                <Bot className="h-4 w-4 text-white" />
              </div>
              <div className="bg-slate-800 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          )}

          {error && (
            <p className="text-center text-red-400 text-sm">{error}</p>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Suggested questions */}
        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 mb-3 justify-center">
            {SUGGESTED.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-full px-3 py-1.5 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <form
          onSubmit={(e) => { e.preventDefault(); send(input); }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about cases, clients, or HTA sections…"
            maxLength={500}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-xl px-4 py-3 transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>

        <p className="text-center text-xs text-slate-600 mt-3">
          Demo data only · 10 requests/hour · No real client data
        </p>
      </div>
    </div>
  );
}
