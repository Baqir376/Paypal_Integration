/**
 * Language handling.
 *
 * Salix is used by sales floors in Pakistan, where a single call routinely
 * moves between Urdu, Roman Urdu and English inside one sentence. Three
 * consequences run through the app:
 *
 *   1. Text direction is decided per string, not per document. A rep's turn
 *      may be Urdu while the buyer's is English, and both sit in the same
 *      column. `dir="auto"` asks the browser to look at the first strong
 *      character, which is exactly the right rule and costs nothing.
 *   2. Dictation has to be told what it is listening for. The Web Speech API
 *      defaults to the page language and will transcribe Urdu speech as
 *      nonsense English if you let it.
 *   3. Speech synthesis has to be told what it is reading. An unset
 *      `utterance.lang` gets the system default voice, which will read Urdu
 *      script as if it were English — or silently skip it.
 */

/** Arabic, Arabic Supplement, Extended-A, and the Arabic Presentation Forms. */
const RTL_SCRIPT =
  /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;

/** True when the string contains Urdu / Arabic script at all. */
export function hasRtl(text: string | null | undefined): boolean {
  return !!text && RTL_SCRIPT.test(text);
}

/**
 * True when the string is *predominantly* RTL.
 *
 * A single Urdu word inside an English sentence should not flip the paragraph,
 * so this counts rather than merely detects. The threshold is deliberately low
 * — Urdu prose carries a lot of Latin-script product names and numbers.
 */
export function isRtl(text: string | null | undefined): boolean {
  if (!text) return false;
  const rtl = (text.match(new RegExp(RTL_SCRIPT, "g")) ?? []).length;
  if (rtl === 0) return false;
  const latin = (text.match(/[A-Za-z]/g) ?? []).length;
  return rtl >= latin * 0.6;
}

/**
 * The `dir` for a string of unknown origin.
 *
 * Always "auto" rather than a computed "rtl"/"ltr": the browser's bidi
 * algorithm is better at this than we are, and "auto" also gets the trailing
 * punctuation right, which is the thing that looks broken when it is wrong.
 */
export const AUTO_DIR = "auto" as const;

/* --------------------------------------------------------------------------
 * The languages a session can be run in
 * ----------------------------------------------------------------------- */

export type SpeechLang = {
  id: string;
  /** What the control says. */
  label: string;
  /** Shown under the label, in the language itself where that helps. */
  native: string;
  /** BCP-47 tag handed to SpeechRecognition and SpeechSynthesis. */
  tag: string;
  /**
   * What the network voice should be asked for.
   *
   * Deliberately not `tag`. That is chosen for the *recogniser* -- Roman Urdu
   * listens as `en-PK` because Pakistani-accented English is the closest
   * acoustic model -- and asking a synthesiser the same question gets a
   * British voice reading Urdu words it cannot pronounce. Which is what used
   * to happen.
   */
  voice: "en" | "ur-roman";
  /** Fallback tags to try if no installed voice matches `tag`. */
  fallbacks: string[];
  rtl: boolean;
};

/**
 * Two, and only two.
 *
 * This is what a Karachi or Lahore floor actually speaks on a sales call.
 * There is no Urdu-script option: a rep dictating "aap ki price bohat zyada
 * hai" wants those words back in the same letters they said them in, and an
 * Urdu recogniser handed Roman Urdu tries to emit Nastaliq, which is neither
 * what was said nor what they can read back at a glance.
 *
 * So Roman Urdu is mapped to `en-PK`, not `ur-PK`. It is Urdu vocabulary in
 * Latin script, and Pakistani-accented English recognition is by far the
 * closer acoustic match. It also means dictation works in every browser that
 * has speech recognition at all, rather than failing with
 * `language-not-supported` the way `ur-PK` does on most of them.
 *
 * The two entries used to be four -- an Urdu-script option and a second,
 * identically labelled "English". A control offering "English" twice is a
 * control nobody trusts.
 */
export const SPEECH_LANGS: SpeechLang[] = [
  {
    id: "en-PK",
    label: "English",
    native: "Pakistani accent",
    tag: "en-PK",
    voice: "en",
    fallbacks: ["en-IN", "en-GB", "en-US", "en"],
    rtl: false,
  },
  {
    id: "roman",
    label: "Roman Urdu",
    native: "Urdu in Latin script",
    tag: "en-PK",
    voice: "ur-roman",
    fallbacks: ["en-IN", "en-GB", "en-US", "en"],
    rtl: false,
  },
];

/** What the model is told to answer in. Sent with every Dojo turn. */
export function replyLanguage(id: string): "en" | "ur-roman" {
  return id === "roman" ? "ur-roman" : "en";
}

export function langById(id: string): SpeechLang {
  return SPEECH_LANGS.find((l) => l.id === id) ?? SPEECH_LANGS[0];
}

/* --------------------------------------------------------------------------
 * Speech capability
 * ----------------------------------------------------------------------- */

export type SpeechSupport = {
  recognition: boolean;
  synthesis: boolean;
  /** Voices installed for the requested language, best first. */
  voices: SpeechSynthesisVoice[];
};

/**
 * The Web Speech API is not in `lib.dom` because it never reached
 * standardisation, so the shape it is used through is declared here rather
 * than reached for as `any` at each call site.
 */
export type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
};

export function recognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Voices that are women, by name.
 *
 * The Web Speech API exposes no gender field, so this is the only way to ask.
 * A name list is crude and incomplete and still far better than the
 * alternative: `voices.find(...)` returns whatever the platform lists first,
 * and on Windows that is Microsoft David — a man. The buyer is a woman, the
 * network voice is a woman, and a fallback that quietly changes her sex
 * undoes the whole point of choosing carefully.
 */
const FEMALE_VOICE =
  /(zira|hazel|heera|susan|linda|catherine|karen|moira|tessa|fiona|samantha|victoria|allison|ava|serena|neerja|swara|kalpana|uzma|asma|female|woman)/i;

/** Voices that are definitely men, skipped unless nothing else is left. */
const MALE_VOICE = /(david|mark|george|james|richard|ravi|hemant|daniel|alex|fred|tom|oliver|male|man)/i;

/**
 * The best installed voice for a language, walking the fallback chain.
 *
 * Only reached when the neural voice is unreachable — see lib/speech.ts, which
 * uses the network route first precisely so that every machine hears the same
 * person. When it is reached, a woman is preferred at each step of the chain
 * before falling back to anything else.
 *
 * Returns `null` rather than an arbitrary voice when nothing matches at all. A
 * caller that hands Urdu text to an English voice produces noise, and silence
 * with an explanation is better than noise.
 */
export function pickVoice(
  lang: SpeechLang,
  voices: SpeechSynthesisVoice[],
): SpeechSynthesisVoice | null {
  if (!voices.length) return null;

  const norm = (v: SpeechSynthesisVoice) => v.lang.replace("_", "-").toLowerCase();

  /** Women first, then anything not obviously a man, then whatever is left. */
  const best = (candidates: SpeechSynthesisVoice[]) =>
    candidates.find((v) => FEMALE_VOICE.test(v.name)) ??
    candidates.find((v) => !MALE_VOICE.test(v.name)) ??
    candidates[0] ??
    null;

  for (const tag of [lang.tag, ...lang.fallbacks]) {
    const wanted = tag.toLowerCase();
    const exact = best(voices.filter((v) => norm(v) === wanted));
    if (exact) return exact;

    const prefix = wanted.split("-")[0];
    const loose = best(voices.filter((v) => norm(v).startsWith(prefix)));
    if (loose) return loose;
  }
  return null;
}

/**
 * Load the voice list, which most browsers populate asynchronously.
 *
 * Chrome returns an empty array on the first call and fires `voiceschanged`
 * once the list is ready; Safari populates synchronously. Handling only one of
 * those is why voice pickers so often show nothing on first load.
 */
export function loadVoices(onReady: (voices: SpeechSynthesisVoice[]) => void): () => void {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    onReady([]);
    return () => {};
  }

  const read = () => onReady(window.speechSynthesis.getVoices());
  read();
  window.speechSynthesis.addEventListener("voiceschanged", read);
  return () => window.speechSynthesis.removeEventListener("voiceschanged", read);
}
