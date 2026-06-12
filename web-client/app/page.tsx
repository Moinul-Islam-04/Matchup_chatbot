"use client";

import { useRef, useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";

type Msg = { role: "user" | "assistant"; content: string };

const TOOL_LABELS: Record<string, string> = {
  get_champion_info: "Looking up champion data",
  get_item_info: "Looking up item data",
  get_rune_info: "Looking up rune data",
  get_live_match_context: "Checking the live match",
};

export default function Home() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, toolStatus]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

    const history: Msg[] = [...messages, { role: "user", content: text }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);
    setError(null);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `Request failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse complete SSE events (separated by a blank line).
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const evt of events) {
          const evMatch = evt.match(/^event: (.+)$/m);
          const dataMatch = evt.match(/^data: (.+)$/m);
          if (!evMatch || !dataMatch) continue;
          const type = evMatch[1];
          const data = JSON.parse(dataMatch[1]);

          if (type === "text") {
            setToolStatus(null);
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = {
                role: "assistant",
                content: next[next.length - 1].content + data.delta,
              };
              return next;
            });
          } else if (type === "tool") {
            setToolStatus(TOOL_LABELS[data.name] ?? `Running ${data.name}`);
          } else if (type === "error") {
            setError(data.message);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setToolStatus(null);
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>
          <span className="gold">LoL</span> Companion
        </h1>
        <p>Context-aware advice for live games — powered by Claude + the Riot API</p>
      </header>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty">
            Ask me something like:
            <br />
            <code>I&apos;m Graves vs Diana jungle — when does she spike and what do I build?</code>
            <br />
            <br />
            or <code>Who is Revenge#Fake up against right now?</code>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "assistant" ? (
            <div key={i} className="bubble assistant markdown">
              {m.content ? (
                <ReactMarkdown>{m.content}</ReactMarkdown>
              ) : busy && i === messages.length - 1 ? (
                "…"
              ) : null}
            </div>
          ) : (
            <div key={i} className="bubble user">
              {m.content}
            </div>
          ),
        )}

        {toolStatus && (
          <div className="tool">
            <span className="dot" /> {toolStatus}…
          </div>
        )}
        {error && <div className="error">⚠ {error}</div>}
      </div>

      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a matchup, powerspike, build, or live game…"
          rows={1}
          disabled={busy}
        />
        <button onClick={send} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
