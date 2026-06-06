const state = {
  filters: {
    region: "all",
    sentiment: "all",
    column: "all",
  },
  data: null,
  months: [],
};

const STOP_WORDS = new Set([
  "about", "after", "against", "among", "board", "case", "city", "could",
  "ethics", "from", "government", "group", "into", "more", "news", "nonprofit",
  "public", "report", "says", "story", "that", "their", "there", "these",
  "they", "this", "through", "under", "using", "what", "when", "where",
  "with", "without", "former", "official", "officials", "executives", "executive",
  "probe", "investigation", "corruption", "fraud", "bribery", "ethics", "ngo",
  "charity", "nonprofit", "government", "public", "case", "cases",
]);

const PHRASE_STOP_WORDS = new Set([
  "the", "and", "for", "with", "from", "into", "over", "after", "amid", "under",
  "into", "that", "this", "will", "have", "been", "were", "your", "their",
]);

const BEHAVIOR_THEMES = [
  { label: "Integrity", patterns: ["integrity", "ethical conduct", "ethical leadership"] },
  { label: "Accountability", patterns: ["accountability", "accountable", "held accountable"] },
  { label: "Whistleblower", patterns: ["whistleblower", "whistleblowers"] },
  { label: "Transparency", patterns: ["transparency", "transparent"] },
  { label: "Oversight", patterns: ["oversight"] },
  { label: "Audit", patterns: ["audit", "auditor", "auditors"] },
  { label: "Ethics Reform", patterns: ["ethics reform", "ethics rules", "ethics overhaul"] },
  { label: "Anti-Corruption Reform", patterns: ["anti-corruption", "anti corruption", "corruption reform", "anti-graft"] },
  { label: "Conflict Of Interest", patterns: ["conflict of interest", "conflicts of interest"] },
  { label: "Self-Dealing", patterns: ["self-dealing", "self dealing"] },
  { label: "Abuse Of Power", patterns: ["abuse of power", "power abuse"] },
  { label: "Procurement Abuse", patterns: ["procurement fraud", "procurement", "bid rigging", "contract fraud"] },
  { label: "Fund Misuse", patterns: ["misuse of funds", "fund misuse", "misused funds", "misappropriation"] },
  { label: "Bribery", patterns: ["bribery", "bribe", "bribes"] },
  { label: "Fraud", patterns: ["fraud", "fraudulent"] },
  { label: "Embezzlement", patterns: ["embezzlement", "embezzle", "embezzled"] },
  { label: "Graft", patterns: ["graft"] },
  { label: "Misconduct", patterns: ["misconduct"] },
  { label: "Ethics Violations", patterns: ["ethics violation", "ethics violations"] },
  { label: "Corruption", patterns: ["corruption", "corrupt"] },
  { label: "Nepotism", patterns: ["nepotism"] },
  { label: "Cronyism", patterns: ["cronyism"] },
  { label: "Pay-To-Play", patterns: ["pay-to-play", "pay to play"] },
  { label: "Extortion", patterns: ["extortion"] },
  { label: "Cover-Up", patterns: ["cover-up", "cover up"] },
];

function formatDate(value) {
  if (!value) return "Unknown date";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown date";
  return parsed.toLocaleString();
}

function formatMonth(month) {
  const [year, monthNumber] = month.split("-");
  const parsed = new Date(`${year}-${monthNumber}-01T00:00:00Z`);
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "long" });
}

function getView() {
  return document.body.dataset.view || "current";
}

function getArchiveMonth() {
  const params = new URLSearchParams(window.location.search);
  return params.get("month");
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path} (${response.status})`);
  }
  return response.json();
}

async function loadMonths() {
  const prefix = getView() === "archive" ? "../" : "";
  const data = await fetchJson(`${prefix}data/archive/months.json`);
  return Array.isArray(data.months) ? data.months : [];
}

async function loadData() {
  const prefix = getView() === "archive" ? "../" : "";
  if (getView() === "archive") {
    const month = getArchiveMonth();
    if (!month) {
      throw new Error("No archive month specified.");
    }
    return fetchJson(`${prefix}data/archive/${month}.json`);
  }
  return fetchJson(`${prefix}data/current.json`);
}

function wireFilters() {
  document.querySelectorAll("[data-filter-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const { filterGroup, filterValue } = button.dataset;
      state.filters[filterGroup] = filterValue;
      document
        .querySelectorAll(`[data-filter-group="${filterGroup}"]`)
        .forEach((item) => item.classList.toggle("active", item === button));
      render();
    });
  });
}

function storyMatches(story) {
  if (state.filters.region !== "all" && story.region !== state.filters.region) {
    return false;
  }
  if (state.filters.sentiment !== "all" && story.sentiment !== state.filters.sentiment) {
    return false;
  }
  return true;
}

function buildTile(story) {
  const tile = document.createElement("article");
  tile.className = `tile ${story.sentiment || "negative"}`;

  const link = document.createElement("a");
  link.href = story.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = story.short_title || story.title || "Untitled story";
  tile.appendChild(link);

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${story.source || "Unknown source"} | ${formatDate(story.published_at)}`;
  tile.appendChild(meta);

  const tags = document.createElement("div");
  tags.className = "tag-row";
  [
    story.region === "us" ? "US" : "Non-US",
    story.sentiment === "positive" ? "Good / Green" : "Bad / Red",
  ].forEach((text) => {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = text;
    tags.appendChild(tag);
  });
  tile.appendChild(tags);

  return tile;
}

function renderColumn(elementId, stories) {
  const list = document.getElementById(elementId);
  list.innerHTML = "";
  if (!stories.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No matching stories for this filter.";
    list.appendChild(empty);
    return;
  }
  stories.forEach((story) => list.appendChild(buildTile(story)));
}

function collectVisibleStories(governmentStories, nonprofitStories) {
  const byUrl = new Map();
  [...governmentStories, ...nonprofitStories].forEach((story) => {
    if (!byUrl.has(story.url)) {
      byUrl.set(story.url, story);
    }
  });
  return [...byUrl.values()];
}

function titleTokens(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length >= 3 && !STOP_WORDS.has(word));
}

function normalizePhrase(words) {
  return words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function extractThemes(stories) {
  const behaviorCounts = new Map();
  const wordCounts = new Map();
  const phraseCounts = new Map();

  stories.forEach((story) => {
    const title = (story.title || "").toLowerCase();
    BEHAVIOR_THEMES.forEach((theme) => {
      if (theme.patterns.some((pattern) => title.includes(pattern))) {
        behaviorCounts.set(theme.label, (behaviorCounts.get(theme.label) || 0) + 1);
      }
    });

    const words = titleTokens(title);
    words.forEach((word) => wordCounts.set(word, (wordCounts.get(word) || 0) + 1));

    for (let index = 0; index < words.length - 1; index += 1) {
      const pair = [words[index], words[index + 1]];
      if (pair.some((word) => PHRASE_STOP_WORDS.has(word))) {
        continue;
      }
      const phrase = normalizePhrase(pair);
      phraseCounts.set(phrase, (phraseCounts.get(phrase) || 0) + 1);
    }

    for (let index = 0; index < words.length - 2; index += 1) {
      const triple = [words[index], words[index + 1], words[index + 2]];
      if (triple.some((word) => PHRASE_STOP_WORDS.has(word))) {
        continue;
      }
      const phrase = normalizePhrase(triple);
      phraseCounts.set(phrase, (phraseCounts.get(phrase) || 0) + 1);
    }
  });

  const behaviorThemes = [...behaviorCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([label, count]) => ({ label, count }));

  if (behaviorThemes.length) {
    return behaviorThemes;
  }

  const phrases = [...phraseCounts.entries()]
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 6)
    .map(([phrase, count]) => ({ label: phrase, count }));

  if (phrases.length >= 4) {
    return phrases;
  }

  const words = [...wordCounts.entries()]
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([word, count]) => ({ label: normalizePhrase([word]), count }));

  return [...phrases, ...words].slice(0, 8);
}

function updateAnalysis(visibleStories) {
  const visibleCount = visibleStories.length;
  const usCount = visibleStories.filter((story) => story.region === "us").length;
  const nonUsCount = visibleStories.filter((story) => story.region === "non-us").length;
  const greenCount = visibleStories.filter((story) => story.sentiment === "positive").length;
  const redCount = visibleStories.filter((story) => story.sentiment === "negative").length;

  document.getElementById("visible-count").textContent = String(visibleCount);
  document.getElementById("region-breakdown").textContent = `US ${usCount} | Non-US ${nonUsCount}`;
  document.getElementById("sentiment-breakdown").textContent = `Green ${greenCount} | Red ${redCount}`;

  const themeList = document.getElementById("theme-list");
  const headerThemeList = document.getElementById("header-theme-list");
  const headerThemeSummary = document.getElementById("header-theme-summary");
  themeList.innerHTML = "";
  headerThemeList.innerHTML = "";
  const themes = extractThemes(visibleStories);
  if (!themes.length) {
    themeList.textContent = "Not enough stories in this filtered view yet.";
    headerThemeSummary.textContent = "Not enough repeated language in the current filter yet.";
    return;
  }
  headerThemeSummary.textContent = `Most common recurring themes across ${visibleStories.length} visible stories.`;
  themes.forEach((theme) => {
    const pill = document.createElement("span");
    pill.className = "theme-pill";
    pill.textContent = `${theme.label} (${theme.count})`;
    themeList.appendChild(pill);
    headerThemeList.appendChild(pill.cloneNode(true));
  });
}

function renderArchiveNav() {
  const container = document.getElementById("archive-links");
  container.innerHTML = "";
  state.months.forEach((month) => {
    const link = document.createElement("a");
    link.className = "archive-link";
    link.textContent = formatMonth(month);
    link.href = getView() === "archive" ? `index.html?month=${month}` : `archive/index.html?month=${month}`;
    if (getView() === "archive" && month === getArchiveMonth()) {
      link.classList.add("active");
    }
    container.appendChild(link);
  });
}

function render() {
  if (!state.data) {
    return;
  }

  const governmentColumn = document.getElementById("government-column");
  const nonprofitColumn = document.getElementById("nonprofit-column");
  governmentColumn.classList.toggle("hidden", state.filters.column === "nonprofit");
  nonprofitColumn.classList.toggle("hidden", state.filters.column === "government");

  const governmentStories = (state.data.government || []).filter(storyMatches);
  const nonprofitStories = (state.data.nonprofit || []).filter(storyMatches);
  let visibleStories;

  if (state.filters.column === "government") {
    visibleStories = collectVisibleStories(governmentStories, []);
  } else if (state.filters.column === "nonprofit") {
    visibleStories = collectVisibleStories([], nonprofitStories);
  } else {
    visibleStories = collectVisibleStories(governmentStories, nonprofitStories);
  }

  document.getElementById("government-count").textContent = String(governmentStories.length);
  document.getElementById("nonprofit-count").textContent = String(nonprofitStories.length);

  renderColumn("government-list", governmentStories);
  renderColumn("nonprofit-list", nonprofitStories);
  updateAnalysis(visibleStories);
}

async function init() {
  try {
    wireFilters();
    state.months = await loadMonths();
    renderArchiveNav();
    state.data = await loadData();
    render();

    const updated = document.getElementById("last-updated");
    updated.textContent = state.data.updated_at
      ? `Last updated: ${formatDate(state.data.updated_at)}`
      : "Last updated: unknown";

    if (getView() === "archive") {
      document.getElementById("archive-title").textContent = `${formatMonth(getArchiveMonth())} archive`;
      updated.textContent = state.data.label
        ? `${state.data.label} | ${updated.textContent}`
        : updated.textContent;
    }
  } catch (error) {
    document.getElementById("last-updated").textContent = `Could not load data: ${error.message}`;
    document.getElementById("government-list").innerHTML = '<div class="empty">Archive load failed.</div>';
    document.getElementById("nonprofit-list").innerHTML = '<div class="empty">Archive load failed.</div>';
  }
}

init();
