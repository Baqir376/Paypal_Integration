"use client";

/**
 * The chapter run — a horizontally expanding accordion.
 *
 * Columns rest at `flex: 1` and the one under the pointer goes to `flex: 3.5`,
 * revealing a full-bleed plate and a spec table while the rest compress back
 * to a numeric spine and a vertical title. The transition is on `flex` with
 * the house curve, which is what makes it read as a mechanism opening rather
 * than as panels swapping.
 *
 * Three accessibility decisions, none of them optional:
 *
 *   1. Focus does exactly what hover does. Content behind a pointer gesture is
 *      content a keyboard user does not have.
 *   2. Each column is a real button controlling a real region, so the open
 *      state is announced rather than merely visible.
 *   3. Below 900px the whole thing stacks with every panel open — the same
 *      content, without a gesture that does not exist on a touchscreen.
 */

import { useState } from "react";

export type Chapter = {
  index: string;
  title: string;
  spine: string;
  copy: string;
  plate: string;
  specs: { label: string; value: string }[];
};

export function SvcCols({ chapters }: { chapters: Chapter[] }) {
  const [open, setOpen] = useState(0);

  return (
    <div className="svc-cols">
      {chapters.map((chapter, index) => {
        const isOpen = index === open;
        return (
          <article
            key={chapter.index}
            className="svc-col"
            data-open={isOpen}
            data-cursor="card"
            onMouseEnter={() => setOpen(index)}
            onFocusCapture={() => setOpen(index)}
          >
            <div
              className="svc-col-plate"
              style={{ backgroundImage: `var(${chapter.plate})` }}
              aria-hidden="true"
            />

            <div className="svc-col-inner">
              <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                <span className="svc-col-index">{chapter.index}</span>
                <span
                  className="sx-tag"
                  style={{
                    marginLeft: "auto",
                    opacity: isOpen ? 1 : 0,
                    transition: "opacity 420ms var(--ease-luxury)",
                  }}
                >
                  {chapter.spine}
                </span>
              </div>

              {/* The button is the whole column's control surface; the spine
                  is its label while closed. */}
              <button
                className="svc-col-spine"
                type="button"
                aria-expanded={isOpen}
                aria-controls={`chapter-${chapter.index}`}
                onClick={() => setOpen(index)}
                style={{
                  background: "none",
                  border: 0,
                  padding: 0,
                  cursor: "pointer",
                  font: "inherit",
                  color: "inherit",
                  letterSpacing: "inherit",
                }}
              >
                {chapter.spine}
              </button>

              <div className="svc-col-body" id={`chapter-${chapter.index}`}>
                <h3 className="svc-col-title">{chapter.title}</h3>
                <p className="svc-col-copy">{chapter.copy}</p>

                <dl className="svc-spec">
                  {chapter.specs.map((spec) => (
                    <div className="svc-spec-row" key={spec.label}>
                      <dt>{spec.label}</dt>
                      <dd>{spec.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
