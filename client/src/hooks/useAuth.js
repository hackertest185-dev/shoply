/**
 * hooks/useAuth.js
 * Convenience hook — reads auth state from Redux and exposes a logout function.
 * logoutUser is an async thunk (calls API then clears state), so it must be
 * dispatched — wrapping it here keeps call sites clean.
 */
import { useSelector, useDispatch } from 'react-redux';
import {
  selectCurrentUser,
  selectIsAuth,
  selectAuthLoading,
  selectAuthError,
  logoutUser,
} from '../features/auth/authSlice';

export function useAuth() {
  const dispatch = useDispatch();

  return {
    user:            useSelector(selectCurrentUser),
    isAuthenticated: useSelector(selectIsAuth),
    isLoading:       useSelector(selectAuthLoading),
    error:           useSelector(selectAuthError),
    // dispatch the async thunk — calls POST /auth/logout then clears Redux state
    logout: () => dispatch(logoutUser()),
  };
}
