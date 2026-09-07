"use client";

/**
 * Loads the field, late and only where it can run.
 *
 * three.js and the fiber renderer are the largest thing this app can ask a
 * browser to download, and the field is decoration -- so it is code-split away
 * from the first paint entirely. Nothing on any page waits on it, and a device
 * that cannot draw it never pays for the bytes.
 */

import dynamic from "next/dynamic";

const Field = dynamic(() => import("./Field").then((m) => m.Field), {
  ssr: false,
  loading: () => null,
});

export function FieldMount() {
  return <Field />;
}
