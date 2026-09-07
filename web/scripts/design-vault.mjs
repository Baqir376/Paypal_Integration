#!/usr/bin/env node
/**
 * The design vault.
 *
 * The art direction is the part of this repository worth stealing, and a
 * public repository hands it over in full. This encrypts the design-bearing
 * files at rest so the repository carries ciphertext, and decrypts them at
 * build time from a key that never leaves the owner's machine.
 *
 * What someone cloning the public repository gets:
 *
 *   - every protected file as an unreadable `.enc` blob;
 *   - a complete, working application that builds, runs and passes its tests;
 *   - a deliberately plain stylesheet in place of the real one.
 *
 * What they do not get is the design. Not the palette, not the easing curves,
 * not the layout system, not the type scale — and nothing an AI can read
 * either, because AES-256-GCM ciphertext is indistinguishable from noise.
 *
 * The honest boundary, stated once: this protects the *repository*. A deployed
 * site still renders the design to whoever visits it, and a screenshot is
 * always enough to approximate a look. This closes the door you asked about —
 * the one marked "pushed to GitHub" — and closes it properly.
 *
 * Usage
 * -----
 *   node scripts/design-vault.mjs lock      encrypt plaintext -> .enc
 *   node scripts/design-vault.mjs unlock    decrypt .enc -> plaintext
 *   node scripts/design-vault.mjs status    what is protected, and its state
 *   node scripts/design-vault.mjs keygen    print a fresh key
 *
 * The key comes from SALIX_DESIGN_KEY, or from web/.design-key (gitignored).
 * With no key, `unlock` writes the plain fallbacks instead of failing, so a
 * clone still builds.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST = path.join(ROOT, "design.manifest.json");
const KEY_FILE = path.join(ROOT, ".design-key");

const ALGORITHM = "aes-256-gcm";
/* Deliberately expensive. The key is a passphrase a person can remember, and
   scrypt is what stops that being brute-forced out of a public repository. */
/* maxmem must be raised explicitly: 128 * N * r is 32MB here, which is exactly
   Node's default ceiling, and scrypt refuses rather than rounding down. */
const SCRYPT = { N: 1 << 15, r: 8, p: 1, keylen: 32, maxmem: 96 * 1024 * 1024 };

/* -------------------------------------------------------------------------
 * Key
 * ---------------------------------------------------------------------- */

function readKey() {
  const fromEnv = process.env.SALIX_DESIGN_KEY?.trim();
  if (fromEnv) return fromEnv;
  if (fs.existsSync(KEY_FILE)) {
    const fromFile = fs.readFileSync(KEY_FILE, "utf8").trim();
    if (fromFile) return fromFile;
  }
  return null;
}

function deriveKey(passphrase, salt) {
  const { keylen, ...params } = SCRYPT;
  return crypto.scryptSync(passphrase, salt, keylen, params);
}

/* -------------------------------------------------------------------------
 * Crypto
 *
 * Every file gets its own random salt and IV, so two files with identical
 * contents encrypt to different blobs and nothing can be inferred by
 * comparing them. GCM's auth tag means a tampered blob fails loudly rather
 * than decrypting to garbage.
 * ---------------------------------------------------------------------- */

function encrypt(plaintext, passphrase) {
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const key = deriveKey(passphrase, salt);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const body = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  // salt | iv | tag | body — a single opaque blob, no readable structure.
  return Buffer.concat([salt, iv, tag, body]).toString("base64");
}

function decrypt(blob, passphrase) {
  const raw = Buffer.from(blob, "base64");
  const salt = raw.subarray(0, 16);
  const iv = raw.subarray(16, 28);
  const tag = raw.subarray(28, 44);
  const body = raw.subarray(44);
  const key = deriveKey(passphrase, salt);
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(body), decipher.final()]).toString("utf8");
}

/* -------------------------------------------------------------------------
 * Manifest
 * ---------------------------------------------------------------------- */

function manifest() {
  if (!fs.existsSync(MANIFEST)) {
    console.error("design.manifest.json is missing.");
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(MANIFEST, "utf8"));
}

const abs = (p) => path.join(ROOT, p);
const encPath = (p) => abs(`${p}.enc`);

/* -------------------------------------------------------------------------
 * Commands
 * ---------------------------------------------------------------------- */

function lock() {
  const key = readKey();
  if (!key) {
    console.error(
      "No key. Set SALIX_DESIGN_KEY or write one to web/.design-key\n" +
        "Generate one with:  node scripts/design-vault.mjs keygen",
    );
    process.exit(1);
  }

  const { protect } = manifest();
  let locked = 0;

  for (const file of protect) {
    const source = abs(file);
    if (!fs.existsSync(source)) {
      console.warn(`  skip    ${file}  (not present)`);
      continue;
    }
    const plaintext = fs.readFileSync(source, "utf8");
    fs.writeFileSync(encPath(file), encrypt(plaintext, key));
    const size = Buffer.byteLength(plaintext);
    console.log(`  locked  ${file}  (${size} bytes -> ciphertext)`);
    locked++;
  }

  console.log(
    `\n${locked} file(s) locked. Commit the .enc files; the plaintext is gitignored.`,
  );
}

/** design/fallbacks/app_system.css for app/system.css. */
function fallbackPath(file, dir) {
  return path.join(ROOT, dir, file.replace(/[\/]/g, "_"));
}

function unlock({ quiet = false } = {}) {
  const key = readKey();
  const { protect, fallbackDir } = manifest();

  if (!key) {
    // A clone with no key must still build. Write the plain stand-ins.
    let stubbed = 0;
    for (const file of protect) {
      const target = abs(file);
      if (fs.existsSync(target) && !fs.existsSync(encPath(file))) {
        // Working copy with no vault yet: leave the author's files alone.
        continue;
      }
      const stub = fallbackPath(file, fallbackDir ?? "design/fallbacks");
      const body = fs.existsSync(stub)
        ? fs.readFileSync(stub, "utf8")
        : `/* Withheld. Build with SALIX_DESIGN_KEY to restore this file. */\n`;
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, body);
      stubbed++;
    }
    if (!quiet) {
      console.log(
        stubbed
          ? `No design key — wrote ${stubbed} plain fallback(s). The app runs, unstyled.`
          : "No design key, and no vault present. Nothing to do.",
      );
    }
    return;
  }

  const { protect: files } = manifest();
  let opened = 0;
  for (const file of files) {
    const blob = encPath(file);
    if (!fs.existsSync(blob)) {
      if (!quiet) console.warn(`  skip    ${file}  (no .enc — run lock first)`);
      continue;
    }
    try {
      const plaintext = decrypt(fs.readFileSync(blob, "utf8"), key);
      fs.mkdirSync(path.dirname(abs(file)), { recursive: true });
      fs.writeFileSync(abs(file), plaintext);
      if (!quiet) console.log(`  opened  ${file}`);
      opened++;
    } catch {
      console.error(
        `  FAILED  ${file}  — wrong key, or the blob was tampered with.`,
      );
      process.exit(1);
    }
  }
  if (!quiet) console.log(`\n${opened} file(s) restored.`);
}

function status() {
  const key = readKey();
  const { protect } = manifest();
  console.log(`key: ${key ? "present" : "ABSENT — builds will fall back to plain"}\n`);
  console.log("  state      file");
  console.log("  ---------  ----------------------------------------");
  for (const file of protect) {
    const hasPlain = fs.existsSync(abs(file));
    const hasBlob = fs.existsSync(encPath(file));
    const state = hasBlob ? (hasPlain ? "unlocked" : "locked") : "unprotected";
    console.log(`  ${state.padEnd(9)}  ${file}`);
  }
}

function keygen() {
  const key = crypto.randomBytes(32).toString("base64url");
  console.log(key);
  console.error(
    "\nStore it somewhere you will not lose it. Without it the vault cannot be opened,\n" +
      "and nobody — including the author — can recover the design from the repository.",
  );
}

/* ---------------------------------------------------------------------- */

const command = process.argv[2];
const quiet = process.argv.includes("--quiet");

switch (command) {
  case "lock":
    lock();
    break;
  case "unlock":
    unlock({ quiet });
    break;
  case "status":
    status();
    break;
  case "keygen":
    keygen();
    break;
  default:
    console.log(
      "usage: design-vault.mjs <lock|unlock|status|keygen> [--quiet]\n\n" +
        "  lock    encrypt the protected files for committing\n" +
        "  unlock  restore them for development or a build\n" +
        "  status  show what is protected and its current state\n" +
        "  keygen  print a fresh key",
    );
    process.exit(command ? 1 : 0);
}
