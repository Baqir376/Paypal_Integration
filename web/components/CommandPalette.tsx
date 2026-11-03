"use client";

/**
 * ⌘K.
 *
 * Two things in one surface: quick navigation, and semantic search across
 * every indexed conversational moment. The second is the interesting half --
 * typing "how did anyone handle a pricing objection" runs the same retrieval
 * the Coach uses and shows the passages that come back.
 *
 * Search is debounced and every in-flight request carries a sequence number,
 * so a slow response for an old query can never overwrite a fast one for the
 * current query.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { lockPageScroll } from "@/lib/motion";
import { AUTO_DIR, isRtl } from "@/lib/lang";
import { clock } from "@/lib/format";
import type { SearchHit } from "@/lib/types";

import { IconArrow, IconSearch } from "./icons";

const DESTINATIONS = [
  { label: "Command centre", href: "/console", hint: "Team overview" },
  { label: "Calls", href: "/calls", hint: "Every analysed conversation" },
  { label: "Team", href: "/team", hint: "Add, edit or remove salespeople" },
  { label: "Playbook", href: "/playbook", hint: "The winning DNA" },
  { label: "Deals at risk", href: "/deals", hint: "Trajectory and risk radar" },
  { label: "The Dojo", href: "/dojo", hint: "Practise against a real buyer" },
  { label: "Cycle report", href: "/report", hint: "End-of-cycle analysis" },
  { label: "Analyse a call", href: "/upload", hint: "Upload a recording" },
  { label: "Credits", href: "/billing", hint: "Balance and buying more" },
];

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const sequence = useRef(0);

  const destinations = DESTINATIONS.filter((d) =>
    d.label.toLowerCase().includes(query.toLowerCase()),
  );
  const rows = [...destinations, ...hits];

  useEffect(() => {
    if (open) {
      setQuery("");
      setHits([]);
      setCursor(0);
      // Focus after the frame so the field is actually mounted.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim() || query.trim().length < 3) {
      setHits([]);
      return;
    }
    const id = ++sequence.current;
    setSearching(true);
    const timer = setTimeout(() => {
      api
        .search(query, { k: 6 })
        .then((results) => {
          if (id !== sequence.current) return;
          setSearchFailed(false);
          setHits(results);
        })
        .catch(() => {
          if (id !== sequence.current) return;
          // Not the same as finding nothing, and must not look like it.
          setSearchFailed(true);
          setHits([]);
        })
        .finally(() => {
          if (id === sequence.current) setSearching(false);
        });
    }, 220);
    return () => clearTimeout(timer);
  }, [query]);

  const choose = useCallback(
    (index: number) => {
      const row = rows[index];
      if (!row) return;
      onClose();
      if ("href" in row) {
        router.push(row.href);
      } else {
        router.push(`/calls/${row.moment.call_id}`);
      }
    },
    [rows, router, onClose],
  );

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setCursor((c) => Math.min(rows.length - 1, c + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setCursor((c) => Math.max(0, c - 1));
      } else if (event.key === "Enter") {
        event.preventDefault();
        choose(cursor);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, rows.length, cursor, choose, onClose]);

  useEffect(() => {
    if (!open) return;
    lockPageScroll(true);
    return () => lockPageScroll(false);
  }, [open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Search Salix"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        background: "color-mix(in oklab, var(--paper) 55%, transparent)",
        backdropFilter: "blur(5px)",
        display: "grid",
        placeItems: "start center",
        paddingTop: "13vh",
      }}
    >
      <div
        className="panel rise"
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "min(620px, calc(100vw - 32px))",
          boxShadow: "var(--shadow-3)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "13px 15px",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <IconSearch size={15} style={{ color: "var(--ink-3)" }} />
          <input
            ref={inputRef}
            // A rep searching for how a colleague handled a price objection may
            // well type it in Urdu. The field follows the query rather than the
            // page.
            dir={AUTO_DIR}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            placeholder="Go to a page, or ask how the team handles an objection"
            style={{
              flex: 1,
              border: "none",
              outline: "none",
              background: "transparent",
              color: "var(--ink)",
              fontSize: 14.5,
              fontFamily: "inherit",
            }}
          />
          {searching && <span className="eyebrow">searching</span>}
        </div>

        <div style={{ maxHeight: "56vh", overflowY: "auto", overscrollBehavior: "contain", padding: 6 }}>
          {rows.length === 0 && (
            <div
              style={{
                padding: "26px 14px",
                textAlign: "center",
                color: "var(--ink-3)",
                fontSize: 13,
              }}
            >
              {query.trim().length < 3
                ? "Keep typing to search the call archive."
                : searching
                  ? "Searching…"
                  : searchFailed
                    ? "Search is unavailable right now. Try again in a moment."
                    : "Nothing matched."}
            </div>
          )}

          {destinations.map((destination, index) => (
            <Row
              key={destination.href}
              active={cursor === index}
              onHover={() => setCursor(index)}
              onClick={() => choose(index)}
            >
              <span style={{ fontWeight: 500 }}>{destination.label}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 12.5 }}>
                {destination.hint}
              </span>
              <IconArrow size={13} style={{ color: "var(--ink-4)" }} />
            </Row>
          ))}

          {hits.length > 0 && (
            <div className="eyebrow" style={{ padding: "12px 12px 6px" }}>
              From the call archive
            </div>
          )}

          {hits.map((hit, index) => {
            const position = destinations.length + index;
            return (
              <Row
                key={hit.moment.id}
                active={cursor === position}
                onHover={() => setCursor(position)}
                onClick={() => choose(position)}
              >
                <span
                  style={{
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    fontSize: 13,
                  }}
                >
                  <span
                    dir={AUTO_DIR}
                    className={isRtl(hit.moment.text) ? "urdu-prose" : undefined}
                  >
                    {hit.moment.text}
                  </span>
                </span>
                <span className={`chip ${hit.moment.outcome === "won" ? "chip-sage" : "chip-neutral"}`}>
                  {hit.moment.kind.replace("_", " ")}
                </span>
                <span className="num" style={{ fontSize: 11, color: "var(--ink-4)" }}>
                  {hit.score.toFixed(2)}
                </span>
              </Row>
            );
          })}
        </div>

        <div
          style={{
            display: "flex",
            gap: 14,
            padding: "8px 15px",
            borderTop: "1px solid var(--rule)",
            background: "var(--paper)",
          }}
        >
          <Hint keys="↑↓" label="navigate" />
          <Hint keys="↵" label="open" />
          <Hint keys="esc" label="close" />
        </div>
      </div>
    </div>
  );
}

function Row({
  active,
  onHover,
  onClick,
  children,
}: {
  active: boolean;
  onHover: () => void;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onMouseEnter={onHover}
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        padding: "9px 11px",
        borderRadius: "var(--r)",
        border: "none",
        background: active ? "var(--paper-3)" : "transparent",
        color: "var(--ink)",
        textAlign: "left",
        cursor: "pointer",
        fontFamily: "inherit",
      }}
    >
      {children}
    </button>
  );
}

function Hint({ keys, label }: { keys: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <kbd
        className="num"
        style={{
          fontSize: 10,
          border: "1px solid var(--rule)",
          borderRadius: 3,
          padding: "0 4px",
          color: "var(--ink-3)",
        }}
      >
        {keys}
      </kbd>
      <span className="eyebrow">{label}</span>
    </span>
  );
}
