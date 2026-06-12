"use client";

import { useRef, useState, useEffect } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { loadIconMaps, lookupIcon, type IconMaps } from "@/lib/ddragon";
import { MatchCard, type MatchData } from "@/components/MatchCard";

type Msg = { role: "user" | "assistant"; content: string; match?: MatchData };

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
  const [icons, setIcons] = useState<IconMaps | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, toolStatus]);

  // Load champion/item/rune icon maps once from Data Dragon.
  useEffect(() => {
    loadIconMaps().then(setIcons).catch(() => {});
  }, []);

  // Render a small icon before any bolded champion/item/rune name.
  const mdComponents: Components = {
    strong({ children }) {
      const text =
        typeof children === "string"
          ? children
          : Array.isArray(children) && children.length === 1 && typeof children[0] === "string"
            ? (children[0] as string)
            : null;
      const url = text ? lookupIcon(icons, text) : null;
      if (url) {
        return (
          <strong className="named">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="inline-icon" src={url} alt="" />
            {children}
          </strong>
        );
      }
      return <strong>{children}</strong>;
    },
  };

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
              const last = next[next.length - 1];
              next[next.length - 1] = {
                ...last,
                role: "assistant",
                content: last.content + data.delta,
              };
              return next;
            });
          } else if (type === "tool") {
            setToolStatus(TOOL_LABELS[data.name] ?? `Running ${data.name}`);
          } else if (type === "match") {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, match: data as MatchData };
              }
              return next;
            });
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
            <div key={i} className="assistant-msg">
              {m.match && <MatchCard match={m.match} icons={icons} />}
              {(m.content || (busy && i === messages.length - 1 && !m.match)) && (
                <div className="bubble assistant markdown">
                  {m.content ? (
                    <ReactMarkdown components={mdComponents}>{m.content}</ReactMarkdown>
                  ) : (
                    "…"
                  )}
                </div>
              )}
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
