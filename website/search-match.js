/**
 * Match semantics for RSDW search boxes: whitespace-separated tokens.
 * - Plain tokens: every token must appear in the haystack (AND, any order).
 * - Tokens starting with "-" (length > 1): exclusion; haystack must not contain
 *   that substring (e.g. "item -test" requires "item" and excludes paths with "test").
 * - A lone "-" token is ignored.
 * Empty query matches everything.
 */
(function (global) {
  function haystackMatchesQuery(haystack, query) {
    const raw = String(query || "")
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    if (raw.length === 0) {
      return true;
    }
    const positives = [];
    const negatives = [];
    for (const t of raw) {
      if (t.startsWith("-") && t.length > 1) {
        negatives.push(t.slice(1));
      } else if (!t.startsWith("-")) {
        positives.push(t);
      }
    }
    const h = String(haystack || "").toLowerCase();
    for (const neg of negatives) {
      if (h.includes(neg)) {
        return false;
      }
    }
    for (const pos of positives) {
      if (!h.includes(pos)) {
        return false;
      }
    }
    return true;
  }

  global.rsdwHaystackMatchesQuery = haystackMatchesQuery;
})(window);
