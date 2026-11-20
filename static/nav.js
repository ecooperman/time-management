// Single source of truth for the nav bar (see trip-planning/static/nav.js,
// the app this pattern is generalized from as Global.buildNav) - change a
// link here once instead of hunting down index.html/admin.html's
// copies.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/admin.html") return "settings";
  if (path === "/users.html") return "users";
  return "planner";
}

const active = currentNavActive();

// This app has no page header to carry the shared "signed in as ... Log out" corner, so Log out lives in the menu
// (last, after Refresh). The menu is built straight away and rebuilt once we know who is signed in. The shared
// code adds a Dashboard entry too. On a phone only the first three stay on the bar; the rest sit behind More.
function buildTimeNav(me) {
  const items = [
    { href: "/", icon: "calendar", label: "Planner", active: active === "planner" },
    { href: "/admin.html", icon: "tag", label: "Settings", active: active === "settings" },
    { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
  ];
  // Only administrators can let people in.
  if (me && me.is_admin) items.splice(2, 0, { href: "/users.html", icon: "users", label: "Users", active: active === "users" });
  if (me) items.push({ href: me.logout_url || "/cdn-cgi/access/logout", icon: "log-out", label: "Log out" });
  Global.buildNav(items, "app-nav-mount", { barItems: 3 });
}

buildTimeNav(null);
Global.currentUser().then((me) => {
  if (me) buildTimeNav(me);
});

// Registered here (not per-page) so it's active no matter which page the
// PWA happens to be opened to - see static/sw.js. Push notifications only
// work once this registration exists; the actual subscribe flow ("Enable
// reminders" on Settings) is separate and only needed once per device.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch((err) => {
    console.error("Service worker registration failed:", err);
  });
}
