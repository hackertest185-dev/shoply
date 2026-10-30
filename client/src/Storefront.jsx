import { useState, useEffect, useReducer, useContext, createContext, useCallback, useRef, useId } from "react";
import { useSelector, useDispatch as useReduxDispatch } from 'react-redux';
import { logoutUser, sessionEstablished } from './features/auth/authSlice';
import PasswordStrength from './components/PasswordStrength';
import { getPasswordFeedback } from './utils/passwordPolicy';
import { disableAdminPush, enableAdminPush, isPushConfigured, listenForForegroundPush } from './services/pushNotifications';

const formatMoney = amount => `${Number(amount || 0).toLocaleString('en-EG', { maximumFractionDigits: 2 })} EGP`;

// The reference experience is a 240-frame canvas sequence. Keeping every
// fourth frame locally gives us the same scroll-scrub feel without making the
// storefront bundle unnecessarily heavy.
const SAFE_IMAGE_HOSTS = new Set(['images.unsplash.com']);
function safeImageSource(value, fallback = '') {
  if (typeof value !== 'string' || !value.trim()) return fallback;
  const raw = value.trim();
  if (raw.startsWith('/') && !raw.startsWith('//')) return raw;
  if (/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/i.test(raw)) return raw;
  try {
    const parsed = new URL(raw);
    if (parsed.protocol === 'https:' && (SAFE_IMAGE_HOSTS.has(parsed.hostname) || parsed.hostname.endsWith('.s3.amazonaws.com'))) return raw;
  } catch { /* invalid URL */ }
  return fallback;
}

// ─────────────────────────────────────────────────────────────────────────────
// DESIGN TOKENS & GLOBAL STYLES
// ─────────────────────────────────────────────────────────────────────────────
const GlobalStyles = () => (
  <style>{`
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --navy:      #091917;
      --navy-mid:  #102522;
      --navy-card: #142a27;
      --navy-border: #2a4540;
      --amber:     #dfbd89;
      --amber-lt:  #f3dcba;
      --amber-dk:  #b78b54;
      --white:     #f7f1e7;
      --muted:     #b3c2b9;
      --muted2:    #83988c;
      --success:   #75c6a2;
      --danger:    #ff8f83;
      --info:      #8dbce0;
      --font-serif: 'Cormorant Garamond', Georgia, serif;
      --font-sans:  'Plus Jakarta Sans', system-ui, sans-serif;
      --font-mono:  'Geist Mono', 'Courier New', monospace;
      --radius:     20px;
      --radius-sm:  12px;
      --shadow-sm:  0 3px 14px rgba(0,0,0,0.12);
      --shadow-md:  0 16px 42px rgba(0,0,0,0.22);
      --shadow-lg:  0 30px 80px rgba(0,0,0,0.38);
      --transition: 0.32s cubic-bezier(0.2,0.75,0.25,1);
    }

    html { scroll-behavior: smooth; }

    body {
      font-family: var(--font-sans);
      background: radial-gradient(circle at 50% -20%, #1b3730 0%, var(--navy) 38%);
      color: var(--white);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: var(--navy); }
    ::-webkit-scrollbar-thumb { background: var(--navy-border); border-radius: 3px; }

    /* Animations */
    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(24px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes slideInRight {
      from { transform: translateX(100%); }
      to   { transform: translateX(0); }
    }
    @keyframes slideInUp {
      from { transform: translateY(100%); opacity: 0; }
      to   { transform: translateY(0); opacity: 1; }
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.5; }
    }
    @keyframes shimmer {
      0%   { background-position: -200% 0; }
      100% { background-position:  200% 0; }
    }
    @keyframes badgePop {
      0%   { transform: scale(1); }
      50%  { transform: scale(1.4); }
      100% { transform: scale(1); }
    }

    .fade-in-up { animation: fadeInUp 0.5s ease both; }
    .fade-in-up-d1 { animation: fadeInUp 0.5s 0.1s ease both; }
    .fade-in-up-d2 { animation: fadeInUp 0.5s 0.2s ease both; }
    .fade-in-up-d3 { animation: fadeInUp 0.5s 0.3s ease both; }

    /* Skeleton shimmer */
    .skeleton {
      background: linear-gradient(90deg, var(--navy-card) 25%, var(--navy-border) 50%, var(--navy-card) 75%);
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
      border-radius: var(--radius-sm);
    }

    /* Utilities */
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    :focus-visible { outline: 2px solid var(--amber-lt) !important; outline-offset: 3px; }
    button, a, input, select, textarea { -webkit-tap-highlight-color: transparent; }
    button:not(:disabled), a { transition: transform var(--transition), box-shadow var(--transition), border-color var(--transition), background var(--transition); }
    button:not(:disabled):active { transform: scale(0.98); }
    .shop-header { background: rgba(9,25,23,.88) !important; backdrop-filter: blur(22px) !important; border-bottom-color: rgba(223,189,137,.16) !important; }
    .shop-header-inner { min-height: 76px; }
    .shop-mobile-toggle, .shop-mobile-menu { display: none; }
    .shop-hero { min-height: 610px !important; background: #102723 !important; border-color: rgba(223,189,137,.25) !important; isolation: isolate; perspective: 1200px; }
    .shop-hero-content { max-width: 55% !important; z-index: 2; }
    .shop-hero-photo { position: absolute; inset: -14px -14px -14px 49%; overflow: hidden; transform-style: preserve-3d; transform: translate3d(var(--hero-x, 0px),var(--hero-y, 0px),0) rotateX(var(--hero-rx, 0deg)) rotateY(var(--hero-ry, 0deg)) scale(1.035); transition: transform .55s cubic-bezier(.18,.72,.18,1); will-change: transform; }
    .shop-hero-photo-inner { position: absolute; inset: -18px; animation: heroDrift 10s ease-in-out infinite alternate; }
    .shop-hero-photo img { display: block; width: 100%; height: 100%; object-fit: cover; object-position: center 55%; }
    .shop-hero-photo::before { content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none; background: radial-gradient(circle at var(--hero-glint-x, 70%) var(--hero-glint-y, 35%), rgba(246,220,174,.13), transparent 42%); transition: background .3s ease; mix-blend-mode: screen; }
    .shop-hero-photo::after { content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none; background: linear-gradient(90deg, #102723 0%, rgba(16,39,35,.08) 45%, rgba(16,39,35,0) 100%); }
    .shop-hero-motion-hint { position: absolute; right: 30px; bottom: 28px; z-index: 2; display: inline-flex; align-items: center; gap: 9px; padding: 10px 13px; border: 1px solid rgba(246,220,174,.34); border-radius: 100px; background: rgba(9,25,23,.66); color: #f6dcae; font-size: 10px; font-weight: 800; letter-spacing: .16em; backdrop-filter: blur(12px); pointer-events: none; transition: opacity .3s ease, transform .3s ease; }
    .shop-hero-motion-hint::before { content: ''; width: 6px; height: 6px; border: 1px solid currentColor; border-radius: 50%; box-shadow: 0 0 0 3px rgba(246,220,174,.12); }
    .shop-motion-mobile { display: none; }
    .shop-hero:hover .shop-hero-motion-hint { opacity: 0; transform: translateY(6px); }
    @keyframes heroDrift { from { transform: translate3d(0,0,0) scale(1.015); } to { transform: translate3d(-7px,-9px,0) scale(1.055); } }
    .shop-hero-orbit, .shop-hero-depth-shadow, .shop-hero-float-chip { display: none; }
    .shop-hero-title { font-size: clamp(64px, 7vw, 104px) !important; line-height: .82 !important; letter-spacing: -.055em; }
    .shop-hero-title em { color: var(--amber-lt); }
    .shop-eyebrow { text-transform: uppercase; letter-spacing: .24em; color: var(--amber-lt); font-size: 11px; font-weight: 800; }
    .shop-section-title { font-size: clamp(38px, 4vw, 54px) !important; line-height: .95; letter-spacing: -.035em; }
    .shop-kicker { color: var(--amber); font-size: 11px; text-transform: uppercase; letter-spacing: .22em; font-weight: 800; margin-bottom: 10px; }
    .shop-category-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .shop-category-tile { min-height: 174px; position: relative; overflow: hidden; background: linear-gradient(140deg,#193630,#102622) !important; border: 1px solid rgba(223,189,137,.17) !important; border-radius: 18px !important; text-align: left !important; align-items: flex-start !important; justify-content: space-between !important; padding: 25px !important; }
    .shop-category-tile::after { content: ''; position: absolute; width: 140px; height: 140px; border: 1px solid rgba(223,189,137,.16); border-radius: 50%; right: -40px; bottom: -75px; transition: transform .6s ease; }
    .shop-category-tile:hover { transform: translateY(-5px); box-shadow: var(--shadow-md); border-color: var(--amber) !important; }
    .shop-category-tile:hover::after { transform: scale(1.2); }
    .shop-category-number { color: var(--amber); font: 600 11px var(--font-mono); letter-spacing: .12em; }
    .shop-product-card { border-color: rgba(223,189,137,.14) !important; transition: transform .45s cubic-bezier(.2,.8,.2,1), box-shadow .45s, border-color .45s !important; }
    .shop-product-card:hover { transform: translateY(-7px); box-shadow: var(--shadow-lg); border-color: rgba(223,189,137,.5) !important; }
    .shop-product-card img { transition: transform .7s cubic-bezier(.2,.8,.2,1); }
    .shop-product-card:hover img { transform: scale(1.055); }
    .shop-trust-card { background: transparent !important; border: 0 !important; border-top: 1px solid rgba(223,189,137,.35) !important; border-radius: 0 !important; text-align: left !important; padding: 26px 4px !important; }
    [data-reveal] { opacity: 0; transform: translateY(26px); transition: opacity .7s ease, transform .7s cubic-bezier(.2,.8,.2,1); }
    [data-reveal].is-visible { opacity: 1; transform: translateY(0); }
    [data-reveal]:nth-child(2) { transition-delay: .09s; }
    [data-reveal]:nth-child(3) { transition-delay: .18s; }
    [data-reveal]:nth-child(4) { transition-delay: .27s; }
    .shop-page { animation: fadeInUp .35s ease both; }
    .shop-filter-layout { display: flex; gap: 32px; }
    .shop-filter-aside { width: 240px; flex-shrink: 0; }
    .shop-product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 20px; }
    .shop-step-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
    .shop-product-detail { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 56px; align-items: start; }
    .shop-card-panel { background: linear-gradient(145deg, var(--navy-card), var(--navy-mid)) !important; border: 1px solid rgba(223,189,137,.18) !important; box-shadow: var(--shadow-sm); }
    .shop-order-card { transition: border-color var(--transition), transform var(--transition), box-shadow var(--transition); }
    .shop-order-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); }
    .shop-form-surface input, .shop-form-surface textarea, .shop-form-surface select { min-height: 44px; }
    @media (max-width: 900px) {
      .shop-hero { min-height: 580px !important; }
      .shop-hero-content { max-width: 62% !important; padding: 55px 40px !important; }
      .shop-category-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
      .shop-filter-layout { flex-direction: column; }
      .shop-filter-aside { width: 100%; }
      .shop-filter-aside > div { position: static !important; display: grid !important; grid-template-columns: repeat(2,minmax(0,1fr)); align-items: start; }
      .shop-product-detail { grid-template-columns: 1fr; gap: 28px; }
    }
    @media (max-width: 700px) {
      .shop-home { padding: 0 14px 80px !important; }
      .shop-home [data-reveal] { opacity: 1 !important; transform: none !important; }
      .shop-section-heading { align-items: flex-start !important; flex-wrap: wrap; gap: 12px; }
      .shop-section-heading .shop-section-title { font-size: clamp(32px, 9vw, 42px) !important; }
      .shop-header-inner { height: auto !important; min-height: 66px; flex-wrap: wrap; padding: 12px 16px !important; gap: 10px !important; }
      .shop-search { order: 3; flex-basis: 100%; max-width: none !important; }
      .shop-search input { height: 40px; }
      .shop-nav-links { display: none !important; }
      .shop-header-actions { gap: 5px !important; }
      .shop-header-actions > button { padding: 8px 10px !important; }
      .shop-desktop-auth, .shop-role-badge { display: none !important; }
      .shop-mobile-toggle { display: flex; align-items: center; justify-content: center; order: 2; width: 40px; height: 40px; background: var(--navy-card); border: 1px solid var(--navy-border); border-radius: 10px; color: var(--white); cursor: pointer; }
      .shop-mobile-menu { display: flex; flex-direction: column; gap: 3px; padding: 4px 16px 16px; background: var(--navy); border-top: 1px solid var(--navy-border); }
      .shop-mobile-menu button { min-height: 44px; padding: 10px 12px; text-align: left; border: 0; border-radius: 8px; background: transparent; color: var(--white); font: 600 14px var(--font-sans); cursor: pointer; }
      .shop-mobile-menu button:hover { background: var(--navy-card); color: var(--amber-lt); }
      .shop-hero { display: flex !important; flex-direction: column; min-height: 0 !important; margin: 18px 0 42px !important; perspective: 900px; }
      .shop-hero-content { max-width: 100% !important; width: 100%; padding: 22px 26px 34px !important; }
      .shop-hero-title { font-size: clamp(55px, 13vw, 76px) !important; margin: 18px 0 20px !important; }
      .shop-hero-photo { order: -1; position: relative; inset: auto; width: 100%; height: clamp(300px, 82vw, 390px); overflow: visible; transform: none !important; transform-style: flat; will-change: auto; touch-action: pan-y; background: radial-gradient(ellipse at 50% 55%, rgba(223,189,137,.24), transparent 58%), #102723; }
      .shop-hero-photo::before { inset: 16px; z-index: 3; border-radius: 24px; background: radial-gradient(circle at var(--hero-glint-x, 70%) var(--hero-glint-y, 35%), rgba(255,239,204,.25), transparent 36%); mix-blend-mode: screen; }
      .shop-hero-photo::after { inset: auto 0 0; height: 65px; z-index: 3; background: linear-gradient(0deg, #102723, transparent); }
      .shop-hero-photo-inner { inset: 25px 32px 34px; z-index: 2; overflow: hidden; border: 1px solid rgba(244,218,177,.44); border-radius: 22px; box-shadow: 0 22px 42px rgba(0,0,0,.35), inset 0 0 0 1px rgba(255,255,255,.1); animation: heroMobileFloat 7s ease-in-out infinite alternate; transform-origin: center center; }
      .shop-hero-photo-inner img { object-position: center 61%; animation: heroMobileZoom 10s ease-in-out infinite alternate; }
      .shop-hero-photo.is-interacting .shop-hero-photo-inner { animation: none; transform: translate3d(var(--hero-x, 0px), var(--hero-y, 0px), 0) rotateX(var(--hero-rx, 0deg)) rotateY(var(--hero-ry, 0deg)); transition: transform .18s ease-out; }
      .shop-hero-photo.is-interacting .shop-hero-photo-inner img { animation-play-state: paused; }
      .shop-hero-orbit { display: block; position: absolute; z-index: 1; left: 6%; right: 6%; top: 19%; bottom: 11%; border: 1px solid rgba(246,220,174,.4); border-radius: 50%; transform: rotate(-24deg); animation: heroOrbit 9s ease-in-out infinite alternate; pointer-events: none; }
      .shop-hero-orbit::after { content: ''; position: absolute; width: 9px; height: 9px; top: 12%; right: 12%; border-radius: 50%; background: #f6dcae; box-shadow: 0 0 0 7px rgba(246,220,174,.13), 0 0 24px rgba(246,220,174,.7); }
      .shop-hero-depth-shadow { display: block; position: absolute; z-index: 0; left: 17%; right: 17%; bottom: 8px; height: 26px; border-radius: 50%; background: rgba(0,0,0,.5); filter: blur(14px); animation: heroShadow 7s ease-in-out infinite alternate; }
      .shop-hero-float-chip { display: inline-flex; position: absolute; z-index: 4; right: 12px; top: 49px; padding: 10px 12px; border: 1px solid rgba(246,220,174,.55); border-radius: 100px; background: rgba(9,25,23,.84); box-shadow: 0 9px 24px rgba(0,0,0,.25); color: var(--amber-lt); font: 800 9px var(--font-sans); letter-spacing: .16em; animation: heroChipFloat 5s ease-in-out infinite alternate; pointer-events: none; }
      .shop-hero-motion-hint { display: inline-flex; right: 17px; bottom: 43px; z-index: 4; padding: 8px 10px; font-size: 9px; letter-spacing: .1em; }
      .shop-motion-desktop { display: none; }
      .shop-motion-mobile { display: inline; }
      .shop-hero:hover .shop-hero-motion-hint { opacity: 1; transform: none; }
      @keyframes heroMobileFloat { from { transform: translate3d(0,5px,0) rotateX(2deg) rotateY(-5deg) rotateZ(-1deg); } to { transform: translate3d(0,-8px,0) rotateX(-2deg) rotateY(5deg) rotateZ(1deg); } }
      @keyframes heroMobileZoom { from { transform: scale(1.08) translateX(-1%); } to { transform: scale(1.17) translateX(1%); } }
      @keyframes heroOrbit { from { transform: rotate(-25deg) scale(.98); opacity: .6; } to { transform: rotate(-19deg) scale(1.04); opacity: 1; } }
      @keyframes heroShadow { from { transform: scale(1.07); opacity: .7; } to { transform: scale(.86); opacity: .4; } }
      @keyframes heroChipFloat { from { transform: translateY(0); } to { transform: translateY(-8px); } }
      .shop-category-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; }
      .shop-category-tile { min-height: 150px; padding: 18px !important; }
      .shop-category-tile [data-category-name] { font-size: clamp(20px, 5.6vw, 26px) !important; overflow-wrap: anywhere; }
      .shop-trust-grid { grid-template-columns: repeat(2,minmax(0,1fr)) !important; }
      .shop-step-grid { grid-template-columns: 1fr; }
      .shop-filter-aside > div { grid-template-columns: 1fr; gap: 16px !important; }
      .shop-product-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; }
      .shop-product-card [data-product-copy] { padding: 12px !important; }
      .shop-collection-heading { flex-wrap: wrap; gap: 16px; }
      .shop-order-card { flex-wrap: wrap; gap: 15px; }
      .shop-admin-actions { flex-wrap: wrap; }
      .shop-admin-product-row { flex-wrap: wrap; }
      .shop-admin-product-row > div:nth-child(2) { min-width: 150px; }
    }
    @media (max-width: 420px) { .shop-product-grid { grid-template-columns: 1fr; } .shop-trust-grid { grid-template-columns: 1fr !important; } }
    @media (max-width: 360px) { .shop-category-grid { grid-template-columns: 1fr; } .shop-category-tile { min-height: 128px; } }
    @media (prefers-reduced-motion: reduce) {
      *,*::before,*::after { scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }
      .shop-hero-photo { transform: none !important; will-change: auto; }
      .shop-hero-photo-inner, .shop-hero-photo-inner img, .shop-hero-orbit, .shop-hero-depth-shadow, .shop-hero-float-chip { animation: none !important; transform: none !important; }
      .shop-hero-motion-hint { display: none; }
      [data-reveal] { opacity: 1 !important; transform: none !important; }
    }
  `}</style>
);

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT — implements the contract exactly
// ─────────────────────────────────────────────────────────────────────────────
//const API_BASE = "https://api.localhost.com/api/v1";
const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

let _accessToken = null;
let _refreshPromise = null;
let _authDispatch = null;

function setAccessToken(t) { _accessToken = t; }
function setAuthDispatch(d) { _authDispatch = d; }

function genRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto?.getRandomValues?.(bytes);
  return "req_" + Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
}

async function silentRefresh() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = apiFetch("/auth/refresh", { method: "POST", _skipAuth: true })
    .then(res => {
      if (res.success) {
        setAccessToken(res.data.access_token);
        if (_authDispatch) _authDispatch({ type: "TOKEN_REFRESHED", token: res.data.access_token });
      } else {
        if (_authDispatch) _authDispatch({ type: "LOGOUT" });
      }
      return res;
    })
    .finally(() => { _refreshPromise = null; });
  return _refreshPromise;
}

async function apiFetch(path, options = {}) {
  if (_refreshPromise) {
    await _refreshPromise;
  }

  //const { _skipAuth, body, method = "GET", ...rest } = options;
  const { _skipAuth, body, method = "GET", isFormData = false, headers: extraHeaders = {}, ...rest } = options;

  const headers = {
    "X-Request-ID": genRequestId(),
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...extraHeaders,
  };
  
  // 2. استخدم أحدث توكن موجود في الذاكرة بعد الانتظار
  if (!_skipAuth && _accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  }



  const config = {
    method,
    headers,
    credentials: "include",           // sends HttpOnly refresh cookie
    ...(body ? { body: isFormData ? body : JSON.stringify(body) } : {}),
    ...rest,
  };

  try {
    const res = await fetch(`${API_BASE}${path}`, config);
    const data = await res.json().catch(() => ({ success: false, error: { code: "PARSE_ERROR", message: "Invalid response" } }));
    if (!res.ok) {
      // FastAPI and SlowAPI may return either `error`, `detail.error`, or a
      // plain string. Normalize all of them so the UI never hides a useful
      // response behind the generic "Something went wrong" message.
      const rawError = data.error ?? data.detail?.error ?? data.detail;
      data.error = typeof rawError === "string"
        ? {
            code: res.status === 429 ? "RATE_LIMITED" : "REQUEST_FAILED",
            message: rawError,
          }
        : rawError || { code: "REQUEST_FAILED", message: "Request failed." };
    }

    // Silent token refresh on 401 TOKEN_EXPIRED
    if (res.status === 401 && data.error?.code === "TOKEN_EXPIRED" && !_skipAuth) {
      await silentRefresh();
      if (_accessToken) {
        return apiFetch(path, options);
      }
    }

    return data;
  } catch (err) {
    return { success: false, error: { code: "NETWORK_ERROR", message: "Network error. Please check your connection." } };
  }
}

async function apiDownload(path) {
  if (_refreshPromise) await _refreshPromise;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: {
        "X-Request-ID": genRequestId(),
        ...(_accessToken ? { Authorization: `Bearer ${_accessToken}` } : {}),
      },
    });
    if (response.status === 401 && attempt === 0) {
      await silentRefresh();
      if (_accessToken) continue;
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail?.message || data.error?.message || "Could not download the receipt.");
    }
    return response.blob();
  }
  throw new Error("Please sign in again to download your receipt.");
}

const api = {
  auth: {
    register:       (body)  => apiFetch("/auth/register",       { method: "POST", body }),
    login:          (body)  => apiFetch("/auth/login",          { method: "POST", body }),
    verifyLoginOtp: (body)  => apiFetch("/auth/verify-login-otp", { method: "POST", body }),
    verifyAccount: (body)   => apiFetch("/auth/verify", { method: "POST", body }),
    resendVerification: (body) => apiFetch("/auth/resend-verification", { method: "POST", body }),
    logout:         ()      => apiFetch("/auth/logout",         { method: "POST" }),
    refresh:        ()      => silentRefresh(),
    me:             ()      => apiFetch("/auth/me"),
    forgotPassword: (body)  => apiFetch("/auth/forgot-password",{ method: "POST", body }),
    resetPassword:  (body)  => apiFetch("/auth/reset-password", { method: "POST", body }),
  },
  products: {
    list:   (params = {}) => apiFetch("/products?" + new URLSearchParams(params)),
    get:    (id)          => apiFetch(`/products/${id}`),
    create: (body)        => apiFetch("/products",             { method: "POST", body }),
    update: (id, body)    => apiFetch(`/products/${id}`,       { method: "PATCH", body }),
    delete: (id)          => apiFetch(`/products/${id}`,       { method: "DELETE" }),
    uploadImage: (form)   => apiFetch("/products/images",      { method: "POST", body: form, isFormData: true }),
    manage: (params = {}) => apiFetch("/products/manage?" + new URLSearchParams(params)),
    reviews: {
      list:   (id, p) => apiFetch(`/products/${id}/reviews?` + new URLSearchParams(p)),
      create: (id, b) => apiFetch(`/products/${id}/reviews`,   { method: "POST", body: b }),
      update: (id, b) => apiFetch(`/products/${id}/reviews/me`, { method: "PATCH", body: b }),
      remove: (id) => apiFetch(`/products/${id}/reviews/me`, { method: "DELETE" }),
    },
  },
  categories: {
    list: () => apiFetch("/categories"),
  },
  cart: {
    get:        ()          => apiFetch("/cart"),
    addItem:    (body)      => apiFetch("/cart/items",              { method: "POST", body }),
    updateItem: (pid, body) => apiFetch(`/cart/items/${pid}`,       { method: "PATCH", body }),
    removeItem: (pid)       => apiFetch(`/cart/items/${pid}`,       { method: "DELETE" }),
    clear:      ()          => apiFetch("/cart",                    { method: "DELETE" }),
  },
  orders: {
    create: (body) => apiFetch("/orders",                           { method: "POST", body }),
    list:   (p)    => apiFetch("/orders?" + new URLSearchParams(p)),
    get:    (id)   => apiFetch(`/orders/${id}`),
    receipt: (id)  => apiDownload(`/orders/${id}/receipt`),
    vendorOrders: (p) => apiFetch("/vendor/orders?" + new URLSearchParams(p)),
    chat: {
      list: (id) => apiFetch(`/orders/${id}/chat`),
      send: (id, body) => apiFetch(`/orders/${id}/chat`, { method: "POST", body }),
    },
    coupons: {
      list: () => apiFetch("/coupons"),
      create: (body) => apiFetch("/coupons", { method: "POST", body }),
      disable: (id) => apiFetch(`/coupons/${id}`, { method: "DELETE" }),
    },
  },
  payments: {
    paymobStatus: () => apiFetch("/payments/paymob/status", { _skipAuth: true }),
    paymobCheckout: (body, idempotencyKey) => apiFetch("/payments/paymob/checkout", {
      method: "POST", body, headers: { "Idempotency-Key": idempotencyKey },
    }),
  },
  coupons: {
    validate: (body) => apiFetch("/coupons/validate", { method: "POST", body }),
  },
  wishlist: {
    list: () => apiFetch("/wishlist"),
    toggle: (productId) => apiFetch(`/wishlist/${productId}`, { method: "POST" }),
    remove: (productId) => apiFetch(`/wishlist/${productId}`, { method: "DELETE" }),
    status: (productId) => apiFetch(`/wishlist/${productId}/status`),
  },
  delivery: {
    verificationStatus: ()      => apiFetch("/delivery/verification/status"),
    submitDocs:         (form)  => apiFetch("/delivery/verification/submit", { method: "POST", body: form, isFormData: true }),
    orders:             ()      => apiFetch("/delivery/orders"),
    startDelivery:      (id)    => apiFetch(`/delivery/orders/${id}/start-delivery`, { method: "POST" }),
    verifyOtp:          (id, b) => apiFetch(`/delivery/orders/${id}/verify-otp`, { method: "POST", body: b }),
    uploadProof:        (id, f) => apiFetch(`/delivery/orders/${id}/proof`,      { method: "POST", body: f, isFormData: true }),
  },
  admin: {
    dashboard:       ()           => apiFetch("/admin/dashboard"),
    salesSummary:    (days = 14)  => apiFetch(`/admin/sales/summary?days=${days}`),
    users:           (p)          => apiFetch("/admin/users?" + new URLSearchParams(p)),
    approveProduct:  (id)         => apiFetch(`/admin/products/${id}/approve`, { method: "PATCH" }),
    rejectProduct:   (id, body)   => apiFetch(`/admin/products/${id}/reject`,  { method: "PATCH", body }),
    pendingProducts: (p)          => apiFetch("/admin/products/pending?" + new URLSearchParams(p || {})),
    agents:          (p)          => apiFetch("/admin/delivery-agents?" + new URLSearchParams(p)),
    approveAgent:    (id)         => apiFetch(`/admin/delivery-agents/${id}/approve`, { method: "PATCH" }),
    rejectAgent:     (id, body)   => apiFetch(`/admin/delivery-agents/${id}/reject`,  { method: "PATCH", body }),
    auditLogs:       (p)          => apiFetch("/admin/audit-logs?" + new URLSearchParams(p)),
    orders:          (p)          => apiFetch("/admin/orders?" + new URLSearchParams(p)),
    registerPushDevice: (token)  => apiFetch("/admin/push-devices", { method: "POST", body: { token } }),
    removePushDevice:   (token)  => apiFetch("/admin/push-devices", { method: "DELETE", body: { token } }),
    whatsappContacted: (id)      => apiFetch(`/admin/orders/${id}/whatsapp-contacted`, { method: "POST" }),
    deliverOrder:   (id)         => apiFetch(`/admin/orders/${id}/deliver`, { method: "POST", body: { payment_received: true } }),
    assignDelivery:  (id, body)   => apiFetch(`/admin/orders/${id}/assign`, { method: "POST", body }),
    cancelOrder:     (id)         => apiFetch(`/admin/orders/${id}/cancel`, { method: "POST" }),
    chat: {
      list: (id) => apiFetch(`/admin/orders/${id}/chat`),
      send: (id, body) => apiFetch(`/admin/orders/${id}/chat`, { method: "POST", body }),
    },
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// STATE — Auth + Cart + UI via useReducer
// ─────────────────────────────────────────────────────────────────────────────
const AppContext = createContext(null);

const INITIAL_STATE = {
  auth: {
    accessToken: null,
    user: null,
    isAuthenticated: false,
    isLoading: true,
  },
  cart: {
    items: [],
    summary: { item_count: 0, subtotal: 0, tax_estimate: 0, total: 0 },
    warnings: [],
    isLoading: false,
  },
  ui: {
    cartOpen: false,
    authModal: null,   // null | 'login' | 'register'
    toast: null,
    page: "home",      // home | products | product | cart | orders | wishlist | checkout | orderSuccess | delivery | admin
    pageParams: {},
  },
};

function reducer(state, action) {
  switch (action.type) {
    case "AUTH_LOADED":
      return {
        ...state,
        auth: {
          accessToken: action.token,
          user: action.user,
          isAuthenticated: !!action.user,
          isLoading: false,
        },
      };
    case "TOKEN_REFRESHED":
      setAccessToken(action.token);
      return { ...state, auth: { ...state.auth, accessToken: action.token } };
    case "LOGOUT":
      setAccessToken(null);
      return {
        ...state,
        auth: { accessToken: null, user: null, isAuthenticated: false, isLoading: false },
        cart: INITIAL_STATE.cart,
      };
    case "CART_LOADED":
      return { ...state, cart: { ...state.cart, ...action.cart, isLoading: false } };
    case "CART_LOADING":
      return { ...state, cart: { ...state.cart, isLoading: true } };
    case "CART_OPEN":  return { ...state, ui: { ...state.ui, cartOpen: true } };
    case "CART_CLOSE": return { ...state, ui: { ...state.ui, cartOpen: false } };
    case "AUTH_MODAL": return { ...state, ui: { ...state.ui, authModal: action.mode } };
    case "NAVIGATE":
      return { ...state, ui: { ...state.ui, page: action.page, pageParams: action.params || {}, cartOpen: false, authModal: null } };
    case "TOAST":
      return { ...state, ui: { ...state.ui, toast: action.toast } };
    case "TOAST_CLEAR":
      return { ...state, ui: { ...state.ui, toast: null } };
    default:
      return state;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MOCK DATA for demo (used when API is not live)
// ─────────────────────────────────────────────────────────────────────────────
// Mock data removed — all data is fetched live from the API.

// ─────────────────────────────────────────────────────────────────────────────
// SHARED UI COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function Btn({ children, variant = "primary", size = "md", onClick, disabled, type = "button", style: s, full }) {
  const base = {
    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "8px",
    border: "none", cursor: disabled ? "not-allowed" : "pointer",
    fontFamily: "var(--font-sans)", fontWeight: 700, letterSpacing: "0.01em",
    transition: "all var(--transition)", borderRadius: "var(--radius-sm)",
    opacity: disabled ? 0.5 : 1, width: full ? "100%" : undefined,
    whiteSpace: "nowrap",
  };
  const sizes = {
    sm: { padding: "6px 14px", fontSize: "13px" },
    md: { padding: "10px 22px", fontSize: "14px" },
    lg: { padding: "14px 28px", fontSize: "15px" },
    xl: { padding: "16px 36px", fontSize: "16px" },
  };
  const variants = {
    primary:   { background: "var(--amber)", color: "#12221d", boxShadow: "0 7px 22px rgba(223,189,137,.18)" },
    secondary: { background: "var(--navy-card)", color: "var(--white)", border: "1px solid var(--navy-border)" },
    ghost:     { background: "transparent", color: "var(--muted)", border: "1px solid var(--navy-border)" },
    danger:    { background: "var(--danger)", color: "#fff" },
    success:   { background: "var(--success)", color: "#fff" },
    outline:   { background: "transparent", color: "var(--amber)", border: "2px solid var(--amber)" },
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      style={{ ...base, ...sizes[size], ...variants[variant], ...s }}
      onMouseEnter={e => { if (!disabled) { e.currentTarget.style.filter = "brightness(1.07)"; e.currentTarget.style.transform = "translateY(-2px)"; } }}
      onMouseLeave={e => { e.currentTarget.style.filter = "none"; e.currentTarget.style.transform = "none"; }}>
      {children}
    </button>
  );
}

function Spinner({ size = 20, color = "var(--amber)" }) {
  return (
    <div style={{
      width: size, height: size, border: `2px solid transparent`,
      borderTopColor: color, borderRadius: "50%",
      animation: "spin 0.7s linear infinite", flexShrink: 0,
    }} />
  );
}

function Badge({ children, color = "var(--amber)", bg }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px",
      borderRadius: "100px", fontSize: "11px", fontWeight: 700, letterSpacing: "0.04em",
      textTransform: "uppercase", color, background: bg || color + "22",
    }}>
      {children}
    </span>
  );
}

function StarRating({ rating, count }) {
  const stars = Math.round(rating);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
      <div style={{ display: "flex", gap: "1px" }}>
        {[1,2,3,4,5].map(i => (
          <svg key={i} width="13" height="13" viewBox="0 0 24 24" fill={i <= stars ? "var(--amber)" : "var(--navy-border)"}>
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
        ))}
      </div>
      <span style={{ fontSize: "12px", color: "var(--muted)" }}>({count})</span>
    </div>
  );
}

function Input({ label, type = "text", value, onChange, placeholder, error, required, name, disabled, inputMode, autoComplete }) {
  const id = useId();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {label && (
        <label htmlFor={id} style={{ fontSize: "13px", fontWeight: 600, color: "var(--muted)" }}>
          {label} {required && <span style={{ color: "var(--amber)" }}>*</span>}
        </label>
      )}
      <input
        id={id} type={type} name={name} value={value} onChange={onChange} disabled={disabled} inputMode={inputMode} autoComplete={autoComplete}
        placeholder={placeholder} required={required}
        style={{
          background: "var(--navy-card)", border: `1px solid ${error ? "var(--danger)" : "var(--navy-border)"}`,
          borderRadius: "var(--radius-sm)", padding: "10px 14px", color: "var(--white)",
          fontFamily: "var(--font-sans)", fontSize: "14px", outline: "none", width: "100%",
          transition: "border-color var(--transition)",
        }}
        onFocus={e => { e.target.style.borderColor = "var(--amber)"; }}
        onBlur={e => { e.target.style.borderColor = error ? "var(--danger)" : "var(--navy-border)"; }}
      />
      {error && <span style={{ fontSize: "12px", color: "var(--danger)" }}>{error}</span>}
    </div>
  );
}

function Select({ label, value, onChange, options, name }) {
  const id = useId();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {label && <label htmlFor={id} style={{ fontSize: "13px", fontWeight: 600, color: "var(--muted)" }}>{label}</label>}
      <select id={id} name={name} value={value} onChange={onChange} style={{
        background: "var(--navy-card)", border: "1px solid var(--navy-border)",
        borderRadius: "var(--radius-sm)", padding: "10px 14px", color: "var(--white)",
        fontFamily: "var(--font-sans)", fontSize: "14px", outline: "none", width: "100%", cursor: "pointer",
      }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function Toast({ toast, onClear }) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onClear, 4000);
    return () => clearTimeout(t);
  }, [toast, onClear]);

  if (!toast) return null;
  const colors = { success: "var(--success)", error: "var(--danger)", info: "var(--info)", warning: "var(--amber)" };
  const icons  = { success: "✓", error: "✕", info: "ℹ", warning: "⚠" };

  return (
    <div style={{
      position: "fixed", bottom: "24px", right: "24px", zIndex: 9999,
      background: "var(--navy-card)", border: `1px solid ${colors[toast.type] || "var(--navy-border)"}`,
      borderLeft: `4px solid ${colors[toast.type] || "var(--amber)"}`,
      borderRadius: "var(--radius)", padding: "14px 18px", maxWidth: "380px",
      display: "flex", alignItems: "flex-start", gap: "12px",
      boxShadow: "var(--shadow-lg)", animation: "slideInUp 0.3s ease",
    }}>
      <span style={{ color: colors[toast.type], fontSize: "16px", fontWeight: 700, lineHeight: 1 }}>
        {icons[toast.type] || "•"}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        {toast.title && <div style={{ fontWeight: 700, fontSize: "14px", marginBottom: "2px" }}>{toast.title}</div>}
        <div style={{ fontSize: "13px", color: "var(--muted)" }}>{toast.message}</div>
      </div>
      <button onClick={onClear} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: "16px", lineHeight: 1 }}>✕</button>
    </div>
  );
}

function Modal({ isOpen, onClose, title, children, width = "480px" }) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);
  if (!isOpen) return null;
  return (
    <div role="presentation" style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center",
      padding: "20px", backdropFilter: "blur(4px)",
    }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title || "Account"} style={{
        background: "var(--navy-card)", borderRadius: "var(--radius)", border: "1px solid var(--navy-border)",
        width: "100%", maxWidth: width, maxHeight: "90vh", overflow: "auto",
        boxShadow: "var(--shadow-lg)", animation: "fadeInUp 0.25s ease",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "20px 24px 0" }}>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: "22px" }}>{title}</h2>
          <button aria-label="Close dialog" onClick={onClose} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: "20px", lineHeight: 1 }}>✕</button>
        </div>
        <div style={{ padding: "20px 24px 24px" }}>{children}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// NAVBAR
// ─────────────────────────────────────────────────────────────────────────────
function Navbar({ state, dispatch, onLogout }) {
  const { auth, cart, ui } = state;
  const [scrolled, setScrolled] = useState(false);
  const [search, setSearch] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const cartCount = cart.items.reduce((acc, i) => acc + i.qty, 0);

  const navigate = (page, params) => dispatch({ type: "NAVIGATE", page, params });
  const openAccount = () => {
    const role = auth.user?.role;
    if (role === "admin") navigate("admin");
    else if (role === "delivery") window.location.href = auth.user?.verification_status === "approved" ? "/delivery/dashboard" : "/verification";
    else navigate("orders");
  };
  const mobileNavigate = (page, params) => { setMobileMenuOpen(false); navigate(page, params); };

  const roleColors = { admin: "var(--danger)", vendor: "var(--info)", delivery: "var(--success)", customer: "var(--amber)" };
  const roleBg     = { admin: "#ef444422", vendor: "#3b82f622", delivery: "#10b98122", customer: "#f59e0b22" };

  return (
    <header className="shop-header" style={{
      position: "sticky", top: 0, zIndex: 900,
      background: scrolled ? "rgba(10,15,30,0.95)" : "var(--navy)",
      borderBottom: "1px solid var(--navy-border)",
      backdropFilter: scrolled ? "blur(12px)" : "none",
      transition: "all var(--transition)",
    }}>
      <div className="shop-header-inner" style={{ maxWidth: "1280px", margin: "0 auto", padding: "0 24px", display: "flex", alignItems: "center", height: "76px", gap: "16px" }}>
        {/* Logo */}
        <button aria-label="Shoply home" onClick={() => mobileNavigate("home")} style={{ background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
          <div style={{
            width: "32px", height: "32px", borderRadius: "8px",
            background: "var(--amber)", display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0a0f1e" strokeWidth="2.5">
              <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/>
              <path d="M16 10a4 4 0 01-8 0"/>
            </svg>
          </div>
          <span style={{ fontFamily: "var(--font-serif)", fontSize: "20px", color: "var(--white)", letterSpacing: "-0.02em" }}>
            Shoply
          </span>
        </button>

        {/* Search */}
        <div className="shop-search" style={{ flex: 1, maxWidth: "410px", position: "relative" }}>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search products..."
            onKeyDown={e => { if (e.key === "Enter" && search.trim()) mobileNavigate("products", { q: search }); }}
            style={{
              width: "100%", background: "var(--navy-card)", border: "1px solid var(--navy-border)",
              borderRadius: "100px", padding: "8px 16px 8px 40px", color: "var(--white)",
              fontFamily: "var(--font-sans)", fontSize: "14px", outline: "none",
              transition: "border-color var(--transition)",
            }}
            onFocus={e => { e.target.style.borderColor = "var(--amber)"; }}
            onBlur={e => { e.target.style.borderColor = "var(--navy-border)"; }}
          />
          <svg style={{ position: "absolute", left: "14px", top: "50%", transform: "translateY(-50%)" }} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
          </svg>
        </div>

        {/* Nav links */}
        <nav className="shop-nav-links" style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          <button onClick={() => navigate("products")} style={{
            background: "none", border: "none", color: "var(--muted)", cursor: "pointer",
            padding: "6px 12px", borderRadius: "var(--radius-sm)", fontSize: "14px", fontWeight: 500,
            transition: "all var(--transition)", fontFamily: "var(--font-sans)",
          }}
            onMouseEnter={e => { e.target.style.color = "var(--white)"; e.target.style.background = "var(--navy-card)"; }}
            onMouseLeave={e => { e.target.style.color = "var(--muted)"; e.target.style.background = "none"; }}>
            Shop
          </button>
        </nav>

        <div className="shop-header-actions" style={{ display: "flex", gap: "8px", alignItems: "center", marginLeft: "auto" }}>
          {/* Role badge */}
          {auth.isAuthenticated && auth.user && (
            <span className="shop-role-badge"><Badge color={roleColors[auth.user.role]} bg={roleBg[auth.user.role]}>
              {auth.user.role}
            </Badge></span>
          )}

          {/* Cart button */}
          <button onClick={() => dispatch({ type: "CART_OPEN" })} style={{
            position: "relative", background: "var(--navy-card)", border: "1px solid var(--navy-border)",
            borderRadius: "var(--radius-sm)", padding: "8px 12px", cursor: "pointer", color: "var(--white)",
            display: "flex", alignItems: "center", gap: "6px", transition: "all var(--transition)",
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--amber)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--navy-border)"; }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/>
              <path d="M16 10a4 4 0 01-8 0"/>
            </svg>
            <span style={{ fontSize: "13px", fontWeight: 600 }}>Cart</span>
            {cartCount > 0 && (
              <span style={{
                position: "absolute", top: "-6px", right: "-6px",
                background: "var(--amber)", color: "#0a0f1e",
                borderRadius: "50%", width: "18px", height: "18px",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "10px", fontWeight: 800, animation: "badgePop 0.3s ease",
              }}>
                {cartCount}
              </span>
            )}
          </button>

          {/* Auth */}
          {auth.isAuthenticated ? (
            <div className="shop-desktop-auth" style={{ position: "relative" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                {auth.user?.role === "customer" && <button type="button" onClick={() => navigate("wishlist")} aria-label="Saved items" style={{ background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius-sm)", padding: "7px 10px", cursor: "pointer", color: "var(--amber)", fontSize: 20, lineHeight: 1 }}>♡</button>}
                <button style={{
                  background: "var(--navy-card)", border: "1px solid var(--navy-border)",
                  borderRadius: "var(--radius-sm)", padding: "6px 12px", cursor: "pointer",
                  color: "var(--white)", display: "flex", alignItems: "center", gap: "8px",
                  fontFamily: "var(--font-sans)", fontSize: "13px", fontWeight: 600,
                }}
                  onClick={openAccount}>
                  <div style={{
                    width: "26px", height: "26px", borderRadius: "50%", background: "var(--amber)",
                    display: "flex", alignItems: "center", justifyContent: "center", color: "#0a0f1e",
                    fontSize: "11px", fontWeight: 800,
                  }}>
                    {auth.user?.name?.charAt(0)?.toUpperCase() || "U"}
                  </div>
                  <span className="truncate" style={{ maxWidth: "80px" }}>{auth.user?.name?.split(" ")[0]}</span>
                </button>
                <Btn variant="ghost" size="sm" onClick={onLogout}>Log out</Btn>
              </div>
            </div>
          ) : (
            <div className="shop-desktop-auth" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Btn variant="ghost" size="sm" onClick={() => dispatch({ type: "AUTH_MODAL", mode: "login" })}>Sign in</Btn>
              <Btn size="sm" onClick={() => dispatch({ type: "AUTH_MODAL", mode: "register" })}>Register</Btn>
            </div>
          )}
        </div>
        <button className="shop-mobile-toggle" aria-label="Open menu" aria-expanded={mobileMenuOpen} onClick={() => setMobileMenuOpen(open => !open)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d={mobileMenuOpen ? "M5 5l14 14M19 5L5 19" : "M4 7h16M4 12h16M4 17h16"}/></svg>
        </button>
      </div>
      {mobileMenuOpen && <nav className="shop-mobile-menu" aria-label="Mobile navigation">
        <button onClick={() => mobileNavigate("products")}>Shop collection</button>
        {auth.isAuthenticated ? <>
          <button onClick={() => { setMobileMenuOpen(false); openAccount(); }}>{auth.user?.role === "admin" ? "Admin dashboard" : auth.user?.role === "delivery" ? "Delivery dashboard" : "My orders"}</button>
          {auth.user?.role === "customer" && <button onClick={() => mobileNavigate("wishlist")}>Saved items</button>}
          <button onClick={() => { setMobileMenuOpen(false); onLogout(); }}>Log out</button>
        </> : <>
          <button onClick={() => { setMobileMenuOpen(false); dispatch({ type: "AUTH_MODAL", mode: "login" }); }}>Sign in</button>
          <button onClick={() => { setMobileMenuOpen(false); dispatch({ type: "AUTH_MODAL", mode: "register" }); }}>Create account</button>
        </>}
      </nav>}
    </header>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AUTH MODAL — Login + Register tabs
// ─────────────────────────────────────────────────────────────────────────────
function AuthModal({ state, dispatch }) {
  const reduxDispatch = useReduxDispatch();
  const { ui } = state;
  const [mode, setMode] = useState(ui.authModal || "login");
  const [loginOtpStep, setLoginOtpStep] = useState(false);
  const [challengeId, setChallengeId] = useState("");
  const [otp, setOtp] = useState("");
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "customer" });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [forgotMode, setForgotMode] = useState(false);

  useEffect(() => {
    setMode(ui.authModal || "login");
    setLoginOtpStep(false);
    setChallengeId("");
    setOtp("");
    setErrors({});
    setServerError("");
    setSuccessMessage("");
    setForgotMode(false);
  }, [ui.authModal]);

  const updateForm = (k, v) => setForm(p => ({ ...p, [k]: v }));
  const close = () => dispatch({ type: "AUTH_MODAL", mode: null });

  const validateIdentity = () => {
    const e = {};
    if (mode === "register" && form.name.trim().length < 2) e.name = "Name must be at least 2 characters";
    if (!form.email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) e.email = "Invalid email format";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const finishLogin = (res) => {
    if (!res.success) {
      setServerError(res.error?.message || "Something went wrong. Please try again.");
      return false;
    }
    if (res.data?.mfa_required) {
      setLoginOtpStep(true);
      setChallengeId(res.data.challenge_id);
      setOtp("");
      setSuccessMessage("A sign-in code was sent to your email. Enter it to continue.");
      return false;
    }
    const { access_token, user } = res.data;
    setAccessToken(access_token);
    // Keep the Redux session used by /admin/monitoring in sync with the storefront.
    reduxDispatch(sessionEstablished({ accessToken: access_token, user }));
    dispatch({ type: "AUTH_LOADED", token: access_token, user });
    dispatch({ type: "TOAST", toast: { type: "success", title: `Welcome back, ${user.name.split(" ")[0]}!`, message: "You are now signed in." } });
    close();
    if (user.role === "delivery") {
      window.location.href = user.verification_status === "approved" ? "/delivery/dashboard" : "/verification";
    } else if (user.role === "admin") {
      dispatch({ type: "NAVIGATE", page: "admin" });
    }
    return true;
  };

  const handlePasswordSubmit = async () => {
    const identityErrors = {};
    if (!form.email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) identityErrors.email = "Invalid email format";
    if (mode === "register" && form.name.trim().length < 2) identityErrors.name = "Name must be at least 2 characters";
    if (mode === "register" && !getPasswordFeedback(form.password).ready) identityErrors.password = getPasswordFeedback(form.password).message;
    if (mode === "login" && !form.password) identityErrors.password = "Enter your password";
    if (form.password.length > 72) identityErrors.password = "Password must be at most 72 characters";
    setErrors(identityErrors);
    if (Object.keys(identityErrors).length) return;
    setLoading(true); setServerError(""); setSuccessMessage("");
    try {
      let res = mode === "login"
        ? await api.auth.login({ email: form.email, password: form.password })
        : await api.auth.register({ name: form.name, email: form.email, password: form.password });
      if (mode === "register" && res.success) {
        setMode("login");
        setSuccessMessage("Account created. Open the verification link in your email, then sign in with your email and password.");
        setForm(p => ({ ...p, password: "" }));
        return;
      }
      if (!res.success && res.error?.code === "EMAIL_NOT_VERIFIED") {
        setServerError("Verify your email before signing in. Open the link we sent or request a new one below.");
        return;
      }
      finishLogin(res);
    } finally {
      setLoading(false);
    }
  };

  const handleLoginOtp = async () => {
    if (!/^\d{6}$/.test(otp)) {
      setServerError("Enter the 6-digit code sent to your email.");
      return;
    }
    setLoading(true); setServerError("");
    try {
      const res = await api.auth.verifyLoginOtp({ challenge_id: challengeId, otp });
      finishLogin(res);
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setLoginOtpStep(false);
    setChallengeId("");
    setOtp("");
    setErrors({});
    setServerError("");
    setSuccessMessage("");
    setForgotMode(false);
  };

  const requestReset = async () => {
    if (!form.email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) { setErrors({ email: "Invalid email format" }); return; }
    setLoading(true); setServerError("");
    const res = await api.auth.forgotPassword({ email: form.email });
    setLoading(false);
    if (res.success) setSuccessMessage("If this email has an account, a reset link was sent. Check your inbox and spam folder.");
    else setServerError(res.error?.message || "Could not request a reset link.");
  };

  return (
    <Modal isOpen={!!ui.authModal} onClose={close} title="">
      {!forgotMode && !loginOtpStep && <div style={{ display: "flex", gap: "0", marginBottom: "24px", borderBottom: "1px solid var(--navy-border)" }}>
        {["login", "register"].map(m => (
          <button key={m} onClick={() => switchMode(m)} style={{
            flex: 1, padding: "10px", background: "none", border: "none",
            borderBottom: mode === m ? "2px solid var(--amber)" : "2px solid transparent",
            color: mode === m ? "var(--white)" : "var(--muted)",
            fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: "14px", cursor: "pointer",
            textTransform: "capitalize", transition: "all var(--transition)",
          }}>
            {m === "login" ? "Sign In" : "Create Account"}
          </button>
        ))}
      </div>}

      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {!forgotMode && !loginOtpStep && mode === "register" && (
          <Input label="Full Name" value={form.name} onChange={e => updateForm("name", e.target.value)} placeholder="Jane Smith" error={errors.name} required />
        )}
        {!forgotMode && !loginOtpStep && <Input label="Email" type="email" value={form.email} onChange={e => updateForm("email", e.target.value)} placeholder="you@example.com" error={errors.email} required />}

        {!forgotMode && loginOtpStep && <>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 24, margin: 0 }}>Check your email</h2>
          <p style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.5 }}>Enter the 6-digit code sent to {form.email}. It expires in 5 minutes.</p>
          <Input label="Sign-in code" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="123456" inputMode="numeric" autoComplete="one-time-code" />
          <Btn full size="lg" onClick={handleLoginOtp} disabled={loading || otp.length !== 6}>{loading ? <Spinner size={18} color="#0a0f1e" /> : "Verify and sign in"}</Btn>
          <button onClick={() => { setLoginOtpStep(false); setChallengeId(""); setOtp(""); setServerError(""); setSuccessMessage(""); }} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 13, cursor: "pointer", textDecoration: "underline" }}>Start over</button>
        </>}

        {forgotMode && <>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 24, margin: 0 }}>Reset your password</h2>
          <p style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.5 }}>We will email you a secure reset link.</p>
          <Input label="Email" type="email" value={form.email} onChange={e => updateForm("email", e.target.value)} placeholder="you@example.com" error={errors.email} required />
          <Btn full size="lg" onClick={requestReset} disabled={loading}>{loading ? "Sending…" : "Send reset link"}</Btn>
          <button onClick={() => setForgotMode(false)} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 13, cursor: "pointer", textDecoration: "underline" }}>Back to sign in</button>
        </>}

        {!forgotMode && !loginOtpStep && (
          <>
            {mode === "login" && <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>Enter your email and password. We will then send a one-time code to your verified email.</p>}
            {mode === "register" && <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>We will email you a verification link. Open it before signing in.</p>}
            <Input label="Password" type="password" value={form.password} onChange={e => { updateForm("password", e.target.value); setErrors(previous => ({ ...previous, password: "" })); }} placeholder={mode === "login" ? "Your password" : "Create a strong password"} autoComplete={mode === "login" ? "current-password" : "new-password"} error={errors.password} required />
            {mode === "register" && <PasswordStrength password={form.password} />}
            <Btn full size="lg" onClick={handlePasswordSubmit} disabled={loading}>
              {loading ? <Spinner size={18} color="#0a0f1e" /> : (mode === "login" ? "Continue" : "Create Account")}
            </Btn>
            {mode === "login" && <button onClick={() => { setForgotMode(true); setServerError(""); setSuccessMessage(""); }} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: "13px", cursor: "pointer", textDecoration: "underline" }}>Forgot password?</button>}
            {mode === "login" && <button onClick={async () => { if (!validateIdentity()) return; const res = await api.auth.resendVerification({ email: form.email }); setSuccessMessage(res.success ? "If your account needs verification, a new link has been sent." : (res.error?.message || "Please try again later.")); }} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: "13px", cursor: "pointer", textDecoration: "underline" }}>
              Need a new verification link?
            </button>}
          </>
        )}

        {serverError && (
          <div style={{ background: "#ef444411", border: "1px solid var(--danger)", borderRadius: "var(--radius-sm)", padding: "10px 14px", fontSize: "13px", color: "var(--danger)" }}>
            {serverError}
          </div>
        )}
        {successMessage && <div style={{ background: "#1d8a641c", border: "1px solid var(--success)", borderRadius: "var(--radius-sm)", padding: "10px 14px", fontSize: 13, color: "var(--success)" }}>{successMessage}</div>}

        <p style={{ fontSize: "12px", color: "var(--muted)", textAlign: "center" }}>
          By continuing you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CART DRAWER
// ─────────────────────────────────────────────────────────────────────────────
function CartDrawer({ state, dispatch }) {
  const { cart, ui, auth } = state;
  useEffect(() => {
    if (!ui.cartOpen) return undefined;
    const onKeyDown = e => { if (e.key === "Escape") dispatch({ type: "CART_CLOSE" }); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [ui.cartOpen, dispatch]);
  if (!ui.cartOpen) return null;

  const removeItem = async (pid) => {
    dispatch({ type: "CART_LOADING" });
    const res = await api.cart.removeItem(pid);
    if (res.success) dispatch({ type: "CART_LOADED", cart: res.data });
    else dispatch({ type: "TOAST", toast: { type: "error", title: "Cart error", message: res.error?.message || "Could not remove item." } });
  };

  const proceedToCheckout = () => {
    if (!auth.isAuthenticated) { dispatch({ type: "AUTH_MODAL", mode: "login" }); return; }
    dispatch({ type: "NAVIGATE", page: "checkout" });
  };

  return (
    <>
      <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 998, backdropFilter: "blur(2px)" }}
        onClick={() => dispatch({ type: "CART_CLOSE" })} />
      <div role="dialog" aria-modal="true" aria-label="Your cart" style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: "100%", maxWidth: "420px",
        background: "var(--navy-card)", borderLeft: "1px solid var(--navy-border)",
        zIndex: 999, display: "flex", flexDirection: "column",
        animation: "slideInRight 0.3s cubic-bezier(0.4,0,0.2,1)",
        boxShadow: "var(--shadow-lg)",
      }}>
        {/* Header */}
        <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--navy-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: "22px" }}>
            Your Cart
            {cart.items.length > 0 && (
              <span style={{ marginLeft: "8px", fontSize: "14px", color: "var(--muted)", fontFamily: "var(--font-sans)", fontWeight: 400 }}>
                ({cart.items.reduce((a, i) => a + i.qty, 0)} items)
              </span>
            )}
          </h2>
          <button aria-label="Close cart" onClick={() => dispatch({ type: "CART_CLOSE" })} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: "22px" }}>✕</button>
        </div>

        {/* Items */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 24px" }}>
          {cart.isLoading && (
            <div style={{ display: "flex", justifyContent: "center", padding: "40px" }}>
              <Spinner />
            </div>
          )}
          {!cart.isLoading && cart.items.length === 0 && (
            <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--muted)" }}>
              <svg aria-hidden="true" width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--amber)" strokeWidth="1.5" style={{ marginBottom: 16 }}><path d="M8 16h32l-3 24H11L8 16Z"/><path d="M17 18v-5a7 7 0 0 1 14 0v5"/><path d="M17 25h14"/></svg>
              <div style={{ fontFamily: "var(--font-serif)", fontSize: "22px", color: "var(--white)", marginBottom: "8px" }}>Your cart is empty</div>
              <div style={{ fontSize: "14px", marginBottom: "24px" }}>Add some products to get started</div>
              <Btn onClick={() => dispatch({ type: "NAVIGATE", page: "products" })}>Browse Products</Btn>
            </div>
          )}
          {!cart.isLoading && cart.items.map(item => (
            <div key={item.product_id + item.variant_id} style={{
              display: "flex", gap: "14px", padding: "16px 0",
              borderBottom: "1px solid var(--navy-border)",
            }}>
              <div style={{ width: "64px", height: "64px", borderRadius: "var(--radius-sm)", overflow: "hidden", flexShrink: 0 }}>
                {item.image ? (
                  <img src={safeImageSource(item.image)} alt={item.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  <div style={{ width: "100%", height: "100%", background: "var(--navy-border)" }} />
                )}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: "14px", marginBottom: "2px" }} className="truncate">{item.name}</div>
                {item.variant_label && <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "6px" }}>{item.variant_label}</div>}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "15px", color: "var(--amber)", fontWeight: 600 }}>
                    {formatMoney(item.unit_price * item.qty)}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "13px", color: "var(--muted)" }}>Qty: {item.qty}</span>
                    <button onClick={() => removeItem(item.product_id)} style={{
                      background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: "14px",
                      padding: "2px 6px", borderRadius: "4px",
                    }}
                      onMouseEnter={e => { e.target.style.color = "var(--danger)"; }}
                      onMouseLeave={e => { e.target.style.color = "var(--muted)"; }}>
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {cart.warnings?.map((w, i) => (
            <div key={i} style={{ background: "#f59e0b11", border: "1px solid #f59e0b44", borderRadius: "var(--radius-sm)", padding: "10px 12px", marginTop: "12px", fontSize: "12px", color: "var(--amber)" }}>
              ⚠ {w.message}
            </div>
          ))}
        </div>

        {/* Summary */}
        {cart.items.length > 0 && (
          <div style={{ padding: "20px 24px", borderTop: "1px solid var(--navy-border)" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "16px" }}>
              {[
                ["Subtotal", formatMoney(cart.summary.subtotal)],
                ...(Number(cart.summary.tax_estimate || 0) > 0 ? [["Tax", formatMoney(cart.summary.tax_estimate)]] : []),
                ["Delivery", "Confirmed on WhatsApp"],
              ].map(([k, v]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: "13px" }}>
                  <span style={{ color: "var(--muted)" }}>{k}</span>
                  <span style={{ fontFamily: k === "Delivery" ? "var(--font-sans)" : "var(--font-mono)" }}>{v}</span>
                </div>
              ))}
              <div style={{ borderTop: "1px solid var(--navy-border)", paddingTop: "8px", display: "flex", justifyContent: "space-between", fontWeight: 700, fontSize: "16px" }}>
                <span>Total</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--amber)" }}>{formatMoney(cart.summary.total)}</span>
              </div>
            </div>
            <Btn full size="lg" onClick={proceedToCheckout}>
              Proceed to Checkout →
            </Btn>
          </div>
        )}
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PRODUCT CARD
// ─────────────────────────────────────────────────────────────────────────────
function WishlistButton({ productId, state, dispatch, compact = false }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    if (!state.auth.isAuthenticated || state.auth.user?.role !== "customer") {
      setSaved(false);
      return () => { active = false; };
    }
    api.wishlist.status(productId).then(res => {
      if (active && res.success) setSaved(Boolean(res.data?.in_wishlist));
    });
    return () => { active = false; };
  }, [productId, state.auth.isAuthenticated, state.auth.user?.role]);

  const toggle = async event => {
    event.stopPropagation();
    if (!state.auth.isAuthenticated) {
      dispatch({ type: "AUTH_MODAL", mode: "login" });
      return;
    }
    if (state.auth.user?.role !== "customer" || busy) return;
    setBusy(true);
    const res = await api.wishlist.toggle(productId);
    setBusy(false);
    if (res.success) {
      setSaved(res.data?.action === "added" || res.data?.action === "already");
      dispatch({ type: "TOAST", toast: { type: "success", title: res.data?.action === "removed" ? "Removed from wishlist" : "Saved to wishlist", message: "You can find it in your saved items." } });
    }
  };

  return <button type="button" aria-label={saved ? "Remove from wishlist" : "Add to wishlist"} aria-pressed={saved} onClick={toggle} disabled={busy}
    style={{ width: compact ? 34 : 38, height: compact ? 34 : 38, borderRadius: "50%", border: "1px solid var(--navy-border)", background: saved ? "#dfbd8930" : "var(--navy-card)", color: saved ? "var(--amber)" : "var(--muted)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: compact ? 18 : 20, opacity: busy ? .55 : 1 }}>
    {saved ? "♥" : "♡"}
  </button>;
}

function ProductCard({ product, state, dispatch, onAddToCart }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);

  const handleAdd = async (e) => {
    e.stopPropagation();
    if (!product.in_stock) return;
    setAdding(true);
    await onAddToCart(product.id, null, 1);
    setAdding(false);
    setAdded(true);
    setTimeout(() => setAdded(false), 1500);
  };

  return (
    <div className="shop-product-card" style={{
      background: "var(--navy-card)", borderRadius: "var(--radius)",
      border: "1px solid var(--navy-border)", overflow: "hidden",
      cursor: "pointer", transition: "all var(--transition)",
      display: "flex", flexDirection: "column",
    }}
      role="link" tabIndex={0} aria-label={`View ${product.name}`}
      onClick={() => dispatch({ type: "NAVIGATE", page: "product", params: { id: product.id } })}
      onKeyDown={e => { if (e.key === "Enter") dispatch({ type: "NAVIGATE", page: "product", params: { id: product.id } }); }}>
      {/* Image */}
      <div style={{ position: "relative", paddingTop: "72%", overflow: "hidden", background: "var(--navy-mid)" }}>
        {safeImageSource(product.images?.[0]) ? (
          <img src={safeImageSource(product.images[0])} alt={product.name} loading="lazy" decoding="async" style={{
            position: "absolute", inset: 0, width: "100%", height: "100%",
            objectFit: "cover", transition: "transform 0.4s ease",
          }} />
        ) : (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)" }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
              <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
            </svg>
          </div>
        )}
        {product.discount_percent > 0 && (
          <div style={{
            position: "absolute", top: "12px", left: "12px",
            background: "var(--danger)", color: "#fff", borderRadius: "6px",
            padding: "2px 8px", fontSize: "11px", fontWeight: 800,
          }}>
            -{product.discount_percent}%
          </div>
        )}
        <div style={{ position: "absolute", top: 12, right: 12 }}><WishlistButton productId={product.id} state={state} dispatch={dispatch} compact /></div>
        {!product.in_stock && (
          <div style={{
            position: "absolute", inset: 0, background: "rgba(10,15,30,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Badge color="var(--muted)" bg="var(--navy-mid)">Out of Stock</Badge>
          </div>
        )}
      </div>

      {/* Content */}
      <div data-product-copy style={{ padding: "20px", flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "4px" }}>
          {product.category?.name}
        </div>
        <h3 style={{ fontFamily: "var(--font-serif)", fontSize: "25px", fontWeight: 600, lineHeight: 1.1, marginBottom: "11px" }} className="truncate">
          {product.name}
        </h3>
        <StarRating rating={product.ratings.average} count={product.ratings.count} />

        <div style={{ marginTop: "auto", paddingTop: "12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "18px", fontWeight: 700, color: "var(--amber)" }}>
              {formatMoney(product.final_price)}
            </span>
            {product.discount_percent > 0 && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "13px", color: "var(--muted)", textDecoration: "line-through", marginLeft: "6px" }}>
                {formatMoney(product.price)}
              </span>
            )}
          </div>
          <button aria-label={`Add ${product.name} to cart`} onClick={handleAdd} disabled={!product.in_stock || adding}
            style={{
              width: "36px", height: "36px", borderRadius: "50%", border: "none",
              background: added ? "var(--success)" : "var(--amber)", cursor: product.in_stock ? "pointer" : "not-allowed",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all var(--transition)", flexShrink: 0,
              opacity: product.in_stock ? 1 : 0.4,
            }}>
            {adding ? <Spinner size={16} color="#0a0f1e" /> : added ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0a0f1e" strokeWidth="2.5">
                <path d="M12 5v14M5 12h14"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// HOME PAGE
// ─────────────────────────────────────────────────────────────────────────────
function HomePage({ state, dispatch, onAddToCart }) {
  const [products, setProducts]   = useState([]);
  const [categories, setCategories] = useState([]);
  const [loadingHome, setLoadingHome] = useState(true);
  const heroPhotoRef = useRef(null);
  const heroFrameRef = useRef(0);
  const heroTouchStartRef = useRef(null);

  useEffect(() => () => window.cancelAnimationFrame(heroFrameRef.current), []);

  const startHeroTouch = event => {
    if (event.pointerType === "touch") heroTouchStartRef.current = { x: event.clientX, y: event.clientY };
  };

  const moveHero = event => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const photo = heroPhotoRef.current;
    if (!photo) return;
    let x;
    let y;
    if (event.pointerType === "touch" && window.innerWidth <= 700 && heroTouchStartRef.current) {
      x = Math.max(-1, Math.min(1, (event.clientX - heroTouchStartRef.current.x) / 70));
      y = Math.max(-1, Math.min(1, (event.clientY - heroTouchStartRef.current.y) / 90));
      if (Math.abs(x) < .1 && Math.abs(y) < .1) return;
      photo.classList.add("is-interacting");
    } else if (event.pointerType === "mouse" && window.innerWidth > 700) {
      const bounds = event.currentTarget.getBoundingClientRect();
      x = Math.max(-1, Math.min(1, ((event.clientX - bounds.left) / bounds.width - .5) * 2));
      y = Math.max(-1, Math.min(1, ((event.clientY - bounds.top) / bounds.height - .5) * 2));
    } else return;
    window.cancelAnimationFrame(heroFrameRef.current);
    heroFrameRef.current = window.requestAnimationFrame(() => {
      photo.style.setProperty("--hero-x", `${x * 9}px`);
      photo.style.setProperty("--hero-y", `${y * 7}px`);
      photo.style.setProperty("--hero-rx", `${-y * 5}deg`);
      photo.style.setProperty("--hero-ry", `${x * 8}deg`);
      photo.style.setProperty("--hero-glint-x", `${70 + x * 17}%`);
      photo.style.setProperty("--hero-glint-y", `${35 + y * 17}%`);
    });
  };

  const resetHero = () => {
    window.cancelAnimationFrame(heroFrameRef.current);
    heroTouchStartRef.current = null;
    const photo = heroPhotoRef.current;
    if (!photo) return;
    photo.classList.remove("is-interacting");
    for (const key of ["--hero-x", "--hero-y", "--hero-rx", "--hero-ry", "--hero-glint-x", "--hero-glint-y"]) photo.style.removeProperty(key);
  };

  useEffect(() => {
    const load = async () => {
      setLoadingHome(true);
      const [prodRes, catRes] = await Promise.all([
        state.auth.isAuthenticated ? api.products.list({ limit: 24, sort: "-created_at" }) : Promise.resolve({ success: true, data: [] }),
        api.categories.list(),
      ]);
      if (prodRes.success) {
        const available = prodRes.data || [];
        const seenCategories = new Set();
        const varied = available.filter(product => {
          if (seenCategories.has(product.category_id)) return false;
          seenCategories.add(product.category_id);
          return true;
        });
        setProducts([...varied, ...available.filter(product => !varied.includes(product))].slice(0, 4));
      }
      if (catRes.success)  setCategories(catRes.data || []);
      setLoadingHome(false);
    };
    load();
  }, [state.auth.isAuthenticated]);

  return (
    <main className="shop-home" style={{ maxWidth: "1280px", margin: "0 auto", padding: "0 24px 80px" }}>
      {/* Hero */}
      <section className="shop-hero" style={{
        position: "relative", borderRadius: "var(--radius)", overflow: "hidden",
        background: "var(--navy-mid)",
        border: "1px solid var(--navy-border)", margin: "28px 0 72px",
        minHeight: "610px", display: "flex", alignItems: "center",
      }}>
        <div className="shop-hero-content" style={{ position: "relative", padding: "60px 70px", maxWidth: "680px" }}>
          <div className="shop-eyebrow fade-in-up">THE SHOPLY EDIT · 2026</div>
          <h1 className="shop-hero-title fade-in-up-d1" style={{
            fontFamily: "var(--font-serif)", fontSize: "clamp(64px, 7vw, 104px)",
            lineHeight: .9, margin: "30px 0 25px", fontWeight: 600,
          }}>
            Everyday,<br /><em>beautifully</em><br />considered.
          </h1>
          <p className="fade-in-up-d2" style={{ color: "var(--muted)", fontSize: "16px", lineHeight: 1.75, marginBottom: "34px", maxWidth: "405px" }}>
            Thoughtful finds for the spaces you make and the moments you keep. Explore the collection, then confirm your order directly with us.
          </p>
          <div className="fade-in-up-d3" style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <Btn size="lg" onClick={() => state.auth.isAuthenticated ? dispatch({ type: "NAVIGATE", page: "products" }) : dispatch({ type: "AUTH_MODAL", mode: "login" })} style={{ borderRadius: 100, padding: "16px 26px" }}>
              {state.auth.isAuthenticated ? "Explore the collection ↗" : "Sign in to explore ↗"}
            </Btn>
            {!state.auth.isAuthenticated && <Btn variant="outline" size="lg" style={{ borderRadius: 100, borderWidth: 1 }} onClick={() => dispatch({ type: "AUTH_MODAL", mode: "register" })}>Create account</Btn>}
          </div>
          <div className="fade-in-up-d3" style={{ borderTop: "1px solid rgba(223,189,137,.3)", marginTop: 55, paddingTop: 16, maxWidth: 430, color: "var(--muted)", fontSize: 12, letterSpacing: ".03em" }}>CURATED BY THE STORE · ORDER VIA WHATSAPP</div>
        </div>
        <div className="shop-hero-photo" ref={heroPhotoRef} onPointerDown={startHeroTouch} onPointerMove={moveHero} onPointerLeave={resetHero} onPointerUp={resetHero} aria-hidden="true">
          <span className="shop-hero-orbit" />
          <span className="shop-hero-depth-shadow" />
          <div className="shop-hero-photo-inner">
            <img src="/shoply-editorial-hero.webp" alt="" width="1024" height="1536" fetchPriority="high" />
          </div>
          <span className="shop-hero-float-chip">THE SHOPLY EDIT</span>
          <span className="shop-hero-motion-hint"><span className="shop-motion-desktop">SCROLL TO EXPLORE</span><span className="shop-motion-mobile">SWIPE TO EXPLORE</span></span>
        </div>
      </section>

      {/* Categories */}
      <section style={{ marginBottom: "72px" }} data-reveal>
        <div className="shop-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "24px" }}>
          <div><div className="shop-kicker">EXPLORE BY INTEREST</div><h2 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: "42px" }}>Find your kind of good.</h2></div>
          <button onClick={() => dispatch({ type: "NAVIGATE", page: "products" })} style={{ background: "none", border: "none", color: "var(--amber)", cursor: "pointer", fontSize: "14px", fontWeight: 600, fontFamily: "var(--font-sans)" }}>
            View all →
          </button>
        </div>
        <div className="shop-category-grid">
          {loadingHome && categories.length === 0 && [...Array(3)].map((_, i) => <div key={i} className="skeleton" style={{ minHeight: 174, borderRadius: 18 }} />)}
          {categories.map((cat, i) => (
            <button key={cat.id} className="shop-category-tile" onClick={() => dispatch({ type: "NAVIGATE", page: "products", params: { category: cat.id, categoryName: cat.name } })}
              style={{
                background: "var(--navy-card)", border: "1px solid var(--navy-border)",
                borderRadius: "var(--radius)", padding: "20px 16px",
                cursor: "pointer", textAlign: "center", transition: "all var(--transition)",
                display: "flex", flexDirection: "column", alignItems: "center", gap: "10px",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--amber)"; e.currentTarget.style.background = "#1a2236"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--navy-border)"; e.currentTarget.style.background = "var(--navy-card)"; }}>
              <span className="shop-category-number">0{i + 1} / COLLECTION</span>
              <div>
                <div data-category-name style={{ fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: "30px", color: "var(--white)", marginBottom: "2px", lineHeight: 1 }}>{cat.name} <span style={{ fontFamily: "var(--font-sans)", fontSize: 17, color: "var(--amber)" }}>↗</span></div>
                {typeof cat.count === "number" && <div style={{ fontSize: "12px", color: "var(--muted)" }}>{cat.count} items</div>}
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Featured Products */}
      <section data-reveal>
        <div className="shop-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "24px" }}>
          <div><div className="shop-kicker">FRESHLY SELECTED</div><h2 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: "42px" }}>The latest finds.</h2></div>
          <button onClick={() => state.auth.isAuthenticated ? dispatch({ type: "NAVIGATE", page: "products" }) : dispatch({ type: "AUTH_MODAL", mode: "login" })} style={{ background: "none", border: "none", color: "var(--amber)", cursor: "pointer", fontSize: "14px", fontWeight: 600, fontFamily: "var(--font-sans)" }}>
            See all →
          </button>
        </div>
        {state.auth.isAuthenticated ? <div className="shop-product-grid">
          {loadingHome && [...Array(4)].map((_, i) => <div key={i} className="skeleton" style={{ minHeight: 290, borderRadius: 18 }} />)}
          {products.map((p, i) => (
            <div key={p.id} style={{ animation: `fadeInUp 0.5s ${i * 0.08}s ease both` }}>
              <ProductCard product={p} state={state} dispatch={dispatch} onAddToCart={onAddToCart} />
            </div>
          ))}
        </div> : <div className="shop-card-panel" style={{ borderRadius: 18, padding: "28px 24px", color: "var(--muted)", lineHeight: 1.7 }}>
          Sign in to discover the latest products selected by Shoply.
          <div style={{ marginTop: 18 }}><Btn onClick={() => dispatch({ type: "AUTH_MODAL", mode: "login" })}>Sign in to explore ↗</Btn></div>
        </div>}
      </section>

      {/* Trust strip */}
      <section className="shop-trust-grid" data-reveal style={{ marginTop: "78px", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "28px" }}>
        {[
          { number: "01", title: "Chosen with care", desc: "Every product is added by the Shoply team." },
          { number: "02", title: "A simple order", desc: "Save what you love and request it in a few steps." },
          { number: "03", title: "A personal follow-up", desc: "We confirm the details with you directly on WhatsApp." },
        ].map(item => (
          <div key={item.title} className="shop-trust-card" style={{
            background: "var(--navy-card)", borderRadius: "var(--radius)",
            border: "1px solid var(--navy-border)", padding: "24px", textAlign: "center",
          }}>
            <div style={{ font: "600 12px var(--font-mono)", color: "var(--amber)", marginBottom: 17 }}>{item.number} / SHOPLY</div>
            <div style={{ fontFamily: "var(--font-serif)", fontSize: "29px", fontWeight: 600, marginBottom: "9px" }}>{item.title}</div>
            <div style={{ fontSize: "13px", color: "var(--muted)", lineHeight: 1.7 }}>{item.desc}</div>
          </div>
        ))}
      </section>
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PRODUCTS PAGE
// ─────────────────────────────────────────────────────────────────────────────
function ProductsPage({ state, dispatch, onAddToCart }) {
  const { ui } = state;
  const [products, setProducts]   = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading]     = useState(false);
  const [filters, setFilters]     = useState({
    q: ui.pageParams?.q || "",
    category: ui.pageParams?.category || "",
    min_price: "", max_price: "", sort: "-created_at", in_stock: false,
  });
  const [page, setPage]   = useState(1);
  const [meta, setMeta]   = useState({ total: 0, total_pages: 1 });

  const updateFilter = (k, v) => setFilters(p => ({ ...p, [k]: v }));

  // Load categories once
  useEffect(() => {
    api.categories.list().then(r => { if (r.success) setCategories(r.data || []); });
  }, []);

  // Load products on filter / page change
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const params = { page, limit: 8, sort: filters.sort };
      if (filters.q)         params.q         = filters.q;
      if (filters.category)  params.category   = filters.category;
      if (filters.min_price) params.min_price  = filters.min_price;
      if (filters.max_price) params.max_price  = filters.max_price;
      if (filters.in_stock)  params.in_stock   = true;
      const res = await api.products.list(params);
      if (res.success) {
        setProducts(res.data || []);
        setMeta(res.meta || { total: 0, total_pages: 1 });
      } else {
        setProducts([]);
        setMeta({ total: 0, total_pages: 1 });
      }
      setLoading(false);
    };
    load();
  }, [filters, page]);

  const sortOptions = [
    { value: "-created_at", label: "Newest" },
    { value: "price", label: "Price: Low to High" },
    { value: "-price", label: "Price: High to Low" },
    { value: "-ratings.average", label: "Top Rated" },
  ];

  return (
    <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "42px 24px 80px" }}>
      <div className="shop-filter-layout">
        {/* Sidebar Filters */}
        <aside className="shop-filter-aside">
          <div style={{ position: "sticky", top: "88px", display: "flex", flexDirection: "column", gap: "24px" }}>
            <div>
              <h3 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--muted)", marginBottom: "12px" }}>Search</h3>
              <input value={filters.q} onChange={e => updateFilter("q", e.target.value)}
                placeholder="Search products..."
                style={{
                  width: "100%", background: "var(--navy-card)", border: "1px solid var(--navy-border)",
                  borderRadius: "var(--radius-sm)", padding: "8px 12px", color: "var(--white)",
                  fontFamily: "var(--font-sans)", fontSize: "13px", outline: "none",
                }} />
            </div>

            <div>
              <h3 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--muted)", marginBottom: "12px" }}>Category</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <button onClick={() => updateFilter("category", "")} style={{
                  background: !filters.category ? "var(--amber)" : "none", border: "1px solid " + (!filters.category ? "var(--amber)" : "var(--navy-border)"),
                  borderRadius: "var(--radius-sm)", padding: "7px 12px", cursor: "pointer", textAlign: "left",
                  color: !filters.category ? "#0a0f1e" : "var(--white)", fontSize: "13px", fontWeight: 500,
                  fontFamily: "var(--font-sans)", transition: "all var(--transition)",
                }}>
                  All Categories
                </button>
                {categories.map(cat => (
                  <button key={cat.id} onClick={() => updateFilter("category", cat.id)} style={{
                    background: filters.category === cat.id ? "var(--amber)" : "none",
                    border: "1px solid " + (filters.category === cat.id ? "var(--amber)" : "var(--navy-border)"),
                    borderRadius: "var(--radius-sm)", padding: "7px 12px", cursor: "pointer", textAlign: "left",
                    color: filters.category === cat.id ? "#0a0f1e" : "var(--white)", fontSize: "13px", fontWeight: 500,
                    fontFamily: "var(--font-sans)", transition: "all var(--transition)",
                  }}>
                    {cat.name}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <h3 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--muted)", marginBottom: "12px" }}>Price Range</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                {[["min_price", "Min EGP"], ["max_price", "Max EGP"]].map(([k, ph]) => (
                  <input key={k} type="number" value={filters[k]} onChange={e => updateFilter(k, e.target.value)}
                    placeholder={ph} min="0"
                    style={{
                      background: "var(--navy-card)", border: "1px solid var(--navy-border)",
                      borderRadius: "var(--radius-sm)", padding: "8px 10px", color: "var(--white)",
                      fontFamily: "var(--font-mono)", fontSize: "13px", outline: "none", width: "100%",
                    }} />
                ))}
              </div>
            </div>

            <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", fontSize: "14px", fontWeight: 500 }}>
              <input type="checkbox" checked={filters.in_stock} onChange={e => updateFilter("in_stock", e.target.checked)}
                style={{ width: "16px", height: "16px", accentColor: "var(--amber)", cursor: "pointer" }} />
              In Stock Only
            </label>
          </div>
        </aside>

        {/* Product Grid */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="shop-collection-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "26px" }}>
            <div>
              <div className="shop-kicker">THE SHOPLY COLLECTION</div>
              <h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: "50px", marginBottom: "8px" }}>
                {filters.category ? categories.find(c => c.id === filters.category)?.name || "Products" : "All Products"}
              </h1>
              <p style={{ color: "var(--muted)", fontSize: "14px" }}>{meta.total} products found</p>
            </div>
            <select value={filters.sort} onChange={e => updateFilter("sort", e.target.value)} style={{
              background: "var(--navy-card)", border: "1px solid var(--navy-border)",
              borderRadius: "var(--radius-sm)", padding: "8px 12px", color: "var(--white)",
              fontFamily: "var(--font-sans)", fontSize: "13px", cursor: "pointer", outline: "none",
            }}>
              {sortOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          {loading ? (
            <div className="shop-product-grid">
              {[...Array(8)].map((_, i) => (
                <div key={i} style={{ borderRadius: "var(--radius)", overflow: "hidden" }}>
                  <div className="skeleton" style={{ paddingTop: "72%" }} />
                  <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
                    <div className="skeleton" style={{ height: "14px", width: "60%" }} />
                    <div className="skeleton" style={{ height: "18px", width: "85%" }} />
                    <div className="skeleton" style={{ height: "12px", width: "40%" }} />
                  </div>
                </div>
              ))}
            </div>
          ) : products.length === 0 ? (
            <div style={{ textAlign: "center", padding: "80px 20px", color: "var(--muted)" }}>
              <svg aria-hidden="true" width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--amber)" strokeWidth="1.5" style={{ marginBottom: 16 }}><circle cx="21" cy="21" r="13"/><path d="m31 31 10 10"/></svg>
              <div style={{ fontFamily: "var(--font-serif)", fontSize: "24px", color: "var(--white)", marginBottom: "8px" }}>No products found</div>
              <div style={{ marginBottom: "24px" }}>Try adjusting your filters</div>
              <Btn onClick={() => setFilters({ q: "", category: "", min_price: "", max_price: "", sort: "-created_at", in_stock: false })}>Clear Filters</Btn>
            </div>
          ) : (
            <div className="shop-product-grid">
              {products.map((p, i) => (
                <div key={p.id} style={{ animation: `fadeInUp 0.4s ${i * 0.05}s ease both` }}>
                  <ProductCard product={p} state={state} dispatch={dispatch} onAddToCart={onAddToCart} />
                </div>
              ))}
            </div>
          )}

          {meta.total_pages > 1 && (
            <div style={{ display: "flex", justifyContent: "center", gap: "8px", marginTop: "40px" }}>
              {[...Array(meta.total_pages)].map((_, i) => (
                <button key={i} onClick={() => setPage(i + 1)} style={{
                  width: "36px", height: "36px", borderRadius: "var(--radius-sm)",
                  background: page === i + 1 ? "var(--amber)" : "var(--navy-card)",
                  border: `1px solid ${page === i + 1 ? "var(--amber)" : "var(--navy-border)"}`,
                  color: page === i + 1 ? "#0a0f1e" : "var(--white)",
                  cursor: "pointer", fontWeight: 600, fontSize: "14px", fontFamily: "var(--font-sans)",
                }}>
                  {i + 1}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PRODUCT DETAIL PAGE
// ─────────────────────────────────────────────────────────────────────────────
function ProductReviews({ productId, state, dispatch }) {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(5);
  const [body, setBody] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    const res = await api.products.reviews.list(productId, { page: 1, limit: 20 });
    if (res.success) setReviews(res.data || []);
    else setMessage(res.error?.message || "Could not load reviews.");
    setLoading(false);
  };

  useEffect(() => { load(); }, [productId]);

  const submit = async event => {
    event.preventDefault();
    if (!state.auth.isAuthenticated) {
      dispatch({ type: "AUTH_MODAL", mode: "login" });
      return;
    }
    const reviewBody = body.trim();
    if (reviewBody.length < 10) { setMessage("Please write at least 10 characters for your review."); return; }
    setSaving(true); setMessage("");
    const res = await api.products.reviews.create(productId, { rating, body: reviewBody });
    setSaving(false);
    if (!res.success) { setMessage(res.error?.message || "Could not save your review."); return; }
    setBody("");
    setMessage("Your review was added.");
    load();
  };

  return <section style={{ marginTop: 56, paddingTop: 34, borderTop: "1px solid var(--navy-border)" }}>
    <div className="shop-section-heading" style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "end", marginBottom: 20 }}>
      <div><div className="shop-kicker">CUSTOMER NOTES</div><h2 style={{ fontFamily: "var(--font-serif)", fontSize: 34, marginTop: 7 }}>Reviews</h2></div>
      <span style={{ color: "var(--muted)", fontSize: 13 }}>{reviews.length} review{reviews.length === 1 ? "" : "s"}</span>
    </div>
    {loading ? <Spinner /> : reviews.length === 0 ? <p style={{ color: "var(--muted)", fontSize: 14 }}>Be the first to share your experience.</p> : <div style={{ display: "grid", gap: 12, marginBottom: 24 }}>
      {reviews.map(review => <article key={review.id} className="shop-card-panel" style={{ padding: 18, borderRadius: "var(--radius-sm)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 8 }}><span style={{ color: "var(--amber)", letterSpacing: 2 }}>{"★".repeat(Math.max(0, Math.min(5, Number(review.rating))))}{"☆".repeat(5 - Math.max(0, Math.min(5, Number(review.rating))))}</span><time style={{ color: "var(--muted2)", fontSize: 11 }}>{review.created_at ? new Date(review.created_at).toLocaleDateString("en-EG") : ""}</time></div>
        <p style={{ color: "var(--muted)", lineHeight: 1.6, fontSize: 14 }}>{review.body}</p>
      </article>)}
    </div>}
    {state.auth.user?.role === "customer" && <form onSubmit={submit} className="shop-card-panel shop-form-surface" style={{ padding: 20, borderRadius: "var(--radius-sm)" }}>
      <h3 style={{ fontSize: 16, marginBottom: 12 }}>Share your experience</h3>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }} aria-label="Rating">
        {[1, 2, 3, 4, 5].map(value => <button key={value} type="button" aria-label={`${value} star${value === 1 ? "" : "s"}`} aria-pressed={rating === value} onClick={() => setRating(value)} style={{ border: 0, background: "none", color: value <= rating ? "var(--amber)" : "var(--muted2)", fontSize: 24, cursor: "pointer", padding: 0 }}>★</button>)}
      </div>
      <textarea value={body} onChange={event => setBody(event.target.value)} maxLength={1000} rows={3} placeholder="What did you think?" style={{ width: "100%", resize: "vertical", borderRadius: 10, border: "1px solid var(--navy-border)", background: "var(--navy-mid)", color: "var(--white)", padding: 12, fontFamily: "inherit" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 10 }}><Btn size="sm" type="submit" disabled={saving}>{saving ? "Saving..." : "Post review"}</Btn>{message && <span role="status" style={{ color: message.includes("added") ? "var(--success)" : "var(--muted)", fontSize: 12 }}>{message}</span>}</div>
    </form>}
  </section>;
}

function ProductDetailPage({ state, dispatch, onAddToCart }) {
  const { ui } = state;
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [qty, setQty] = useState(1);
  const [adding, setAdding] = useState(false);
  const [imgIdx, setImgIdx] = useState(0);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const res = await api.products.get(ui.pageParams?.id);
      if (res.success) {
        setProduct(res.data);
        setSelectedVariant(res.data.variants?.[0] || null);
      } else {
        // Product not found in API — leave as null (shows "not found" UI)
        setProduct(null);
      }
      setLoading(false);
    };
    load();
  }, [ui.pageParams?.id]);

  const handleAdd = async () => {
    setAdding(true);
    await onAddToCart(product.id, selectedVariant?.id, qty);
    setAdding(false);
    dispatch({ type: "CART_OPEN" });
  };

  if (loading) return (
    <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "40px 24px" }}>
      <div className="shop-product-detail">
        <div className="skeleton" style={{ paddingTop: "100%", borderRadius: "var(--radius)" }} />
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {[80, 50, 30, 60, 40].map((w, i) => <div key={i} className="skeleton" style={{ height: "16px", width: `${w}%` }} />)}
        </div>
      </div>
    </main>
  );

  if (!product) return (
    <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "80px 24px", textAlign: "center" }}>
      <div style={{ fontFamily: "var(--font-serif)", fontSize: "28px", marginBottom: "16px" }}>Product not found</div>
      <Btn onClick={() => dispatch({ type: "NAVIGATE", page: "products" })}>← Back to Products</Btn>
    </main>
  );

  const images = product.images?.map(image => safeImageSource(image)).filter(Boolean).length
    ? product.images.map(image => safeImageSource(image)).filter(Boolean)
    : ["https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&q=80"];

  return (
    <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "32px 24px 80px" }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "32px", fontSize: "13px" }}>
        {[["Home", "home"], ["Products", "products"], [product.name]].map(([label, page], i, arr) => (
          <span key={label} style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {page ? (
              <button onClick={() => dispatch({ type: "NAVIGATE", page })} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: "13px" }}
                onMouseEnter={e => { e.target.style.color = "var(--amber)"; }}
                onMouseLeave={e => { e.target.style.color = "var(--muted)"; }}>
                {label}
              </button>
            ) : (
              <span className="truncate" style={{ color: "var(--white)", maxWidth: "200px" }}>{label}</span>
            )}
            {i < arr.length - 1 && <span style={{ color: "var(--muted2)" }}>›</span>}
          </span>
        ))}
      </div>

      <div className="shop-product-detail">
        {/* Image gallery */}
        <div>
          <div style={{ borderRadius: "var(--radius)", overflow: "hidden", background: "var(--navy-card)", border: "1px solid var(--navy-border)", aspectRatio: "1", marginBottom: "12px" }}>
            <img src={safeImageSource(images[imgIdx])} alt={product.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
          {images.length > 1 && (
            <div style={{ display: "flex", gap: "8px" }}>
              {images.map((img, i) => (
                <button key={i} onClick={() => setImgIdx(i)} style={{
                  width: "64px", height: "64px", borderRadius: "var(--radius-sm)", overflow: "hidden",
                  border: `2px solid ${i === imgIdx ? "var(--amber)" : "var(--navy-border)"}`,
                  cursor: "pointer", padding: 0, background: "var(--navy-card)", transition: "border-color var(--transition)",
                }}>
                  <img src={safeImageSource(img)} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Product info */}
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <div>
            <div style={{ display: "flex", gap: "8px", marginBottom: "10px", flexWrap: "wrap" }}>
              <Badge color="var(--info)">{product.category?.name}</Badge>
              {product.in_stock ? <Badge color="var(--success)">In Stock</Badge> : <Badge color="var(--danger)">Out of Stock</Badge>}
              {product.discount_percent > 0 && <Badge color="var(--danger)">-{product.discount_percent}% OFF</Badge>}
              <WishlistButton productId={product.id} state={state} dispatch={dispatch} />
            </div>
            <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "clamp(24px,3vw,36px)", lineHeight: 1.2, marginBottom: "12px" }}>{product.name}</h1>
            <StarRating rating={product.ratings?.average || 4.5} count={product.ratings?.count || 0} />
          </div>

          <div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "36px", fontWeight: 700, color: "var(--amber)" }}>
              {formatMoney(product.final_price || product.price)}
            </span>
            {product.discount_percent > 0 && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "20px", color: "var(--muted)", textDecoration: "line-through", marginLeft: "12px" }}>
                {formatMoney(product.price)}
              </span>
            )}
          </div>

          {product.description && (
            <p style={{ color: "var(--muted)", fontSize: "15px", lineHeight: 1.7 }}>{product.description}</p>
          )}

          {/* Variants */}
          {product.variants && product.variants.length > 0 && (
            <div>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "10px" }}>
                {product.variants[0].color ? "Color" : "Variant"}
              </div>
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                {product.variants.map(v => (
                  <button key={v.id} onClick={() => setSelectedVariant(v)} style={{
                    padding: "8px 16px", borderRadius: "var(--radius-sm)",
                    border: `2px solid ${selectedVariant?.id === v.id ? "var(--amber)" : "var(--navy-border)"}`,
                    background: selectedVariant?.id === v.id ? "var(--amber)" : "var(--navy-card)",
                    color: selectedVariant?.id === v.id ? "#0a0f1e" : "var(--white)",
                    cursor: "pointer", fontWeight: 600, fontSize: "13px",
                    fontFamily: "var(--font-sans)", transition: "all var(--transition)",
                  }}>
                    {v.color || v.size || v.sku}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Qty + Add to Cart */}
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", background: "var(--navy-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--navy-border)" }}>
              {[["−", -1], [qty, 0], ["+", 1]].map(([label, delta], i) => (
                <button key={i} onClick={() => delta && setQty(q => Math.max(1, Math.min(selectedVariant?.stock_qty || product?.variants?.[0]?.stock_qty || 1, q + delta)))}
                  style={{
                    width: "40px", height: "44px", background: "none", border: "none",
                    color: delta === 0 ? "var(--white)" : "var(--amber)", cursor: delta !== 0 ? "pointer" : "default",
                    fontWeight: 700, fontSize: "18px", fontFamily: "var(--font-mono)",
                    borderRight: i < 2 ? "1px solid var(--navy-border)" : "none",
                  }}>
                  {label}
                </button>
              ))}
            </div>
            <Btn full size="lg" onClick={handleAdd} disabled={!product.in_stock || adding}>
              {adding ? <Spinner size={18} color="#0a0f1e" /> : product.in_stock ? "Add to Cart" : "Out of Stock"}
            </Btn>
          </div>

          {/* Store */}
          <div style={{ padding: "16px", background: "var(--navy-mid)", borderRadius: "var(--radius-sm)", border: "1px solid var(--navy-border)" }}>
            <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "4px" }}>Sold by</div>
            <div style={{ fontWeight: 600, fontSize: "15px" }}>Shoply</div>
          </div>

          {/* Tags */}
          {product.tags?.length > 0 && (
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              {product.tags.map(t => <Badge key={t} color="var(--muted2)" bg="var(--navy-mid)">{t}</Badge>)}
            </div>
          )}
        </div>
      </div>
      <ProductReviews productId={product.id} state={state} dispatch={dispatch} />
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CHECKOUT PAGE
// ─────────────────────────────────────────────────────────────────────────────
function CheckoutPage({ state, dispatch }) {
  const { cart } = state;
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [couponCode, setCouponCode] = useState("");
  const [coupon, setCoupon] = useState(null);
  const [couponLoading, setCouponLoading] = useState(false);
  const [startingPayment, setStartingPayment] = useState(false);
  const [paymobEnabled, setPaymobEnabled] = useState(false);

  useEffect(() => {
    api.payments.paymobStatus().then(result => {
      if (result.success) setPaymobEnabled(Boolean(result.data?.card_checkout_enabled));
    });
  }, []);

  const applyCoupon = async () => {
    if (!couponCode.trim()) return;
    setCouponLoading(true); setError("");
    const res = await api.coupons.validate({ code: couponCode.trim(), subtotal: cart.summary.subtotal });
    setCouponLoading(false);
    if (res.success) setCoupon(res.data);
    else { setCoupon(null); setError(res.error?.message || "Could not apply this coupon."); }
  };

  const placeOrder = async () => {
    const number = whatsappNumber.replace(/[\s()-]/g, "");
    if (!/^\+[1-9]\d{7,14}$/.test(number)) {
      setError("Enter your WhatsApp number with country code, for example +201234567890.");
      return;
    }
    if (cart.items.length === 0) {
      setError("Your cart is empty.");
      return;
    }
    setLoading(true);
    setError("");
    const res = await api.orders.create({ whatsapp_number: number, ...(coupon?.code ? { coupon_code: coupon.code } : {}) });
    setLoading(false);
    if (!res.success) {
      setError(res.error?.message || res.detail?.message || "Could not place your order. Please try again.");
      return;
    }
    dispatch({ type: "CART_LOADED", cart: { items: [], summary: { item_count: 0, subtotal: 0, tax_estimate: 0, total: 0 }, warnings: [], isLoading: false } });
    dispatch({ type: "NAVIGATE", page: "orderSuccess", params: { order: res.data } });
  };

  const payByCard = async () => {
    const number = whatsappNumber.replace(/[\s()-]/g, "");
    if (!/^\+[1-9]\d{7,14}$/.test(number)) {
      setError("Enter your WhatsApp number with country code, for example +201234567890.");
      return;
    }
    if (cart.items.length === 0) { setError("Your cart is empty."); return; }
    setStartingPayment(true);
    setError("");
    const idempotencyKey = `paymob-${window.crypto.randomUUID()}`;
    const res = await api.payments.paymobCheckout({
      whatsapp_number: number,
      ...(coupon?.code ? { coupon_code: coupon.code } : {}),
    }, idempotencyKey);
    setStartingPayment(false);
    if (!res.success) {
      setError(res.error?.message || res.detail?.message || "Could not start secure card checkout.");
      return;
    }
    try {
      const checkout = new URL(res.data.checkout_url);
      if (checkout.protocol !== "https:" || !["accept.paymob.com", "eg.checkout.paymob.com"].includes(checkout.hostname)) {
        throw new Error("Invalid checkout destination");
      }
      window.location.assign(checkout.toString());
    } catch {
      setError("The secure payment page could not be opened. Please contact the store.");
    }
  };

  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "48px 24px 80px" }}>
      <div className="shop-kicker">ONE STEP FROM YOUR NEW FIND</div>
      <h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: 50, marginBottom: 14 }}>Place your order</h1>
      <p style={{ color: "var(--muted)", marginBottom: 28 }}>Choose a secure card payment with Paymob or send an order request and arrange payment on WhatsApp.</p>
      <div className="shop-card-panel shop-form-surface" style={{ background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius)", padding: 28 }}>
        <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 22, marginBottom: 18 }}>Order summary</h2>
        {cart.items.map(item => (
          <div key={`${item.product_id}-${item.variant_id || ""}`} style={{ display: "flex", justifyContent: "space-between", gap: 16, padding: "10px 0", borderBottom: "1px solid var(--navy-border)" }}>
            <span>{item.name} × {item.qty}</span>
            <span style={{ fontFamily: "var(--font-mono)" }}>{formatMoney(item.subtotal)}</span>
          </div>
        ))}
        <div style={{ display: "flex", justifyContent: "space-between", padding: "18px 0 8px", fontWeight: 700 }}><span>Subtotal</span><span style={{ color: "var(--amber)", fontFamily: "var(--font-mono)" }}>{formatMoney(cart.summary.total)}</span></div>
        {coupon && <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0 18px", color: "var(--success)", fontSize: 13 }}><span>Coupon {coupon.code}</span><span>-{formatMoney(coupon.discount)}</span></div>}
        <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0 24px", fontWeight: 700, borderTop: "1px solid var(--navy-border)" }}><span>Total</span><span style={{ color: "var(--amber)", fontFamily: "var(--font-mono)" }}>{formatMoney(coupon?.total ?? cart.summary.total)}</span></div>
        <Input label="WhatsApp number with country code" type="tel" value={whatsappNumber} onChange={e => setWhatsappNumber(e.target.value)} placeholder="+201234567890" required />
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginTop: 4 }}><div style={{ flex: 1 }}><Input label="Coupon code (optional)" value={couponCode} onChange={e => { setCouponCode(e.target.value.toUpperCase()); setCoupon(null); }} placeholder="WELCOME10" /></div><Btn variant="outline" onClick={applyCoupon} disabled={couponLoading}>{couponLoading ? "…" : "Apply"}</Btn></div>
        <p style={{ color: "var(--muted)", fontSize: 12, margin: "8px 0 18px" }}>Card details are entered on Paymob’s secure checkout and are never stored by Shoply. The WhatsApp option does not take payment now.</p>
        {error && <p style={{ color: "var(--danger)", fontSize: 13, marginBottom: 14 }}>{error}</p>}
        {paymobEnabled && <>
          <Btn full size="lg" onClick={payByCard} disabled={startingPayment || loading || cart.items.length === 0}>{startingPayment ? "Opening secure checkout…" : "Pay securely by Visa / card · Paymob"}</Btn>
          <div style={{ textAlign: "center", color: "var(--muted2)", fontSize: 12, margin: "14px 0" }}>OR</div>
        </>}
        <Btn full variant="outline" onClick={placeOrder} disabled={loading || startingPayment || cart.items.length === 0}>{loading ? "Submitting…" : "Request order via WhatsApp"}</Btn>
      </div>
    </main>
  );
}

function OrderChat({ orderId }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const load = async () => { const res = await api.orders.chat.list(orderId); if (res.success) setMessages(res.data || []); else setError(res.error?.message || "Could not load chat."); };
  useEffect(() => { if (!open) return undefined; load(); const timer = window.setInterval(load, 10000); return () => window.clearInterval(timer); }, [open, orderId]);
  const send = async () => { if (!text.trim()) return; const res = await api.orders.chat.send(orderId, { text: text.trim() }); if (res.success) { setMessages(current => [...current, res.data]); setText(""); } else setError(res.error?.message || "Could not send message."); };
  return <div style={{ marginTop: 16 }}><Btn size="sm" variant="outline" onClick={() => setOpen(value => !value)}>{open ? "Close chat" : "Message the store"}</Btn>{open && <div style={{ marginTop: 12, padding: 14, border: "1px solid var(--navy-border)", borderRadius: 10 }}><div style={{ maxHeight: 170, overflowY: "auto", display: "grid", gap: 8, marginBottom: 10 }}>{messages.length ? messages.map(message => <div key={message.id} style={{ padding: "8px 10px", borderRadius: 8, background: message.sender_role === "customer" ? "#dfbd8920" : "#10b98120", justifySelf: message.sender_role === "customer" ? "end" : "start", maxWidth: "85%", fontSize: 13 }}>{message.text}<div style={{ color: "var(--muted)", fontSize: 10, marginTop: 3 }}>{message.sender_role === "customer" ? "You" : "Shoply"}</div></div>) : <span style={{ color: "var(--muted)", fontSize: 12 }}>No messages yet.</span>}</div><div style={{ display: "flex", gap: 8 }}><input value={text} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === "Enter") send(); }} placeholder="Write a message…" style={{ flex: 1, padding: "9px 10px", borderRadius: 8, border: "1px solid var(--navy-border)", background: "var(--navy-mid)", color: "var(--white)" }} /><Btn size="sm" onClick={send}>Send</Btn></div>{error && <p style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>{error}</p>}</div>}</div>;
}

function AdminOrderChat({ orderId }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const load = async () => { const res = await api.admin.chat.list(orderId); if (res.success) setMessages(res.data || []); else setError(res.error?.message || "Could not load chat."); };
  useEffect(() => { if (!open) return undefined; load(); const timer = window.setInterval(load, 10000); return () => window.clearInterval(timer); }, [open, orderId]);
  const send = async () => { if (!text.trim()) return; const res = await api.admin.chat.send(orderId, { text: text.trim() }); if (res.success) { setMessages(current => [...current, res.data]); setText(""); } else setError(res.error?.message || "Could not send message."); };
  return <div style={{ marginTop: 12 }}><Btn size="sm" variant="ghost" onClick={() => setOpen(value => !value)}>{open ? "Close customer chat" : "Open customer chat"}</Btn>{open && <div style={{ marginTop: 10, padding: 12, border: "1px solid var(--navy-border)", borderRadius: 8 }}><div style={{ maxHeight: 150, overflowY: "auto", display: "grid", gap: 7, marginBottom: 9 }}>{messages.length ? messages.map(message => <div key={message.id} style={{ padding: "7px 9px", borderRadius: 7, background: message.sender_role === "admin" ? "#dfbd8920" : "#10b98120", justifySelf: message.sender_role === "admin" ? "end" : "start", maxWidth: "85%", fontSize: 12 }}>{message.text}</div>) : <span style={{ color: "var(--muted)", fontSize: 12 }}>No messages yet.</span>}</div><div style={{ display: "flex", gap: 7 }}><input value={text} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === "Enter") send(); }} placeholder="Reply to customer…" style={{ flex: 1, padding: "8px 9px", borderRadius: 7, border: "1px solid var(--navy-border)", background: "var(--navy-mid)", color: "var(--white)" }} /><Btn size="sm" onClick={send}>Send</Btn></div>{error && <p style={{ color: "var(--danger)", fontSize: 12, marginTop: 7 }}>{error}</p>}</div>}</div>;
}

// ─────────────────────────────────────────────────────────────────────────────
// ORDER SUCCESS PAGE
// ─────────────────────────────────────────────────────────────────────────────
function OrderSuccessPage({ state, dispatch }) {
  const order = state.ui.pageParams?.order;
  return (
    <main style={{ maxWidth: "600px", margin: "0 auto", padding: "80px 24px", textAlign: "center" }}>
      <div style={{ animation: "fadeInUp 0.5s ease" }}>
        <div style={{
          width: "80px", height: "80px", borderRadius: "50%", background: "#10b98122",
          border: "2px solid var(--success)", display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 24px", fontSize: "36px",
        }}>
          ✓
        </div>
        <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "36px", marginBottom: "12px" }}>Order Request Received</h1>
        <p style={{ color: "var(--muted)", fontSize: "16px", lineHeight: 1.7, marginBottom: "24px" }}>
          The store admin will contact you on WhatsApp to confirm your order, delivery, and payment. No payment has been taken yet.
        </p>
        {order && (
          <div style={{ background: "var(--navy-card)", borderRadius: "var(--radius)", border: "1px solid var(--navy-border)", padding: "24px", marginBottom: "32px", textAlign: "left" }}>
            {[
              ["Order ID", order.order_id],
              ["Status", order.status],
              ["Total", formatMoney(order.total || 0)],
              ["Items", order.items_count],
            ].map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--navy-border)" }}>
                <span style={{ color: "var(--muted)", fontSize: "14px" }}>{k}</span>
                <span style={{ fontWeight: 600, fontFamily: k === "Total" ? "var(--font-mono)" : "var(--font-sans)", color: k === "Status" ? "var(--success)" : "var(--white)" }}>{v}</span>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
          <Btn variant="ghost" onClick={() => dispatch({ type: "NAVIGATE", page: "orders" })}>View Orders</Btn>
          <Btn onClick={() => dispatch({ type: "NAVIGATE", page: "home" })}>Continue Shopping</Btn>
        </div>
      </div>
    </main>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ORDERS PAGE
// ─────────────────────────────────────────────────────────────────────────────
function OrdersPage({ state, dispatch }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextPage, setNextPage] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [receiptError, setReceiptError] = useState("");
  const [downloadingId, setDownloadingId] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const res = await api.orders.list({ page: 1, limit: 20 });
      if (res.success) {
        setOrders(res.data || []);
        setNextPage((res.meta?.total_pages || 1) > 1 ? 2 : null);
      } else {
        setOrders([]);
        setLoadError(res.error?.message || "Could not load your orders.");
      }
      setLoading(false);
    };
    load();
  }, []);

  const statusColor = { pending_contact: "var(--amber)", confirmed: "var(--info)", shipped: "var(--amber)", out_for_delivery: "var(--amber-dk)", delivered: "var(--success)", cancelled: "var(--danger)", pending: "var(--muted)" };

  const loadMore = async () => {
    if (!nextPage || loadingMore) return;
    setLoadingMore(true);
    setLoadError("");
    const res = await api.orders.list({ page: nextPage, limit: 20 });
    if (res.success) {
      setOrders(current => [...current, ...(res.data || [])]);
      setNextPage(nextPage < (res.meta?.total_pages || 1) ? nextPage + 1 : null);
    } else {
      setLoadError(res.error?.message || "Could not load more orders.");
    }
    setLoadingMore(false);
  };

  const downloadReceipt = async orderId => {
    setReceiptError("");
    setDownloadingId(orderId);
    try {
      const pdf = await api.orders.receipt(orderId);
      const url = URL.createObjectURL(pdf);
      const link = document.createElement("a");
      link.href = url;
      link.download = `shoply-receipt-${orderId.slice(-8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setReceiptError(error.message || "Could not download the receipt.");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <main style={{ maxWidth: "900px", margin: "0 auto", padding: "40px 24px 80px" }}>
      <div className="shop-kicker">YOUR SHOPLY ACCOUNT</div>
      <h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: "50px", marginBottom: "32px" }}>Your orders</h1>
      {loadError && <p role="alert" style={{ color: "var(--danger)", marginBottom: 16 }}>{loadError}</p>}
      {receiptError && <p role="alert" style={{ color: "var(--danger)", marginBottom: 16 }}>{receiptError}</p>}
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "60px" }}><Spinner size={32} /></div>
      ) : orders.length === 0 ? (
        <div style={{ textAlign: "center", padding: "80px 20px", color: "var(--muted)" }}>
          <svg aria-hidden="true" width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--amber)" strokeWidth="1.5" style={{ marginBottom: 16 }}><path d="m24 4 18 9v22l-18 9-18-9V13L24 4Z"/><path d="m6 13 18 9 18-9M24 22v22"/></svg>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: "24px", color: "var(--white)", marginBottom: "8px" }}>No orders yet</div>
          <Btn onClick={() => dispatch({ type: "NAVIGATE", page: "products" })} style={{ marginTop: "16px" }}>Start Shopping</Btn>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {orders.map(order => (
            <div key={order.id} className="shop-card-panel" style={{
              background: "var(--navy-card)", borderRadius: "var(--radius)",
              border: "1px solid var(--navy-border)", padding: "24px",
            }}>
              <div className="shop-order-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "15px" }}>#{order.id}</span>
                  <Badge color={statusColor[order.status] || "var(--muted)"}>{order.status.replace(/_/g, " ")}</Badge>
                </div>
                <div style={{ fontSize: "13px", color: "var(--muted)" }}>
                  {order.items_count ?? order.items?.length ?? 0} item(s) · {new Date(order.created_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "Africa/Cairo" })}
                </div>
                {order.contact_status === "contacted" && (
                  <div style={{ color: "var(--success)", fontSize: 13, marginTop: 6, fontWeight: 700 }}>
                    ✓ The store contacted you on WhatsApp
                  </div>
                )}
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "20px", fontWeight: 700, color: "var(--amber)", whiteSpace: "nowrap" }}>
                  {formatMoney(order.total)}
                </div>
              </div>
              {order.items?.length > 0 && (
                <div style={{ borderTop: "1px solid var(--navy-border)", marginTop: 18, paddingTop: 15 }}>
                  <div style={{ color: "var(--muted)", fontSize: 11, fontWeight: 800, letterSpacing: ".15em", marginBottom: 10 }}>ITEMS IN THIS ORDER</div>
                  {order.items.map((item, index) => (
                    <div key={`${item.product_id || item.name}-${index}`} style={{ display: "flex", justifyContent: "space-between", gap: 14, fontSize: 13, padding: "5px 0" }}>
                      <span>{item.name || "Product"} <span style={{ color: "var(--muted)" }}>× {item.qty}</span></span>
                      <span style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>{formatMoney(Number(item.unit_price || 0) * Number(item.qty || 0))}</span>
                    </div>
                  ))}
                </div>
              )}
              <OrderChat orderId={order.id} />
              {order.status === "delivered" && order.payment_status === "paid" && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 17 }}>
                  <span style={{ color: "var(--success)", fontSize: 13 }}>Delivered {order.delivered_at ? new Date(order.delivered_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "Africa/Cairo" }) : ""} · Payment confirmed</span>
                  <Btn size="sm" variant="outline" disabled={downloadingId === order.id} onClick={() => downloadReceipt(order.id)}>{downloadingId === order.id ? "Preparing PDF..." : "Download receipt PDF"}</Btn>
                </div>
              )}
            </div>
          ))}
          {nextPage && <Btn variant="outline" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Loading..." : "Show more orders"}</Btn>}
        </div>
      )}
    </main>
  );
}

function WishlistPage({ state, dispatch, onAddToCart }) {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    const res = await api.wishlist.list();
    if (res.success) setProducts(res.data || []);
    else setError(res.error?.message || "Could not load your saved items.");
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (state.auth.user?.role !== "customer") return <HomePage state={state} dispatch={dispatch} onAddToCart={onAddToCart} />;
  return <main style={{ maxWidth: "1280px", margin: "0 auto", padding: "48px 24px 80px" }}>
    <div className="shop-kicker">YOUR SHOPLY ACCOUNT</div>
    <h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: 50, marginBottom: 12 }}>Saved items</h1>
    <p style={{ color: "var(--muted)", marginBottom: 30 }}>Products you want to come back to.</p>
    {error && <p role="alert" style={{ color: "var(--danger)", marginBottom: 18 }}>{error}</p>}
    {loading ? <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Spinner size={32} /></div> : products.length === 0 ? <div className="shop-card-panel" style={{ padding: 44, textAlign: "center", borderRadius: "var(--radius)", color: "var(--muted)" }}><div style={{ fontSize: 42, color: "var(--amber)", marginBottom: 10 }}>♡</div><h2 style={{ fontFamily: "var(--font-serif)", color: "var(--white)", fontSize: 28, marginBottom: 8 }}>Nothing saved yet</h2><p style={{ marginBottom: 22 }}>Tap the heart on a product to keep it here.</p><Btn onClick={() => dispatch({ type: "NAVIGATE", page: "products" })}>Browse collection</Btn></div> : <div className="shop-product-grid">{products.map(product => <ProductCard key={product.id} product={product} state={state} dispatch={dispatch} onAddToCart={onAddToCart} />)}</div>}
  </main>;
}

// ─────────────────────────────────────────────────────────────────────────────
// ADMIN PRODUCT MANAGEMENT
// ─────────────────────────────────────────────────────────────────────────────
function AdminProducts({ dispatch }) {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ name: "", description: "", price: "", stock_qty: "", category_id: "", image_data: "", image_name: "" });
  const openCreate = () => {
    setEditingId(null);
    setForm({ name: "", description: "", price: "", stock_qty: "", category_id: "", image_data: "", image_name: "" });
    setError("");
    setShowForm(true);
  };
  const openEdit = product => {
    setEditingId(product.id);
    setForm({ name: product.name || "", description: product.description || "", price: String(product.price ?? ""), stock_qty: "", category_id: product.category_id || "", image_data: product.images?.[0] || "", image_name: product.images?.[0] ? "Current image" : "" });
    setError("");
    setShowForm(true);
  };

  const selectImage = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("Choose a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > 6_000_000) {
      setError("Image must be smaller than 6 MB.");
      return;
    }
    setSaving(true);
    setError("");
    const payload = new FormData();
    payload.append("image", file, "product-image");
    const res = await api.products.uploadImage(payload);
    setSaving(false);
    if (!res.success) {
      setError(res.error?.message || "Could not validate the image.");
      return;
    }
    setForm(current => ({ ...current, image_data: res.data.image, image_name: "Validated image" }));
  };

  const reload = async () => {
    const res = await api.products.manage({ limit: 200 });
    if (res.success) setProducts(res.data || []);
    else setError(res.error?.message || "Could not load products.");
    setLoading(false);
  };

  useEffect(() => {
    reload();
    api.categories.list().then(res => { if (res.success) setCategories(res.data || []); });
  }, []);

  const save = async () => {
    const price = Number(form.price);
    const stock = Number(form.stock_qty);
    if (form.name.trim().length < 3 || !form.description.trim() || !Number.isFinite(price) || price <= 0 || (!editingId && (!form.category_id || !Number.isInteger(stock) || stock < 0))) {
      setError("Enter a name, description, category, positive price, and valid stock quantity.");
      return;
    }
    setSaving(true);
    setError("");
    const details = {
      name: form.name.trim(), description: form.description.trim(), price,
      images: form.image_data ? [form.image_data] : [],
    };
    const res = editingId ? await api.products.update(editingId, details) : await api.products.create({
      ...details,
      category_id: form.category_id,
      variants: [{ sku: `SKU-${Date.now()}`, stock_qty: stock }],
    });
    setSaving(false);
    if (!res.success) {
      setError(res.error?.message || res.detail?.message || "Could not create product.");
      return;
    }
    setShowForm(false);
    setEditingId(null);
    setForm({ name: "", description: "", price: "", stock_qty: "", category_id: "", image_data: "", image_name: "" });
    dispatch({ type: "TOAST", toast: { type: "success", title: editingId ? "Product updated" : "Product added", message: "The catalog is up to date." } });
    reload();
  };

  const toggle = async (product) => {
    const next = product.status === "active" ? "inactive" : "active";
    const res = await api.products.update(product.id, { status: next });
    if (res.success) reload();
    else setError(res.error?.message || "Could not update product.");
  };

  return (
    <section style={{ margin: "36px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 24 }}>Products</h2>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Add and manage what customers can buy.</p>
        </div>
        <Btn onClick={openCreate}>+ Add Product</Btn>
      </div>
      {error && !showForm && <p style={{ color: "var(--danger)", marginBottom: 12 }}>{error}</p>}
      {loading ? <Spinner /> : products.length === 0 ? (
        <div style={{ padding: 24, background: "var(--navy-card)", borderRadius: "var(--radius)", color: "var(--muted)" }}>No products yet. Add the first one.</div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {products.map(product => (
            <div key={product.id} className="shop-admin-product-row" style={{ display: "flex", alignItems: "center", gap: 16, padding: 14, background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius)" }}>
              {safeImageSource(product.images?.[0]) && <img src={safeImageSource(product.images[0])} alt="" style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 6 }} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong>{product.name}</strong>
                <div style={{ color: "var(--muted)", fontSize: 13 }}>{formatMoney(product.final_price ?? product.price)} · {product.status}</div>
              </div>
              <Btn size="sm" variant="ghost" onClick={() => openEdit(product)}>Edit</Btn>
              <Btn size="sm" variant="ghost" onClick={() => toggle(product)}>{product.status === "active" ? "Hide" : "Publish"}</Btn>
            </div>
          ))}
        </div>
      )}
      <Modal isOpen={showForm} onClose={() => setShowForm(false)} title={editingId ? "Edit Product" : "Add Product"}>
        <div style={{ display: "grid", gap: 14 }}>
          <Input label="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
          <Input label="Price (EGP)" type="number" value={form.price} onChange={e => setForm({ ...form, price: e.target.value })} required />
          {!editingId && <><Select label="Category" value={form.category_id} onChange={e => setForm({ ...form, category_id: e.target.value })} options={[{ value: "", label: "Choose a category" }, ...categories.map(c => ({ value: c.id, label: c.name }))]} />
          <Input label="Stock quantity" type="number" value={form.stock_qty} onChange={e => setForm({ ...form, stock_qty: e.target.value })} required /></>}
          <div>
            <label style={{ display: "block", fontSize: 13, color: "var(--muted)", marginBottom: 6 }}>Product image (optional)</label>
            <input type="file" accept="image/jpeg,image/png,image/webp" onChange={selectImage} style={{ width: "100%", color: "var(--white)", padding: 10, border: "1px solid var(--navy-border)", borderRadius: 8, background: "var(--navy-card)" }} />
            {form.image_data && (
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
                <img src={safeImageSource(form.image_data)} alt="Preview" style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8, border: "1px solid var(--navy-border)" }} />
                <div style={{ color: "var(--muted)", fontSize: 12, flex: 1 }}>{form.image_name}</div>
                <Btn size="sm" variant="ghost" onClick={() => setForm(current => ({ ...current, image_data: "", image_name: "" }))}>Remove</Btn>
              </div>
            )}
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 6 }}>JPEG, PNG, or WebP · max 2.5 MB</p>
          </div>
          <div>
            <label style={{ display: "block", fontSize: 13, color: "var(--muted)", marginBottom: 6 }}>Description</label>
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={4} style={{ width: "100%", padding: 12, borderRadius: 8, background: "var(--navy-card)", border: "1px solid var(--navy-border)", color: "var(--white)" }} />
          </div>
          {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}
          <Btn full onClick={save} disabled={saving}>{saving ? "Saving…" : editingId ? "Save changes" : "Add Product"}</Btn>
        </div>
      </Modal>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
function AdminOrderRequests({ onDelivered }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deliveryTarget, setDeliveryTarget] = useState(null);
  const [paymentReceived, setPaymentReceived] = useState(false);
  const [savingDelivery, setSavingDelivery] = useState(false);
  const [contactingId, setContactingId] = useState(null);

  const buildWhatsappMessage = (order) => {
    const items = (order.items || []).map(item => `- ${item.name || item.product_id} × ${item.qty}`).join("\n");
    return [
      "مرحبًا، معك Shoply بخصوص طلبك.",
      `رقم الطلب: ${order.id.slice(-8)}`,
      "المنتجات:",
      items || "- لا توجد تفاصيل",
      `الإجمالي: ${formatMoney(order.total || 0)}`,
      order.payment_method === "paymob"
        ? "طريقة الدفع: بطاقة عبر Paymob (تم التأكيد إلكترونيًا)."
        : "طريقة الدفع: InstaPay",
      ...(order.payment_method === "paymob" ? [] : ["رقم InstaPay: 01030888493", "من فضلك أرسل تأكيد الدفع على نفس المحادثة."]),
    ].join("\n");
  };

  const reload = async () => {
    setError("");
    const res = await api.admin.orders({ status: "pending_contact", page: 1, limit: 100 });
    if (res.success) setOrders(res.data || []);
    else setError(res.error?.message || "Could not load order requests.");
    setLoading(false);
  };

  useEffect(() => { reload(); }, []);

  const confirmContact = async (orderId) => {
    setContactingId(orderId);
    setError("");
    const result = await api.admin.whatsappContacted(orderId);
    setContactingId(null);
    if (!result.success) {
      setError(result.error?.message || "Could not confirm WhatsApp contact.");
      return;
    }
    await reload();
  };

  const finishDelivery = async () => {
    if (!deliveryTarget || !paymentReceived) return;
    setSavingDelivery(true);
    const result = await api.admin.deliverOrder(deliveryTarget.id);
    setSavingDelivery(false);
    if (!result.success) {
      setError(result.error?.message || "Could not mark the order as delivered.");
      return;
    }
    setDeliveryTarget(null);
    setPaymentReceived(false);
    await reload();
    onDelivered();
  };

  return (
    <section style={{ margin: "36px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 24 }}>WhatsApp order requests</h2>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Contact customers to confirm their order and payment.</p>
        </div>
        <Btn variant="ghost" size="sm" onClick={reload}>Refresh</Btn>
      </div>
      {error && <p style={{ color: "var(--danger)", marginBottom: 12 }}>{error}</p>}
      {loading ? <Spinner /> : orders.length === 0 ? (
        <div style={{ padding: 24, background: "var(--navy-card)", borderRadius: "var(--radius)", color: "var(--muted)" }}>No new order requests.</div>
      ) : <div style={{ display: "grid", gap: 12 }}>
        {orders.map(order => (
          <div key={order.id} style={{ padding: 18, background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
              <div>
                <strong>Order #{order.id.slice(-8)}</strong>
                <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>
                  {order.whatsapp_number} · {formatMoney(order.total || 0)} · {order.payment_status}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                <a href={`https://wa.me/${order.whatsapp_number?.replace(/\D/g, "")}?text=${encodeURIComponent(buildWhatsappMessage(order))}`} target="_blank" rel="noopener noreferrer" style={{ color: "#0a0f1e", background: "var(--success)", borderRadius: 8, padding: "10px 14px", textDecoration: "none", fontWeight: 700, fontSize: 13 }}>Open WhatsApp</a>
                {order.contact_status !== "contacted" && <Btn size="sm" variant="outline" disabled={contactingId === order.id} onClick={() => confirmContact(order.id)}>{contactingId === order.id ? "Saving..." : "Confirm message sent"}</Btn>}
                {order.contact_status === "contacted" && <Btn size="sm" onClick={() => { setDeliveryTarget(order); setPaymentReceived(order.payment_status === "paid"); }}>Mark delivered</Btn>}
              </div>
            </div>
            <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 12 }}>
              {order.items?.map(item => `${item.name || item.product_id} × ${item.qty}`).join(" · ")}
            </div>
            {order.contact_status === "contacted" && <div style={{ color: "var(--success)", fontSize: 12, marginTop: 10 }}>✓ Contacted on WhatsApp</div>}
            <AdminOrderChat orderId={order.id} />
          </div>
        ))}
      </div>}
      <Modal isOpen={Boolean(deliveryTarget)} onClose={() => { if (!savingDelivery) setDeliveryTarget(null); }} title="Complete delivery">
        <p style={{ color: "var(--muted)", fontSize: 14, lineHeight: 1.6, marginBottom: 18 }}>
          Order #{deliveryTarget?.id?.slice(-8)} · {formatMoney(deliveryTarget?.total)}. This will mark the order as delivered, add it to sales, and make the customer's PDF receipt available.
        </p>
        {deliveryTarget?.payment_status === "paid" ? (
          <p style={{ color: "var(--success)", fontSize: 13, marginBottom: 20 }}>✓ Paymob confirmed this payment automatically.</p>
        ) : (
          <label style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 13, lineHeight: 1.5, cursor: "pointer", marginBottom: 20 }}>
            <input type="checkbox" checked={paymentReceived} onChange={event => setPaymentReceived(event.target.checked)} style={{ marginTop: 3, accentColor: "var(--amber)" }} />
            I confirm the InstaPay payment was received and the order was delivered to the customer.
          </label>
        )}
        <Btn full disabled={!paymentReceived || savingDelivery} onClick={finishDelivery}>{savingDelivery ? "Saving..." : "Confirm delivery"}</Btn>
      </Modal>
    </section>
  );
}

function AdminCoupons() {
  const [coupons, setCoupons] = useState([]);
  const [form, setForm] = useState({ code: "", discount_type: "percent", value: "", min_order_total: "", max_uses: "" });
  const [message, setMessage] = useState("");
  const load = async () => { const res = await api.admin.coupons.list(); if (res.success) setCoupons(res.data || []); else setMessage(res.error?.message || "Could not load coupons."); };
  useEffect(() => { load(); }, []);
  const create = async () => { const res = await api.admin.coupons.create({ code: form.code, discount_type: form.discount_type, value: Number(form.value), min_order_total: Number(form.min_order_total || 0), max_uses: Number(form.max_uses || 0), active: true }); if (!res.success) { setMessage(res.error?.message || "Could not create coupon."); return; } setForm({ code: "", discount_type: "percent", value: "", min_order_total: "", max_uses: "" }); setMessage("Coupon created."); load(); };
  const disable = async id => { await api.admin.coupons.disable(id); load(); };
  return <section style={{ margin: "36px 0" }}><div><h2 style={{ fontFamily: "var(--font-serif)", fontSize: 24 }}>Coupons</h2><p style={{ color: "var(--muted)", fontSize: 13 }}>Create simple percentage or fixed EGP discounts.</p></div><div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: 8, margin: "14px 0" }}><Input label="Code" value={form.code} onChange={event => setForm({ ...form, code: event.target.value.toUpperCase() })} placeholder="WELCOME10" /><Select label="Type" value={form.discount_type} onChange={event => setForm({ ...form, discount_type: event.target.value })} options={[{ value: "percent", label: "Percent" }, { value: "fixed", label: "Fixed EGP" }]} /><Input label="Value" type="number" value={form.value} onChange={event => setForm({ ...form, value: event.target.value })} /><Input label="Min order" type="number" value={form.min_order_total} onChange={event => setForm({ ...form, min_order_total: event.target.value })} /><Input label="Max uses (0 = unlimited)" type="number" value={form.max_uses} onChange={event => setForm({ ...form, max_uses: event.target.value })} /></div><Btn size="sm" onClick={create} disabled={!form.code || !form.value}>Create coupon</Btn>{message && <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>{message}</p>}<div style={{ display: "grid", gap: 8, marginTop: 14 }}>{coupons.map(coupon => <div key={coupon.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: 12, background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: 8 }}><span><strong>{coupon.code}</strong> · {coupon.discount_type === "percent" ? `${coupon.value}%` : `${coupon.value} EGP`} · used {coupon.used_count || 0}</span>{coupon.active && <Btn size="sm" variant="ghost" onClick={() => disable(coupon.id)}>Disable</Btn>}</div>)}</div></section>;
}

// ─────────────────────────────────────────────────────────────────────────────
function AdminDeliverySales({ revision }) {
  const [days, setDays] = useState(14);
  const [summary, setSummary] = useState(null);
  const [delivered, setDelivered] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      const [salesResult, ordersResult] = await Promise.all([
        api.admin.salesSummary(days),
        api.admin.orders({ status: "delivered", payment_status: "paid", page: 1, limit: 100 }),
      ]);
      if (!active) return;
      if (salesResult.success && ordersResult.success) {
        setSummary(salesResult.data);
        setDelivered(ordersResult.data || []);
      } else {
        setError(salesResult.error?.message || ordersResult.error?.message || "Could not load delivery sales.");
      }
      setLoading(false);
    };
    load();
    return () => { active = false; };
  }, [days, revision]);

  const highest = Math.max(1, ...(summary?.daily || []).map(day => day.revenue));

  return (
    <section style={{ margin: "44px 0 0" }}>
      <div className="shop-kicker">DELIVERY & SALES</div>
      <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 34, margin: "8px 0 7px" }}>Delivered orders</h2>
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 24 }}>Sales count only orders marked delivered with payment received.</p>
      {error && <p role="alert" style={{ color: "var(--danger)", marginBottom: 14 }}>{error}</p>}
      {loading ? <Spinner /> : summary && <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
          {[
            ["TOTAL SALES", formatMoney(summary.total_revenue)],
            ["DELIVERED ORDERS", summary.delivered_orders],
            ["ITEMS SOLD", summary.items_sold],
          ].map(([label, value]) => (
            <div key={label} style={{ padding: 20, background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius)" }}>
              <div style={{ color: "var(--muted)", fontSize: 10, fontWeight: 800, letterSpacing: ".14em" }}>{label}</div>
              <div style={{ color: "var(--amber)", fontFamily: "var(--font-mono)", fontSize: "clamp(19px, 2.4vw, 27px)", fontWeight: 700, marginTop: 12 }}>{value}</div>
            </div>
          ))}
        </div>
        <div style={{ padding: "24px 22px 18px", background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius)", marginBottom: 22 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 19 }}>
            <div>
              <div style={{ fontWeight: 800, fontSize: 15 }}>Sales by delivery day</div>
              <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>{formatMoney(summary.period_revenue)} in the last {days} days</div>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {[7, 14, 30].map(option => <button key={option} type="button" onClick={() => setDays(option)} aria-pressed={days === option} style={{ padding: "7px 10px", borderRadius: 8, border: `1px solid ${days === option ? "var(--amber)" : "var(--navy-border)"}`, color: days === option ? "var(--amber)" : "var(--muted)", background: "transparent", cursor: "pointer", fontSize: 12 }}>{option}d</button>)}
            </div>
          </div>
          <div role="img" aria-label={`Sales chart for the last ${days} days, total ${formatMoney(summary.period_revenue)}`} style={{ overflowX: "auto" }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 168, minWidth: days === 30 ? 850 : 460, borderBottom: "1px solid var(--navy-border)", paddingBottom: 25 }}>
              {summary.daily.map(day => (
                <div key={day.date} title={`${day.date}: ${formatMoney(day.revenue)} · ${day.orders} order(s)`} style={{ flex: 1, minWidth: 18, height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center", position: "relative" }}>
                  <div style={{ width: "100%", maxWidth: 34, height: `${Math.max(3, (day.revenue / highest) * 100)}%`, borderRadius: "6px 6px 0 0", background: day.revenue ? "linear-gradient(180deg, var(--amber-lt), var(--amber-dk))" : "var(--navy-border)" }} />
                  <span style={{ position: "absolute", top: "calc(100% + 7px)", color: "var(--muted)", fontSize: 10, whiteSpace: "nowrap" }}>{days === 7 ? new Date(`${day.date}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : day.date.slice(-2)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <h3 style={{ fontFamily: "var(--font-serif)", fontSize: 25, marginBottom: 12 }}>Recent deliveries</h3>
        {delivered.length === 0 ? <div style={{ padding: 22, background: "var(--navy-card)", borderRadius: "var(--radius)", color: "var(--muted)" }}>No delivered orders yet. Completed orders will appear here.</div> :
          <div style={{ display: "grid", gap: 10 }}>
            {delivered.map(order => <div key={order.id} style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", padding: 17, background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius-sm)" }}>
              <div>
                <strong style={{ fontSize: 13 }}>Order #{order.id.slice(-8)}</strong>
                <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 5 }}>{(order.items || []).map(item => `${item.name || "Product"} × ${item.qty}`).join(" · ") || `${order.items_count || 0} item(s)`}</div>
                <div style={{ color: "var(--success)", fontSize: 12, marginTop: 6 }}>Delivered {order.delivered_at ? new Date(order.delivered_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "Africa/Cairo" }) : ""} · {order.payment_status === "paid" ? "Paid" : "Payment pending"}</div>
              </div>
              <strong style={{ color: "var(--amber)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>{formatMoney(order.total)}</strong>
            </div>)}
          </div>}
      </>}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
function AdminDashboard({ dispatch }) {
  const [salesRevision, setSalesRevision] = useState(0);
  return (
    <main style={{ maxWidth: 1080, margin: "0 auto", padding: "40px 24px 80px" }}>
      <div className="shop-kicker">STORE WORKSPACE</div>
      <h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: 50 }}>Admin dashboard</h1>
      <p style={{ color: "var(--muted)", marginTop: 6 }}>Manage products and contact customers about their orders.</p>
      <AdminPushNotifications dispatch={dispatch} />
      <AdminProducts dispatch={dispatch} />
      <AdminCoupons />
      <AdminOrderRequests onDelivered={() => setSalesRevision(value => value + 1)} />
      <AdminDeliverySales revision={salesRevision} />
    </main>
  );
}

function AdminPushNotifications({ dispatch }) {
  const [messaging, setMessaging] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!messaging) return undefined;
    return listenForForegroundPush(messaging, payload => {
      const title = payload.notification?.title || "Shoply: طلب جديد";
      const body = payload.notification?.body || "وصلك طلب جديد من المتجر.";
      dispatch({ type: "TOAST", toast: { type: "success", title, message: body } });
      if (Notification.permission === "granted") {
        try { new Notification(title, { body, icon: "/favicon.svg" }); } catch { /* Browser may suppress foreground notifications. */ }
      }
    });
  }, [messaging, dispatch]);

  const enable = async () => {
    setBusy(true); setMessage("");
    try {
      const result = await enableAdminPush();
      const saved = await api.admin.registerPushDevice(result.token);
      if (!saved.success) throw new Error(saved.error?.message || "Could not save this device.");
      setMessaging(result.messaging);
      setMessage("إشعارات الطلبات الجديدة مفعّلة على الجهاز ده.");
    } catch (error) {
      setMessage(error.message || "ما قدرناش نفعّل الإشعارات.");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true); setMessage("");
    try {
      const token = await disableAdminPush();
      if (token) {
        const removed = await api.admin.removePushDevice(token);
        if (!removed.success) throw new Error(removed.error?.message || "Could not remove this device.");
      }
      setMessaging(null);
      setMessage("تم إيقاف إشعارات الطلبات على الجهاز ده.");
    } catch (error) {
      setMessage(error.message || "ما قدرناش نوقف الإشعارات.");
    } finally {
      setBusy(false);
    }
  };

  const configured = isPushConfigured();
  return (
    <section style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14, margin: "24px 0", padding: 18, background: "var(--navy-card)", border: "1px solid var(--navy-border)", borderRadius: "var(--radius)" }}>
      <div>
        <strong>تنبيهات الطلبات على الموبايل</strong>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>هيوصلك إشعار لما عميل يبعت طلب جديد.</p>
        {message && <p role="status" style={{ color: message.includes("مفعّلة") || message.includes("إيقاف") ? "var(--success)" : "var(--amber)", fontSize: 12, marginTop: 6 }}>{message}</p>}
        {!configured && <p style={{ color: "var(--amber)", fontSize: 12, marginTop: 6 }}>محتاجين نكمّل إعداد Firebase قبل التفعيل.</p>}
      </div>
      {messaging
        ? <Btn size="sm" variant="outline" onClick={disable} disabled={busy}>{busy ? "لحظة…" : "إيقاف الإشعارات"}</Btn>
        : <Btn size="sm" onClick={enable} disabled={busy || !configured}>{busy ? "جاري التفعيل…" : "تفعيل إشعارات الموبايل"}</Btn>}
    </section>
  );
}

function VerifyAccountPage({ dispatch, token }) {
  const [message, setMessage] = useState("Verifying your email…");
  const [verified, setVerified] = useState(false);
  const submitted = useRef(false);
  useEffect(() => {
    if (submitted.current) return;
    submitted.current = true;
    if (!token) { setMessage("This verification link is invalid or expired."); return; }
    api.auth.verifyAccount({ token }).then(res => {
      setVerified(!!res.success);
      setMessage(res.success ? "Your email is verified. Sign in with your email and password, then enter the code we send you." : (res.error?.message || "This verification link is invalid or expired."));
    });
  }, [token]);
  return <main style={{ maxWidth: 520, margin: "0 auto", padding: "90px 24px 120px" }}>
    <div className="shop-kicker">SHOPLY ACCOUNT</div>
    <h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: 46 }}>Email verification</h1>
    <p style={{ color: verified ? "var(--success)" : "var(--muted)", margin: "24px 0", lineHeight: 1.7 }}>{message}</p>
    <Btn onClick={() => dispatch({ type: "AUTH_MODAL", mode: "login" })}>Sign in</Btn>
  </main>;
}

function ResetPasswordPage({ dispatch, token }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const submit = async () => {
    const feedback = getPasswordFeedback(password);
    if (!feedback.ready) { setMessage(feedback.message); return; }
    if (password !== confirm) { setMessage("Both passwords must match."); return; }
    setLoading(true); setMessage("");
    const res = await api.auth.resetPassword({ token, new_password: password });
    setLoading(false);
    if (res.success) { setMessage("Password reset. You can sign in now."); window.history.replaceState({}, "", "/"); window.setTimeout(() => dispatch({ type: "AUTH_MODAL", mode: "login" }), 700); }
    else setMessage(res.error?.message || "This reset link is invalid or expired.");
  };
  return <main style={{ maxWidth: 520, margin: "0 auto", padding: "90px 24px 120px" }}><div className="shop-kicker">SHOPLY ACCOUNT</div><h1 className="shop-section-title" style={{ fontFamily: "var(--font-serif)", fontSize: 46 }}>Choose a new password</h1><div style={{ display: "grid", gap: 14, marginTop: 24 }}><Input label="New password" type="password" value={password} autoComplete="new-password" onChange={event => { setPassword(event.target.value); setMessage(""); }} /><PasswordStrength password={password} /><Input label="Confirm password" type="password" value={confirm} autoComplete="new-password" onChange={event => setConfirm(event.target.value)} />{message && <p style={{ color: message.startsWith("Password reset") ? "var(--success)" : "var(--danger)", fontSize: 13 }}>{message}</p>}<Btn full size="lg" onClick={submit} disabled={loading || !token}>{loading ? "Saving…" : "Set new password"}</Btn></div></main>;
}

// APP INITIALIZER — attempts silent refresh on load
// ─────────────────────────────────────────────────────────────────────────────
// function AppInitializer({ dispatch }) {
//   useEffect(() => {
//     const init = async () => {
//       const res = await api.auth.refresh();
//       if (res.success) {
//         setAccessToken(res.data.access_token);
//         const meRes = await api.auth.me();
//         dispatch({ type: "AUTH_LOADED", token: res.data.access_token, user: meRes.success ? meRes.data : null });
//       } else {
//         dispatch({ type: "AUTH_LOADED", token: null, user: null });
//       }
//     };
//     init();
//   }, [dispatch]);
//   return null;
// }

// ─────────────────────────────────────────────────────────────────────────────
// ROOT APP
// ─────────────────────────────────────────────────────────────────────────────
export default function Storefront() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const authFromRedux = useSelector((state) => state.auth); // الوصول لحالة Redux
  const reduxDispatch = useReduxDispatch();

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.get("payment") === "paymob" && !state.auth.isLoading) {
      window.history.replaceState({}, "", window.location.pathname);
      dispatch({ type: "NAVIGATE", page: "orders" });
      dispatch({ type: "TOAST", toast: { type: "success", title: "Payment submitted", message: "We’re confirming the payment with Paymob. Check your orders in a moment." } });
      return;
    }
    if (query.get("admin_orders") !== "1" || state.auth.isLoading) return;
    window.history.replaceState({}, "", window.location.pathname);
    if (state.auth.isAuthenticated && state.auth.user?.role === "admin") {
      dispatch({ type: "NAVIGATE", page: "admin" });
    }
  }, [state.auth.isLoading, state.auth.isAuthenticated, state.auth.user?.role]);

  useEffect(() => {
    const resetHash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    // Recovery tokens are accepted only in the URL fragment, which browsers
    // never send to the server in requests or Referer headers.
    const verifyToken = resetHash.get("verify_token");
    const resetToken = resetHash.get("reset_token");
    if (verifyToken || resetToken) {
      window.history.replaceState({}, "", window.location.pathname);
      dispatch({ type: "NAVIGATE", page: verifyToken ? "verifyAccount" : "resetPassword", params: { token: verifyToken || resetToken } });
    }
    window.scrollTo({ top: 0, behavior: "auto" });
    const sections = document.querySelectorAll("[data-reveal]");
    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      sections.forEach(section => section.classList.add('is-visible'));
      return;
    }
    const observer = new window.IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: .08, rootMargin: '0px 0px -30px 0px' });
    sections.forEach(section => observer.observe(section));
    return () => observer.disconnect();
  }, [state.ui.page, state.auth.isAuthenticated]);

  useEffect(() => {
    // إذا نجح Redux في جلب بيانات المستخدم ولم يتم تحديث Storefront بعد
    if (authFromRedux.isAuthenticated && !state.auth.isAuthenticated) {
      
      setAccessToken(authFromRedux.accessToken); // 👈 أضف هذا السطر لحقن التوكن في الذاكرة
      
      dispatch({ 
        type: "AUTH_LOADED", 
        token: authFromRedux.accessToken, 
        user: authFromRedux.user 
      });
    }
    // إذا انتهى التحميل في Redux وفشل تسجيل الدخول
    else if (!authFromRedux.isLoading && !authFromRedux.isAuthenticated && state.auth.isLoading) {
      dispatch({ type: "AUTH_LOADED", token: null, user: null });
    }
  }, [authFromRedux, state.auth.isLoading, dispatch]);

  // Wire auth dispatch for silent refresh
  useEffect(() => { setAuthDispatch(dispatch); }, [dispatch]);

  // Load cart when authenticated
  useEffect(() => {
    if (!state.auth.isAuthenticated) return;
    const loadCart = async () => {
      dispatch({ type: "CART_LOADING" });
      const res = await api.cart.get();
      if (res.success) dispatch({ type: "CART_LOADED", cart: res.data });
      else dispatch({ type: "CART_LOADED", cart: { items: [], summary: { item_count: 0, subtotal: 0, tax_estimate: 0, total: 0 }, warnings: [] } });
    };
    loadCart();
  }, [state.auth.isAuthenticated]);

  // Add to cart handler — uses real API only
  const onAddToCart = useCallback(async (productId, variantId, qty = 1) => {
    if (!state.auth.isAuthenticated) {
      dispatch({ type: "AUTH_MODAL", mode: "login" });
      return;
    }
    const res = await api.cart.addItem({ product_id: productId, variant_id: variantId || null, qty });
    if (res.success) {
      dispatch({ type: "CART_LOADED", cart: res.data });
      dispatch({ type: "TOAST", toast: { type: "success", title: "Added to cart ✓", message: "Item added successfully." } });
    } else {
      dispatch({ type: "TOAST", toast: { type: "error", title: "Error", message: res.error?.message || "Could not add item to cart." } });
    }
  }, [state.auth.isAuthenticated, state.cart.items]);

  const toastClear = useCallback(() => dispatch({ type: "TOAST_CLEAR" }), []);
  const handleLogout = useCallback(async () => {
    try {
      await reduxDispatch(logoutUser());
    } finally {
      dispatch({ type: "LOGOUT" });
      dispatch({ type: "NAVIGATE", page: "home" });
      dispatch({
        type: "TOAST",
        toast: {
          type: "success",
          title: "Logged out",
          message: "Session ended. Please sign in again to continue.",
        },
      });
    }
  }, [reduxDispatch]);

  // Render current page
  const renderPage = () => {
    if (state.auth.isLoading) {
      return (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh", flexDirection: "column", gap: "16px" }}>
          <Spinner size={40} />
          <p style={{ color: "var(--muted)" }}>Loading...</p>
        </div>
      );
    }
    const pageProps = { state, dispatch, onAddToCart };
    switch (state.ui.page) {
      case "home":         return <HomePage {...pageProps} />;
      case "admin":        return state.auth.user?.role === "admin" ? <AdminDashboard {...pageProps} /> : <HomePage {...pageProps} />;
      case "products":
      case "product":
      case "checkout":
      case "orders":
        if (!state.auth.isAuthenticated) return (
          <main style={{ minHeight: "60vh", maxWidth: 600, margin: "0 auto", padding: "100px 24px", textAlign: "center" }}>
            <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 36, marginBottom: 12 }}>Sign in to shop</h1>
            <p style={{ color: "var(--muted)", marginBottom: 24 }}>Create an account or sign in to see products and place an order.</p>
            <Btn onClick={() => dispatch({ type: "AUTH_MODAL", mode: "login" })}>Sign In</Btn>
          </main>
        );
        if (state.ui.page === "products") return <ProductsPage {...pageProps} />;
        if (state.ui.page === "product") return <ProductDetailPage {...pageProps} />;
        if (state.ui.page === "checkout") return <CheckoutPage {...pageProps} />;
        return <OrdersPage {...pageProps} />;
      case "orderSuccess": return <OrderSuccessPage {...pageProps} />;
      case "wishlist":     return state.auth.isAuthenticated ? <WishlistPage {...pageProps} /> : <HomePage {...pageProps} />;
      case "verifyAccount": return <VerifyAccountPage dispatch={dispatch} token={state.ui.pageParams.token} />;
      case "resetPassword": return <ResetPasswordPage dispatch={dispatch} token={state.ui.pageParams.token} />;
      case "delivery":     { window.location.href = "/delivery/dashboard"; return null; }
      default:             return <HomePage {...pageProps} />;
    }
  };

  return (
    <div>
      <GlobalStyles />
      <Navbar state={state} dispatch={dispatch} onLogout={handleLogout} />
      <div key={state.ui.page} className="shop-page">{renderPage()}</div>
      <CartDrawer state={state} dispatch={dispatch} />
      <AuthModal state={state} dispatch={dispatch} />
      <Toast toast={state.ui.toast} onClear={toastClear} />

      {/* Footer */}
      <footer style={{ borderTop: "1px solid rgba(223,189,137,.2)", padding: "64px 24px 30px", background: "#071411" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 32, flexWrap: "wrap", paddingBottom: 48 }}>
            <div>
              <div className="shop-kicker">CURATED FOR EVERYDAY LIVING</div>
              <div style={{ fontFamily: "var(--font-serif)", fontSize: "clamp(48px,7vw,90px)", lineHeight: .9, letterSpacing: "-.04em", color: "var(--white)" }}>Good things, <em style={{ color: "var(--amber)" }}>found.</em></div>
            </div>
            <Btn variant="outline" style={{ borderRadius: 100, borderWidth: 1 }} onClick={() => dispatch({ type: "NAVIGATE", page: "products" })}>Explore the collection ↗</Btn>
          </div>
          <div style={{ borderTop: "1px solid var(--navy-border)", paddingTop: 24, display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", color: "var(--muted)", fontSize: 12 }}>
            <span>© 2026 Shoply · Curated with care.</span>
            <span>Questions about an order? We’ll follow up on WhatsApp.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
