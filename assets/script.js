document.addEventListener("DOMContentLoaded", function () {
  var filterBtns   = document.querySelectorAll(".filter-btn");
  var tiles        = document.querySelectorAll(".tile");
  var searchInput  = document.getElementById("search-input");
  var currentFilter = "all";
  var currentSearch = "";

  function applyFilters() {
    tiles.forEach(function (tile) {
      var isUs       = tile.getAttribute("data-us") === "true";
      var searchText = (tile.getAttribute("data-searchtext") || "").toLowerCase();

      var passesFilter =
        currentFilter === "all" ||
        (currentFilter === "us"   &&  isUs) ||
        (currentFilter === "intl" && !isUs);

      var passesSearch =
        currentSearch === "" || searchText.indexOf(currentSearch) !== -1;

      tile.classList.toggle("hidden", !(passesFilter && passesSearch));
    });
  }

  // Filter buttons
  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      filterBtns.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      currentFilter = btn.getAttribute("data-filter");
      applyFilters();
    });
  });

  // Search input — debounced slightly for performance
  if (searchInput) {
    var debounceTimer;
    searchInput.addEventListener("input", function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        currentSearch = searchInput.value.toLowerCase().trim();
        applyFilters();
      }, 150);
    });
  }
});
