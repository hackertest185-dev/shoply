import { getApp, getApps, initializeApp } from "firebase/app";
import { getMessaging, onBackgroundMessage } from "firebase/messaging/sw";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

if (Object.values(firebaseConfig).every(value => typeof value === "string" && value.length > 0)) {
  const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
  const messaging = getMessaging(app);

  onBackgroundMessage(messaging, payload => {
    const title = payload.notification?.title || "Shoply: طلب جديد";
    const options = {
      body: payload.notification?.body || "وصلك طلب جديد من المتجر.",
      icon: "/favicon.svg",
      badge: "/favicon.svg",
      data: { url: payload.fcmOptions?.link || "/", orderId: payload.data?.order_id || "" },
      tag: payload.data?.order_id || "shoply-new-order",
    };
    return self.registration.showNotification(title, options);
  });
}

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const destination = new URL(event.notification.data?.url || "/", self.location.origin);
  destination.searchParams.set("admin_orders", "1");
  const target = destination.href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const existing = windows.find(client => client.url.startsWith(self.location.origin));
    if (existing) {
      await existing.navigate(target);
      await existing.focus();
      return;
    }
    await self.clients.openWindow(target);
  })());
});
