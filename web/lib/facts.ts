/**
 * Claims the marketing page makes about the system.
 *
 * The landing page's whole argument is that nothing should be asserted
 * without evidence. It then asserted "185 TESTS PASSING" in two places, from
 * two separate literals, for a suite that had long since grown past it — and
 * a number nobody can check is exactly the kind of number the page spends
 * three sections telling you not to trust.
 *
 * One constant now, and `api/tests/test_claims.py` fails the build when it
 * stops matching the real collected count. So this cannot quietly rot: the
 * suite that the number is *about* is the thing that checks it.
 *
 * Everything else on that page — which model is reasoning, what is
 * transcribing, whether the index is semantic — is read from /api/health at
 * runtime rather than written down here, because those change per deployment.
 */

/** Backend tests collected by `pytest --collect-only`. */
export const TEST_COUNT = 1007;

/** Metric fixtures computed by hand and asserted against the engine. */
export const HAND_COMPUTED_FIXTURES = 45;

/** The talk-ratio benchmark every call is measured against. */
export const TALK_RATIO_BENCHMARK = 43;
