import { useSelector, useDispatch } from 'react-redux';
import { selectCart, selectCartCount, selectCartTotal, addToCart, removeFromCart, clearCart, fetchCart } from '../features/cart/cartSlice';
import { useEffect } from 'react';
import { useAuth } from './useAuth';

export function useCart() {
  const dispatch = useDispatch();
  const { isAuthenticated } = useAuth();
  const cart = useSelector(selectCart);

  useEffect(() => {
    if (isAuthenticated) dispatch(fetchCart());
  }, [isAuthenticated, dispatch]);

  return {
    ...cart,
    count:  useSelector(selectCartCount),
    total:  useSelector(selectCartTotal),
    add:    (item)       => dispatch(addToCart(item)),
    remove: (productId)  => dispatch(removeFromCart(productId)),
    clear:  ()           => dispatch(clearCart()),
  };
}
