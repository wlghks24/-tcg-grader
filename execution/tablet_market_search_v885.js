/* V885 proposal: deterministic, read-only local search; not wired into tablet UI. */
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
  const GAMES = new Set(['ALL', 'Pokémon', 'ONE PIECE', 'NARUTO', 'UNKNOWN']);
  const KINDS = new Set(['ALL', 'BOX', 'HIT']);
  const normalize = value => String(value == null ? '' : value).normalize('NFKC').trim().toLocaleLowerCase('ko-KR');
  function identity(item) {
    return [item.region, normalize(item.game), item.kind || item.asset, normalize(item.name)].join('|');
  }
  function aliasesFor(watch) {
    const index = new Map(), conflicts = new Set();
    const entries = Array.isArray(watch && watch.items) ? watch.items.slice(0, 5000) : [];
    for (const item of entries) {
      if (!item || !REGIONS[item.region] || item.region === 'ALL' || item.region === 'CN' ||
          !item.name || !item.game || !['BOX', 'HIT'].includes(item.asset)) continue;
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
    const region = options.region || 'ALL', game = options.game || 'ALL', kind = options.kind || 'ALL';
    if (!Object.prototype.hasOwnProperty.call(REGIONS, region) || !GAMES.has(game) || !KINDS.has(kind)) return [];
    const query = normalize(options.query).slice(0, 200);
    const max = Number.isSafeInteger(options.limit) && options.limit > 0 ? Math.min(options.limit, 5000) : 5000;
    const allowed = new Set(REGIONS[region]), aliases = aliasesFor(watch), results = [];
    for (const row of (Array.isArray(rows) ? rows.slice(0, 5000) : [])) {
      if (!row || !allowed.has(row.region) || !['HIT','BOX'].includes(row.kind) ||
          !GAMES.has(row.game) || row.game === 'ALL' ||
          (game !== 'ALL' && row.game !== game) || (kind !== 'ALL' && row.kind !== kind)) continue;
      const a = aliases.get(identity(row));
      const searchable = [row.name, row.region, row.game, row.kind, ...(LABELS[row.region] || []),
        ...(a ? [a.native, a.code] : [])].map(normalize).join(' ');
      if (!query || searchable.includes(query)) results.push(row);
      if (results.length >= max) break;
    }
    return results;
  }
  return Object.freeze({search, normalize, regions: Object.keys(REGIONS)});
});
