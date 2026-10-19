import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { api } from '../../services/apiClient';

export const fetchOrders = createAsyncThunk('orders/fetch', async (params) => {
  const r = await api.orders.list(params);
  return { orders: r.data.data, meta: r.data.meta };
});

const ordersSlice = createSlice({
  name: 'orders',
  initialState: { orders:[], meta:null, isLoading:false, error:null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchOrders.pending,   (s)    => { s.isLoading = true; })
      .addCase(fetchOrders.fulfilled, (s, a) => { s.isLoading = false; s.orders = a.payload.orders; s.meta = a.payload.meta; })
      .addCase(fetchOrders.rejected,  (s, a) => { s.isLoading = false; s.error = a.error.message; });
  },
});
export default ordersSlice.reducer;
export const selectOrders = (s) => s.orders;
