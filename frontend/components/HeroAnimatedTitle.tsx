"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";

const ROTATING_WORDS = ["codebase.", "architecture.", "repositories.", "security."];

export default function HeroAnimatedTitle() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((prev) => (prev + 1) % ROTATING_WORDS.length);
    }, 3200);
    return () => clearInterval(timer);
  }, []);

  const words = "Documentation that keeps up with your".split(" ");

  return (
    <h1 className="max-w-5xl text-4xl font-bold leading-[1.2] tracking-tight text-white sm:text-5xl lg:text-6xl flex flex-wrap items-center gap-x-3 sm:gap-x-4 gap-y-2 py-1">
      {/* Staggered word-by-word entrance for main title */}
      {words.map((word, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            delay: i * 0.05,
            ease: [0.22, 1, 0.36, 1],
          }}
          className="inline-block"
        >
          {word}
        </motion.span>
      ))}

      {/* Dynamic rotating word — rendered cleanly in-flow to prevent any text clipping */}
      <span className="relative inline-block py-1">
        <AnimatePresence mode="wait">
          <motion.span
            key={ROTATING_WORDS[index]}
            initial={{ y: 24, opacity: 0, filter: "blur(4px)" }}
            animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
            exit={{ y: -24, opacity: 0, filter: "blur(4px)" }}
            transition={{
              duration: 0.45,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="inline-block bg-gradient-to-r from-teal-light via-teal to-accent-cta bg-clip-text text-transparent font-extrabold pb-1"
          >
            {ROTATING_WORDS[index]}
          </motion.span>
        </AnimatePresence>
      </span>
    </h1>
  );
}
