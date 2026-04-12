/**
 * Match semantics aligned with index.html (app.js) file search: whitespace-separated
 * terms must all appear in the haystack (any order). Empty query matches everything.
 */
(function (global) {
  function haystackMatchesQuery(haystack, query) {
    const tokens = String(query || "")
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    if (tokens.length === 0) {
      return true;
    }
    const h = String(haystack || "").toLowerCase();
    return tokens.every((t) => h.includes(t));
  }

  global.rsdwHaystackMatchesQuery = haystackMatchesQuery;
})(window);
