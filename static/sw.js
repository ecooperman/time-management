// The first service worker in this app family - exists purely to receive
// Web Push messages and show them as notifications. Deliberately does NOT
// implement any fetch/caching strategy: the app's own no_cache middleware
// (see app/main.py) goes out of its way to keep the PWA from ever serving
// stale content, and a caching service worker would fight that. No fetch
// listener at all means every request just passes straight through to the
// network, same as if this file didn't exist for anything but push.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = { title: "Reminder", body: "You have a task to check on.", url: "/" };
  if (event.data) {
    try {
      payload = { ...payload, ...event.data.json() };
    } catch (e) {
      payload.body = event.data.text();
    }
  }
  const options = {
    body: payload.body,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: { url: payload.url || "/", taskId: payload.taskId || null },
  };
  // Only a task-linked reminder (not some future non-task push) gets a
  // "Mark done" action button. iOS reveals action buttons via a long-press/
  // pull-down on the notification, same UX as any native app - a plain tap
  // still just opens the app, handled below. Two actions is the safe
  // cross-platform max; this app only needs one.
  if (payload.taskId) {
    options.actions = [{ action: "mark_done", title: "Mark done" }];
  }
  event.waitUntil(self.registration.showNotification(payload.title, options));
});

self.addEventListener("notificationclick", (event) => {
  const data = event.notification.data || {};
  const targetUrl = data.url || "/";
  event.notification.close();

  if (event.action === "mark_done" && data.taskId) {
    event.waitUntil(
      fetch(`/api/tasks/${data.taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "done" }),
      })
        .then((res) => {
          // A lapsed Cloudflare Access session answers with a redirect to
          // a login page (not JSON) instead of a real API error - treat
          // anything that isn't a genuine successful API response as a
          // failure and fall back to opening the app, rather than silently
          // doing nothing and leaving the task looking done when it isn't.
          if (!res.ok) throw new Error(`mark done failed: ${res.status}`);
          return res.json();
        })
        .catch(() => focusOrOpen(targetUrl))
    );
    return;
  }

  event.waitUntil(focusOrOpen(targetUrl));
});

function focusOrOpen(targetUrl) {
  return self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
    for (const client of clientList) {
      if ("focus" in client) {
        client.navigate(targetUrl);
        return client.focus();
      }
    }
    if (self.clients.openWindow) {
      return self.clients.openWindow(targetUrl);
    }
  });
}
