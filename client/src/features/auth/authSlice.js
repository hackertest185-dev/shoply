/**
 * features/auth/authSlice.js
 * Access token stored in Redux (memory only — NOT localStorage).
 * Refresh token lives exclusively in HttpOnly cookie managed by the browser.
 */
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { api } from '../../services/apiClient';

export const initializeAuth = createAsyncThunk('auth/initialize', async (_, { rejectWithValue }) => {
  try {
    // Attempt silent refresh — cookie sent automatically
    const refreshRes = await api.auth.refresh();
    const { access_token } = refreshRes.data.data;
    const meRes = await api.auth.me();
    return { accessToken: access_token, user: meRes.data.data };
  } catch {
    return rejectWithValue(null);
  }
});

export const logoutUser = createAsyncThunk('auth/logout', async (_, { dispatch }) => {
  try {
    await api.auth.logout();
  } catch { /* swallow — logout anyway */ }
  dispatch(logout());
});

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    accessToken:      null,
    user:             null,
    isAuthenticated:  false,
    isLoading:        true,   // true until initializeAuth settles
    error:            null,
  },
  reducers: {
    logout: (state) => {
      state.accessToken     = null;
      state.user            = null;
      state.isAuthenticated = false;
      state.isLoading       = false;
      state.error           = null;
    },
    tokenRefreshed: (state, action) => {
      state.accessToken = action.payload;
    },
    sessionEstablished: (state, action) => {
      state.accessToken = action.payload.accessToken;
      state.user = action.payload.user;
      state.isAuthenticated = Boolean(action.payload.user);
      state.isLoading = false;
      state.error = null;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // initializeAuth
      .addCase(initializeAuth.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(initializeAuth.fulfilled, (state, action) => {
        state.accessToken     = action.payload.accessToken;
        state.user            = action.payload.user;
        state.isAuthenticated = true;
        state.isLoading       = false;
      })
      .addCase(initializeAuth.rejected, (state) => {
        state.isAuthenticated = false;
        state.isLoading       = false;
      });
  },
});

export const { logout, tokenRefreshed, sessionEstablished, clearError } = authSlice.actions;
export default authSlice.reducer;

// Selectors
export const selectCurrentUser  = (state) => state.auth.user;
export const selectIsAuth        = (state) => state.auth.isAuthenticated;
export const selectAuthLoading   = (state) => state.auth.isLoading;
export const selectAuthError     = (state) => state.auth.error;
export const selectAccessToken   = (state) => state.auth.accessToken;
