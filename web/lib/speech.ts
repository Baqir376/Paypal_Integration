"use client";

/**
 * Saying something out loud.
 *
 * Two routes, tried in order, and the caller is told which one was used:
 *
 *   1. The neural voice from /speech/tts. Always a woman, always the right
 *      accent for the language, and identical on every machine.
 *   2. A local voice installed on this machine — only if the network one is
 *      unreachable, so a session degrades to some speech rather than none.
 *
 * The order used to be the other way round, on the reasoning that a local
 * voice is instant and costs no round trip. That was wrong for this product:
 * the buyer is a woman, and the default English voice on Windows is Microsoft
 * David, who is not. The Dojo announced "read aloud by Microsoft David" and a
 * male buyer answered every English session, however carefully the neural
 * voices had been chosen.
 *
 * Consistency is the point. One rep hearing Neerja and another hearing
 * whatever their laptop happens to have installed is not a product, and the
 * network route is cached for a day per line, so the cost is one round trip
 * the first time a sentence is ever spoken.
 */

import { pickVoice, type SpeechLang } from "./lang";

export type SpokenBy =
  | { via: "local"; voice: string; lang: string }
  | { via: "network"; lang: string }
  | { via: "none"; reason: string };

let currentAudio: HTMLAudioElement | null = null;

/** Stop whatever is speaking, on either route. */
export function stopSpeaking() {
  if (typeof window === "undefined") return;
  window.speechSynthesis?.cancel();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
}

/**
 * Speak `text`, and report how.
 *
 * Resolves as soon as playback has *started* rather than finished: the caller
 * wants to update a readout, not to block a turn on the length of a sentence.
 */
export async function speak(
  text: string,
  lang: SpeechLang,
  voices: SpeechSynthesisVoice[],
): Promise<SpokenBy> {
  if (typeof window === "undefined") return { via: "none", reason: "server" };

  const line = text.trim();
  if (!line) return { via: "none", reason: "nothing to say" };

  stopSpeaking();

  /* --- 1. the neural voice, which is the intended one --------------- */
  try {
    const src = `/speech/tts?lang=${encodeURIComponent(lang.voice)}&text=${encodeURIComponent(
      line.slice(0, 1200),
    )}`;

    const audio = new Audio(src);
    audio.preload = "auto";
    currentAudio = audio;

    await new Promise<void>((resolve, reject) => {
      // `canplay` rather than `loadeddata`: the route synthesises chunk by
      // chunk upstream, so the first byte can be several seconds behind the
      // request on a long line.
      const ok = () => {
        cleanup();
        resolve();
      };
      const fail = () => {
        cleanup();
        reject(new Error("no audio"));
      };
      const cleanup = () => {
        audio.removeEventListener("canplay", ok);
        audio.removeEventListener("error", fail);
        clearTimeout(timer);
      };
      const timer = setTimeout(fail, 15000);
      audio.addEventListener("canplay", ok);
      audio.addEventListener("error", fail);
    });

    await audio.play();
    return { via: "network", lang: lang.tag };
  } catch {
    currentAudio = null;

    /* --- 2. whatever this machine has, rather than silence ---------- */
    const local = pickVoice(lang, voices);
    if (local && window.speechSynthesis) {
      const utterance = new SpeechSynthesisUtterance(line);
      utterance.voice = local;
      utterance.lang = local.lang;
      utterance.rate = 1.02;
      utterance.pitch = 0.96;
      window.speechSynthesis.speak(utterance);
      return { via: "local", voice: local.name, lang: local.lang };
    }

    return {
      via: "none",
      reason: `the neural voice is unreachable and this machine has no ${lang.label} voice`,
    };
  }
}
