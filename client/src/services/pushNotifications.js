import { getApp, getApps, initializeApp } from "firebase/app";
import { deleteToken, getMessaging, getToken, isSupported, onMessage } from "firebase/messaging";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY;
const configured = Object.values(firebaseConfig).every(value => typeof value === "string" && value.length > 0) && Boolean(vapidKey);

export function isPushConfigured() {
  return configured;
}

async function getPushRuntime() {
  if (!configured) throw new Error("Firebase notifications have not been configured yet.");
  if (!(await isSupported())) throw new Error("This browser does not support web push notifications.");
  if (!("serviceWorker" in navigator) || !("Notification" in window)) {
    throw new Error("This browser does not support web push notifications.");
  }
  const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
  const messaging = getMessaging(app);
  const serviceWorkerRegistration = await navigator.serviceWorker.register("/firebase-messaging-sw.js", { type: "module" });
  return { messaging, serviceWorkerRegistration };
}

export async function enableAdminPush() {
  const { messaging, serviceWorkerRegistration } = await getPushRuntime();
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Allow notifications in your browser to receive new-order alerts.");
  const token = await getToken(messaging, { vapidKey, serviceWorkerRegistration });
  if (!token) throw new Error("Could not register this device for notifications.");
  return { token, messaging };
}

export async function disableAdminPush() {
  const { messaging, serviceWorkerRegistration } = await getPushRuntime();
  const token = await getToken(messaging, { vapidKey, serviceWorkerRegistration });
  if (token) await deleteToken(messaging);
  return token;
}

export function listenForForegroundPush(messaging, onNotification) {
  return onMessage(messaging, payload => onNotification(payload));
}
