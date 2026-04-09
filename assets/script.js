document.addEventListener("DOMContentLoaded", function () {
  var filterBtns = document.querySelectorAll(".filter-btn");
  var tiles      = document.querySelectorAll(".tile");

  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      // Update active button
      filterBtns.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");

      var filter = btn.getAttribute("data-filter");

      tiles.forEach(function (tile) {
        var isUs = tile.getAttribute("data-us") === "true";

        if (filter === "all") {
          tile.classList.remove("hidden");
        } else if (filter === "us") {
          isUs ? tile.classList.remove("hidden") : tile.classList.add("hidden");
        } else if (filter === "intl") {
          isUs ? tile.classList.add("hidden") : tile.classList.remove("hidden");
        }
      });
    });
  });
});
