/* V885 isolated read-only candidate; not yet wired to the tablet UI. */
'use strict';
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TCGTabletMarketSearchV885 = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  const REGIONS = Object.freeze({
    ALL: ['KR', 'JP', 'US', 'CN-S', 'CN-T', 'GLOBAL'],
    KR: ['KR'], JP: ['JP'], US: ['US'], CN: ['CN-S', 'CN-T'],
    'CN-S': ['CN-S'], 'CN-T': ['CN-T'], GLOBAL: ['GLOBAL']
  });
  const LABELS = Object.freeze({
    KR: ['한국판', '한국어', 'korean'],
    JP: ['일본판', '일본어', 'japanese'],
    US: ['미국판', '영어판', 'english'],
    'CN-S': ['중국판', '중국 간체', 'simplified chinese'],
    'CN-T': ['중국판', '중국 번체', 'traditional chinese'],
    GLOBAL: ['글로벌', 'global']
  });
  const GAME_ALIASES = Object.freeze({
    'Pokémon': ['포켓몬', '포켓몬카드', 'pokemon'],
    'ONE PIECE': ['원피스', 'onepiece'],
    'NARUTO': ['나루토'],
    'UNKNOWN': []
  });
  const GAMES = new Set(['ALL', ...Object.keys(GAME_ALIASES)]);
  const KINDS = new Set(['ALL', 'BOX', 'HIT']);
  const normalize = value => String(value == null ? '' : value).normalize('NFKC').trim().toLocaleLowerCase('ko-KR');
  const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const identity = item => JSON.stringify([item.region, item.game, item.kind || item.asset, normalize(item.name)]);
  function aliasesFor(watch) {
    const index = new Map(), conflicts = new Set();
    const entries = Array.isArray(watch && watch.items) ? watch.items.slice(0, 5000) : [];
    for (const item of entries) {
      if (!item || typeof item !== 'object' || !hasOwn(REGIONS, item.region) ||
          item.region === 'ALL' || item.region === 'CN' ||
          typeof item.name !== 'string' || !item.name.trim() || item.name.length > 250 ||
          !hasOwn(GAME_ALIASES, item.game) || item.game === 'UNKNOWN' ||
          !['BOX', 'HIT'].includes(item.asset)) continue;
      const key = identity(item);
      const code = typeof item.product_code === 'string' ? item.product_code.trim().slice(0, 80) : '';
      const native = typeof item.native === 'string' ? item.native.trim().slice(0, 160) : '';
      if (index.has(key)) {
        const previous = index.get(key);
        if (previous.code !== code || previous.native !== native) conflicts.add(key);
      } else index.set(key, {code, native});
    }
    for (const key of conflicts) index.delete(key);
    return index;
  }
  function search(rows, watch, options = {}) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) return [];
    const region = options.region ?? 'ALL', game = options.game ?? 'ALL', kind = options.kind ?? 'ALL';
    if (!hasOwn(REGIONS, region) || !GAMES.has(game) || !KINDS.has(kind)) return [];
    if (options.limit !== undefined && (!Number.isSafeInteger(options.limit) || options.limit < 0)) return [];
    const max = options.limit === undefined ? 5000 : Math.min(options.limit, 5000);
    if (max === 0 || !Array.isArray(rows)) return [];
    if (options.query != null && typeof options.query !== 'string') return [];
    const query = normalize(options.query);
    if (query.length > 200) return [];
    const terms = query ? query.split(/\s+/u).filter(Boolean) : [];
    if (terms.length > 12) return [];
    const allowed = new Set(REGIONS[region]), aliases = terms.length ? aliasesFor(watch) : null, results = [];
    for (const row of rows.slice(0, 5000)) {
      if (!row || typeof row !== 'object' || Array.isArray(row) ||
          typeof row.name !== 'string' || !row.name.trim() || row.name.length > 250 ||
          !allowed.has(row.region) || !['HIT','BOX'].includes(row.kind) ||
          !GAMES.has(row.game) || row.game === 'ALL' ||
          (game !== 'ALL' && row.game !== game) || (kind !== 'ALL' && row.kind !== kind)) continue;
      if (!terms.length) { results.push(row); if (results.length >= max) break; continue; }
      const a = aliases.get(identity(row));
      const searchable = [row.name, row.region, row.game, row.kind,
        ...(LABELS[row.region] || []), ...(GAME_ALIASES[row.game] || []),
        ...(a ? [a.native, a.code] : [])].map(normalize).join(' ');
      if (terms.every(term => searchable.includes(term))) results.push(row);
      if (results.length >= max) break;
    }
    return results;
  }
  return Object.freeze({search, normalize, regions: Object.keys(REGIONS)});
});
