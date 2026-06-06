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
  "with", "without",
]);

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

function extractThemes(stories) {
  const counts = new Map();
  stories.forEach((story) => {
    const text = `${story.title} ${story.source}`.toLowerCase();
    text
      .replace(/[^a-z0-9\s-]/g, " ")
      .split(/\s+/)
      .filter((word) => word.length >= 4 && !STOP_WORDS.has(word))
      .forEach((word) => counts.set(word, (counts.get(word) || 0) + 1));
  });
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([word, count]) => ({ word, count }));
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
  themeList.innerHTML = "";
  const themes = extractThemes(visibleStories);
  if (!themes.length) {
    themeList.textContent = "Not enough stories in this filtered view yet.";
    return;
  }
  themes.forEach((theme) => {
    const pill = document.createElement("span");
    pill.className = "theme-pill";
    pill.textContent = `${theme.word} (${theme.count})`;
    themeList.appendChild(pill);
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

  document.getElementById("government-count").textContent = String(governmentStories.length);
  document.getElementById("nonprofit-count").textContent = String(nonprofitStories.length);

  renderColumn("government-list", governmentStories);
  renderColumn("nonprofit-list", nonprofitStories);
  updateAnalysis(collectVisibleStories(governmentStories, nonprofitStories));
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
