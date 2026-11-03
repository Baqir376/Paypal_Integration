"use client";

/**
 * The wordmark that closes the site, in the landing page's own cream and bark gold.
 * The letters rise in once as it scrolls into view, and that is all it does.
 *
 * Decoration, so it is hidden from screen readers, and under reduced motion it is
 * simply the finished word.
 */

import { motion, useReducedMotion } from "framer-motion";

const LETTERS = "SALIX".split("");

export function FooterWord() {
  const reduced = useReducedMotion();

  return (
    <motion.p
      className="foot-word"
      aria-hidden="true"
      initial={reduced ? "shown" : "hidden"}
      whileInView="shown"
      viewport={{ once: true, amount: 0.25 }}
      transition={{ staggerChildren: 0.07 }}
    >
      {LETTERS.map((letter, index) => (
        <motion.span
          key={index}
          className="foot-word-letter"
          variants={{
            hidden: { y: "45%", opacity: 0 },
            shown: { y: 0, opacity: 1 },
          }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        >
          {letter}
        </motion.span>
      ))}
    </motion.p>
  );
}
