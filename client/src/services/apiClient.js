/**
 * services/apiClient.js
 * Axios instance pre-configured with:
 *   - Base URL from env
 *   - withCredentials: true (sends HttpOnly refresh cookie)
 *   - X-Request-ID on every request
 *   - Request interceptor: injects Bearer token from Redux store
 *   - Response interceptor: silent token refresh on 401 TOKEN_EXPIRED
 */
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';
import { store } from '../store';
import { tokenRefreshed, logout } from '../features/auth/authSlice';

// استخدام المتغير البيئي مع fallback محلي
const BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,       // Sends HttpOnly refresh_token cookie automatically
  headers: { 'Content-Type': 'application/json' },
});

let isRefreshing = false;
let pendingQueue = [];

const processQueue = (error, token = null) => {
  pendingQueue.forEach(({ resolve, reject }) =>
    error ? reject(error) : resolve(token)
  );
  pendingQueue = [];
};

// ── Silent Refresh Logic ───────────────────────────────────────────────────
// دالة التجديد الذكية التي تحفظ التوكن في Redux بمجرد استلامه
const silentRefresh = async () => {
  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      pendingQueue.push({ resolve, reject });
    });
  }

  isRefreshing = true;
  try {
    const res = await axios.post(
      `${BASE_URL}/auth/refresh`,
      {},
      { withCredentials: true }
    );
    const newToken = res.data.data.access_token;
    
    // تحديث التوكن في Redux Store فوراً ليكون جاهزاً للطلبات اللاحقة
    store.dispatch(tokenRefreshed(newToken));
    processQueue(null, newToken);
    
    return res; 
  } catch (err) {
    processQueue(err, null);
    store.dispatch(logout()); // طرد المستخدم فقط إذا فشل التجديد فعلياً
    throw err;
  } finally {
    isRefreshing = false;
  }
};

// ── Request interceptor: add auth header + request ID ──────────────────────
apiClient.interceptors.request.use((config) => {
  config.headers['X-Request-ID'] = uuidv4();
  
  // سحب أحدث توكن متاح من الـ Store قبل كل طلب
  const token = store.getState().auth.accessToken;
  if (token) config.headers['Authorization'] = `Bearer ${token}`;
  
  return config;
});

// ── Response interceptor: silent refresh on TOKEN_EXPIRED ──────────────────
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const errCode  = error.response?.data?.error?.code || error.response?.data?.detail?.code || error.response?.data?.detail?.error?.code;

    if (error.response?.status === 401 && errCode === 'TOKEN_EXPIRED' && !original._retry) {
      original._retry = true;

      // إذا كان هناك طلب تجديد قيد التنفيذ، اجعل هذا الطلب ينتظر في الطابور
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject });
        }).then((token) => {
          original.headers['Authorization'] = `Bearer ${token}`;
          return apiClient(original);
        });
      }

      // طلب تجديد التوكن
      try {
        await silentRefresh();
        // بمجرد نجاح التجديد، أعد إرسال الطلب المرفوض. 
        // سيقوم الـ Request Interceptor بوضع التوكن الجديد تلقائياً.
        return apiClient(original);
      } catch (refreshErr) {
        return Promise.reject(refreshErr);
      }
    }

    return Promise.reject(error);
  }
);

// ── API module ─────────────────────────────────────────────────────────────
export const api = {
  auth: {
    register:       (data)         => apiClient.post('/auth/register', data),
    login:          (data)         => apiClient.post('/auth/login', data),
    verifyAdminMfa:  (data)         => apiClient.post('/auth/admin/verify-mfa', data),
    logout:         ()             => apiClient.post('/auth/logout'),
    refresh:        ()             => silentRefresh(), // 👈 ربط الدالة بمسار الـ Refresh
    me:             ()             => apiClient.get('/auth/me'),
    forgotPassword: (data)         => apiClient.post('/auth/forgot-password', data),
    verifyAccount:  (data)         => apiClient.post('/auth/verify', data),
  },
  products: {
    list:   (params)               => apiClient.get('/products', { params }),
    get:    (id)                   => apiClient.get(`/products/${id}`),
    create: (data)                 => apiClient.post('/products', data),
    update: (id, data)             => apiClient.patch(`/products/${id}`, data),
    delete: (id)                   => apiClient.delete(`/products/${id}`),
    uploadImage: (formData)         => apiClient.post('/products/images', formData, {
                                        headers: { 'Content-Type': 'multipart/form-data' },
                                      }),
    mine:   (params)               => apiClient.get('/products/mine', { params }),
  },
  categories: {
    list: ()                       => apiClient.get('/categories'),
  },
  cart: {
    get:        ()                 => apiClient.get('/cart'),
    addItem:    (data)             => apiClient.post('/cart/items', data),
    updateItem: (productId, data)  => apiClient.patch(`/cart/items/${productId}`, data),
    removeItem: (productId)        => apiClient.delete(`/cart/items/${productId}`),
    clear:      ()                 => apiClient.delete('/cart'),
  },
  checkout: {
    createIntent: (data)           => apiClient.post('/checkout/payment-intent', data),
    confirmOrder: (data)           => apiClient.post('/orders', data),
  },
  orders: {
    list: (params)                 => apiClient.get('/orders', { params }),
    get:  (id)                     => apiClient.get(`/orders/${id}`),
    vendorOrders: (params)         => apiClient.get('/vendor/orders', { params }),
  },
  delivery: {
    verificationStatus: ()         => apiClient.get('/delivery/verification/status'),
    submitDocs: (formData)         => apiClient.post('/delivery/verification/submit', formData, {
                                        headers: { 'Content-Type': 'multipart/form-data' },
                                      }),
    orders:     ()                 => apiClient.get('/delivery/orders'),
    startDelivery: (orderId)       => apiClient.post(`/delivery/orders/${orderId}/start-delivery`),
    verifyOtp:  (orderId, data)    => apiClient.post(`/delivery/orders/${orderId}/verify-otp`, data),
    uploadProof: (orderId, form)   => apiClient.post(`/delivery/orders/${orderId}/proof`, form, {
                                        headers: { 'Content-Type': 'multipart/form-data' },
                                      }),
  },
  admin: {
    dashboard:      ()             => apiClient.get('/admin/dashboard'),
    users:          (params)       => apiClient.get('/admin/users', { params }),
    approveProduct: (id)           => apiClient.patch(`/admin/products/${id}/approve`),
    rejectProduct:  (id, data)     => apiClient.patch(`/admin/products/${id}/reject`, data),
    pendingProducts: (params)      => apiClient.get('/admin/products/pending', { params }),
    agents:         (params)       => apiClient.get('/admin/delivery-agents', { params }),
    agentDocs:      (id)           => apiClient.get(`/admin/delivery-agents/${id}/documents`),
    approveAgent:   (id)           => apiClient.patch(`/admin/delivery-agents/${id}/approve`),
    rejectAgent:    (id, data)     => apiClient.patch(`/admin/delivery-agents/${id}/reject`, data),
    auditLogs:      (params)       => apiClient.get('/admin/audit-logs', { params }),
    health:         ()             => apiClient.get('/admin/monitoring/health'),
    refund:         (id, data)     => apiClient.post(`/admin/orders/${id}/refund`, data),
    orders:         (params)       => apiClient.get('/admin/orders', { params }),
    getOrder:       (id)           => apiClient.get(`/admin/orders/${id}`),
    assignDelivery: (id, data)     => apiClient.post(`/admin/orders/${id}/assign`, data),
    cancelOrder:    (id)           => apiClient.post(`/admin/orders/${id}/cancel`),
  },
};
