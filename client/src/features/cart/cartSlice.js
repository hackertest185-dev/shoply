import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { api } from '../../services/apiClient';

export const fetchCart    = createAsyncThunk('cart/fetch',    async () => { const r = await api.cart.get();                      return r.data.data; });
export const addToCart    = createAsyncThunk('cart/add',      async (item) => { const r = await api.cart.addItem(item);         return r.data.data; });
export const updateCart   = createAsyncThunk('cart/update',   async ({ productId, data }) => { const r = await api.cart.updateItem(productId, data); return r.data.data; });
export const removeFromCart = createAsyncThunk('cart/remove', async (productId) => { const r = await api.cart.removeItem(productId); return r.data.data; });
export const clearCart    = createAsyncThunk('cart/clear',    async () => { await api.cart.clear(); return { items: [], summary: { item_count:0, subtotal:0, tax_estimate:0, total:0 }, warnings:[] }; });

const cartSlice = createSlice({
  name: 'cart',
  initialState: { items:[], summary:{ item_count:0, subtotal:0, tax_estimate:0, total:0 }, warnings:[], isLoading:false, error:null },
  reducers: { resetCart: (state) => { state.items=[]; state.summary={ item_count:0, subtotal:0, tax_estimate:0, total:0 }; } },
  extraReducers: (builder) => {
    const handle = (thunk) => {
      builder.addCase(thunk.pending,   (s)    => { s.isLoading = true; s.error = null; });
      builder.addCase(thunk.fulfilled, (s, a) => { s.isLoading = false; Object.assign(s, a.payload); });
      builder.addCase(thunk.rejected,  (s, a) => { s.isLoading = false; s.error = a.error.message; });
    };
    [fetchCart, addToCart, updateCart, removeFromCart, clearCart].forEach(handle);
  },
});
export const { resetCart } = cartSlice.actions;
export default cartSlice.reducer;
export const selectCart      = (s) => s.cart;
export const selectCartCount = (s) => s.cart.items.reduce((a, i) => a + i.qty, 0);
export const selectCartTotal = (s) => s.cart.summary.total;
