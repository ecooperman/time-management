// Single source of truth for the nav bar (see trip-planning/static/nav.js,
// the app this pattern is generalized from as Global.buildNav) - change a
// link here once instead of hunting down index.html/jobs.html/admin.html's
// copies.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/jobs.html") return "jobs";
  if (path === "/admin.html") return "settings";
  return "planner";
}

const active = currentNavActive();
Global.buildNav([
  { href: "/", icon: "calendar", label: "Planner", active: active === "planner" },
  { href: "/jobs.html", icon: "briefcase", label: "Jobs", active: active === "jobs" },
  { href: "/admin.html", icon: "tag", label: "Settings", active: active === "settings" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);
