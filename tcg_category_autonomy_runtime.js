/* v424: evidence-bounded autonomous TCG category UI runtime. */
(function () {
  "use strict";

  var VERSION = "v424-category-autonomy";
  var REGISTRY_URL = "./tcg_game_registry.json";
  var CACHE_TTL_MS = 6 * 60 * 60 * 1000;
  var CORE_TERMS = {
    Pokemon: { KR: "포켓몬 카드", JP: "ポケモンカード", US: "Pokemon cards" },
    "Pokémon": { KR: "포켓몬 카드", JP: "ポケモンカード", US: "Pokemon cards" },
    "ONE PIECE": { KR: "원피스 카드", JP: "ワンピースカード", US: "One Piece Card Game" },
    NARUTO: { KR: "나루토 카드게임", JP: "NARUTO カードゲーム", US: "Naruto Card Game" }
  };
  var cache = { registry: null, loadedAt: 0, enabled: [], watch: [], terms: {} };

  function text(value, fallback) {
    var result = String(value == null ? "" : value).trim();
    return result || String(fallback == null ? "" : fallback);
  }

  function activeState(state) {
    return state === "core" || state === "promoted";
  }

  function capability(row, name) {
    return !!(row && row.capabilities && row.capabilities[name] === true);
  }

  function safeRows(data) {
    return Array.isArray(data && data.games) ? data.games.filter(function (row) {
      return row && typeof row === "object" && text(row.id) && text(row.canonical);
    }) : [];
  }

  function validRegistry(data) {
    if (!data || typeof data !== "object" || data.schema_version !== 1) return false;
    if (!data.policy || data.policy.profit_guarantee !== false ||
        data.policy.market_direction_prediction !== false ||
        data.policy.source_code_auto_generation !== false ||
        data.policy.user_behavior_tracking !== false) return false;
    var rows = safeRows(data);
    if (rows.length < 3 || rows.length > 64) return false;
    var ids = {};
    var canonicals = {};
    var coreIds = {};
    rows.forEach(function (row) {
      if (row.state === "core") coreIds[row.id] = true;
      ids[row.id] = (ids[row.id] || 0) + 1;
      canonicals[String(row.canonical).toLowerCase()] =
        (canonicals[String(row.canonical).toLowerCase()] || 0) + 1;
    });
    if (ids.pokemon !== 1 || ids.onepiece !== 1 || ids.naruto !== 1) return false;
    if (Object.keys(ids).some(function (key) { return ids[key] !== 1; })) return false;
    if (Object.keys(canonicals).some(function (key) { return canonicals[key] !== 1; })) return false;
    return rows.every(function (row) {
      return ["core", "promoted", "watch"].indexOf(String(row.state)) >= 0 &&
        row.capabilities && row.capabilities.grading !== true ? true :
        row.state === "core" && row.capabilities && row.capabilities.grading === true;
    });
  }

  function fallbackRegistry() {
    return {
      schema_version: 1,
      updated_at: "",
      policy: {
        profit_guarantee: false,
        investment_return_prediction: false,
        market_direction_prediction: false,
        source_code_auto_generation: false,
        user_behavior_tracking: false
      },
      games: [
        {
          id: "pokemon", canonical: "Pokémon", label_ko: "포켓몬", state: "core",
          purchase_value: "Pokemon", promo_value: "포켓몬 카드",
          aliases: ["pokemon", "pokémon", "포켓몬"],
          capabilities: { market: true, release: true, promo: true, purchase: true, grading: true },
          regions: ["KR", "JP", "US"], activation_score: 1
        },
        {
          id: "onepiece", canonical: "ONE PIECE", label_ko: "원피스", state: "core",
          purchase_value: "ONE PIECE", promo_value: "원피스 카드",
          aliases: ["one piece", "onepiece", "원피스"],
          capabilities: { market: true, release: true, promo: true, purchase: true, grading: true },
          regions: ["KR", "JP", "US"], activation_score: 1
        },
        {
          id: "naruto", canonical: "NARUTO", label_ko: "나루토", state: "core",
          purchase_value: "NARUTO", promo_value: "나루토 카드",
          aliases: ["naruto", "나루토"],
          capabilities: { market: true, release: true, promo: true, purchase: true, grading: true },
          regions: ["KR", "JP", "US"], activation_score: 1
        }
      ]
    };
  }

  function rowsFor(data, name, includeWatch) {
    return safeRows(data).filter(function (row) {
      return (activeState(String(row.state)) || (includeWatch && row.state === "watch")) &&
        capability(row, name);
    }).sort(function (a, b) {
      var stateA = a.state === "core" ? 0 : a.state === "promoted" ? 1 : 2;
      var stateB = b.state === "core" ? 0 : b.state === "promoted" ? 1 : 2;
      if (stateA !== stateB) return stateA - stateB;
      return Number(b.activation_score || 0) - Number(a.activation_score || 0);
    });
  }

  function termFor(row) {
    var value = text(row.purchase_value || row.canonical || row.label_ko, row.id);
    var korean = text(row.promo_value || row.label_ko || row.canonical, value);
    return {
      KR: korean.indexOf("카드") >= 0 ? korean : korean + " 카드",
      JP: value + " カード",
      US: value + " cards"
    };
  }

  function buildTerms(rows) {
    var terms = {};
    Object.keys(CORE_TERMS).forEach(function (key) {
      terms[key] = CORE_TERMS[key];
    });
    rows.forEach(function (row) {
      var value = text(row.purchase_value || row.canonical, row.id);
      var term = termFor(row);
      [value, row.canonical, row.id].concat(Array.isArray(row.aliases) ? row.aliases : [])
        .forEach(function (key) {
          if (text(key)) terms[text(key)] = term;
        });
    });
    return terms;
  }

  function optionValue(row, name) {
    if (name === "promo") return text(row.promo_value || row.canonical, row.id);
    if (name === "purchase") return text(row.purchase_value || row.canonical, row.id);
    return text(row.canonical, row.id);
  }

  function appendOption(parent, row, name) {
    var option = document.createElement("option");
    option.value = optionValue(row, name);
    option.textContent = text(row.label_ko || row.canonical, row.id);
    option.dataset.tcgRegistryId = text(row.id);
    option.dataset.tcgState = text(row.state);
    parent.appendChild(option);
  }

  function replaceSelect(id, rows, name, includeAll, includeWatch) {
    var select = document.getElementById(id);
    if (!select) return;
    var previous = String(select.value || "");
    var fragment = document.createDocumentFragment();
    if (includeAll) {
      var all = document.createElement("option");
      all.value = "ALL";
      all.textContent = "🎴 전체 게임";
      fragment.appendChild(all);
    }
    var active = rows.filter(function (row) { return activeState(row.state); });
    var watch = rows.filter(function (row) { return row.state === "watch"; });
    active.forEach(function (row) { appendOption(fragment, row, name); });
    if (includeWatch && watch.length) {
      var group = document.createElement("optgroup");
      group.label = "AI 관찰 후보 · 검증 전";
      watch.forEach(function (row) { appendOption(group, row, name); });
      fragment.appendChild(group);
    }
    select.replaceChildren(fragment);
    var values = Array.prototype.map.call(select.options, function (option) { return option.value; });
    select.value = values.indexOf(previous) >= 0 ? previous : (includeAll ? "ALL" : values[0] || "");
  }

  function numberText(value) {
    var number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2) : "미확인";
  }

  function element(tag, className, content) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (content != null) node.textContent = content;
    return node;
  }

  function renderPanel() {
    if (!document.body || !cache.registry) return;
    var panel = document.getElementById("tcgCategoryAutonomyPanel");
    if (!panel) {
      panel = element("section", "top-info-panel tcg-category-autonomy-panel");
      panel.id = "tcgCategoryAutonomyPanel";
      var anchor = document.getElementById("featureCategories") ||
        document.querySelector("main.app") || document.body.firstElementChild;
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(panel, anchor.nextSibling);
      else document.body.appendChild(panel);
    }
    panel.replaceChildren();
    var head = element("div", "feature-category-head");
    var titleBox = element("div");
    titleBox.appendChild(element("h2", "", "AI 자동 카테고리 감시·확장"));
    titleBox.appendChild(element(
      "p", "muted",
      "검증된 카테고리는 화면에 연결하고, 근거가 부족한 카테고리는 관찰 후보로만 유지합니다."
    ));
    head.appendChild(titleBox);
    var refresh = element("button", "secondary-button", "카테고리 새로고침");
    refresh.type = "button";
    refresh.addEventListener("click", function () { loadRegistry(true); });
    head.appendChild(refresh);
    panel.appendChild(head);

    var summary = element(
      "div", "muted",
      "활성 " + cache.enabled.length + "개 · 관찰 후보 " + cache.watch.length +
        "개 · 기준시각 " + text(cache.registry.updated_at, "미확인")
    );
    summary.style.margin = "8px 0";
    panel.appendChild(summary);

    var list = element("div", "tcg-category-autonomy-list");
    cache.enabled.slice(0, 24).forEach(function (row) {
      var item = element("div", "tcg-category-autonomy-item");
      item.dataset.tcgState = text(row.state);
      var label = text(row.label_ko || row.canonical, row.id);
      var stateLabel = row.state === "core" ? "핵심" : "활성";
      item.appendChild(element("strong", "", label + " · " + stateLabel));
      item.appendChild(element(
        "span", "muted",
        "  " + text(row.canonical) + " · 근거점수 " + numberText(row.activation_score) +
          " · " + (Array.isArray(row.regions) ? row.regions.join("/") : "지역 미확인")
      ));
      list.appendChild(item);
    });
    if (cache.watch.length) {
      list.appendChild(element("h3", "", "관찰 후보"));
      cache.watch.slice(0, 24).forEach(function (row) {
        var item = element("div", "tcg-category-autonomy-item");
        item.dataset.tcgState = "watch";
        item.appendChild(element(
          "strong", "",
          text(row.label_ko || row.canonical, row.id) + " · 관찰"
        ));
        item.appendChild(element(
          "span", "muted",
          "  " + text(row.canonical) + " · 활성화 전 근거 확인 필요"
        ));
        list.appendChild(item);
      });
    }
    panel.appendChild(list);
    panel.appendChild(element(
      "p", "muted",
      "안전 제한: 수익 보장·가격 방향 예측·임의 코드 생성·검증 전 자동 활성화는 하지 않습니다."
    ));
  }

  function publish(data) {
    var rows = safeRows(data);
    cache.registry = data;
    cache.enabled = rows.filter(function (row) {
      return activeState(row.state) && capability(row, "market");
    });
    cache.watch = rows.filter(function (row) {
      return row.state === "watch" && capability(row, "market");
    });
    cache.terms = buildTerms(rows);
    replaceSelect("v12Game", rowsFor(data, "market", false), "market", true, false);
    replaceSelect("v13Game", rowsFor(data, "market", false), "market", true, false);
    replaceSelect("analysisGame", rowsFor(data, "market", false), "market", true, false);
    replaceSelect("tradeGame", rowsFor(data, "market", false), "market", true, false);
    replaceSelect("promoGame", rowsFor(data, "promo", false), "promo", true, false);
    replaceSelect("purchaseGame", rowsFor(data, "purchase", true), "purchase", false, true);
    renderPanel();
    document.dispatchEvent(new CustomEvent("tcg-category-registry-ready", {
      detail: {
        version: VERSION,
        registry: data,
        enabled: cache.enabled.slice(),
        watch: cache.watch.slice(),
        terms: Object.assign({}, cache.terms),
        generatedAt: new Date().toISOString()
      }
    }));
  }

  function loadRegistry(force) {
    if (!force && cache.registry && Date.now() - cache.loadedAt < CACHE_TTL_MS) {
      publish(cache.registry);
      return Promise.resolve(cache.registry);
    }
    return fetch(REGISTRY_URL, { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error("TCG_CATEGORY_REGISTRY_HTTP_" + response.status);
      return response.json();
    }).then(function (data) {
      if (!validRegistry(data)) throw new Error("TCG_CATEGORY_REGISTRY_INVALID");
      cache.loadedAt = Date.now();
      publish(data);
      return data;
    }).catch(function () {
      var fallback = fallbackRegistry();
      cache.loadedAt = Date.now();
      publish(fallback);
      return fallback;
    });
  }

  window.TCGCategoryRuntime = {
    version: VERSION,
    load: loadRegistry,
    enabled: function () { return cache.enabled.slice(); },
    watch: function () { return cache.watch.slice(); },
    termsFor: function (key) { return cache.terms[text(key)] || null; },
    snapshot: function () {
      return {
        version: VERSION,
        registry: cache.registry,
        enabled: cache.enabled.slice(),
        watch: cache.watch.slice()
      };
    }
  };

  function boot() {
    loadRegistry(false);
    window.setInterval(function () { loadRegistry(true); }, CACHE_TTL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
