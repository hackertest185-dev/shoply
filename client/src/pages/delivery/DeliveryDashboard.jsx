/**
 * pages/delivery/DeliveryDashboard.jsx  ★
 * Order queue and stats for verified delivery agents.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/apiClient';

export default function DeliveryDashboard() {
  const navigate = useNavigate();
  const [orders,  setOrders]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(null);

  useEffect(() => {
    api.delivery.orders()
      .then((r) => setOrders(r.data.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleStartDelivery = async (orderId, e) => {
    e.stopPropagation();
    setStarting(orderId);
    try {
      await api.delivery.startDelivery(orderId);
      const res = await api.delivery.orders();
      setOrders(res.data.data || []);
    } catch (err) {
      console.error('Start delivery failed:', err);
    } finally {
      setStarting(null);
    }
  };

  const statusColor = { confirmed: '#86aeb3', out_for_delivery: '#dfbd89', delivered: '#10b981' };
  const deliveryStatusColor = { assigned: '#86aeb3', otp_verified: '#10b981' };

  return (
    <main style={{ maxWidth: '900px', margin: '0 auto', padding: '40px 24px 80px' }}>
      <div className="delivery-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '32px' }}>
        <div>
          <div style={{ color: 'var(--amber)', fontSize: 11, fontWeight: 800, letterSpacing: '.2em', marginBottom: 10 }}>SHOPLY DELIVERY</div>
          <h1 style={{ fontFamily: 'Cormorant Garamond, Georgia, serif', fontSize: 'clamp(38px, 5vw, 54px)', lineHeight: 1, marginBottom: '8px' }}>Delivery Dashboard</h1>
          <p style={{ color: '#b3c2b9', fontSize: '14px' }}>Your assigned order queue</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <div style={{ background: '#142a27', border: '1px solid #2a4540', borderRadius: '10px', padding: '16px 20px', textAlign: 'center' }}>
            <div style={{ fontFamily: 'monospace', fontSize: '24px', fontWeight: 700, color: '#dfbd89' }}>{orders.length}</div>
            <div style={{ fontSize: '12px', color: '#b3c2b9' }}>Assigned</div>
          </div>
          <div style={{ background: '#142a27', border: '1px solid #2a4540', borderRadius: '10px', padding: '16px 20px', textAlign: 'center' }}>
            <div style={{ fontFamily: 'monospace', fontSize: '24px', fontWeight: 700, color: '#10b981' }}>{orders.filter(o => o.delivery_status === 'otp_verified').length}</div>
            <div style={{ fontSize: '12px', color: '#b3c2b9' }}>OTP Verified</div>
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: '#b3c2b9' }}>Loading orders...</div>
      ) : orders.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '80px', color: '#b3c2b9' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>📦</div>
          <div style={{ fontFamily: 'Cormorant Garamond, Georgia, serif', fontSize: '22px', color: '#f7f1e7', marginBottom: '8px' }}>No orders assigned</div>
          <p>New orders will appear here when assigned to you.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {orders.map((order) => (
            <div key={order.id} className="delivery-order-card" style={{
              background: '#142a27', border: '1px solid #2a4540', borderRadius: '12px',
              padding: '20px 24px', transition: 'border-color 0.2s',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}
              onMouseEnter={(e) => e.currentTarget.style.borderColor = '#dfbd89'}
              onMouseLeave={(e) => e.currentTarget.style.borderColor = '#2a4540'}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>#{order.id?.slice(-8)}</span>
                  <span style={{
                    fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '100px',
                    color: statusColor[order.status] || '#b3c2b9',
                    background: (statusColor[order.status] || '#b3c2b9') + '22',
                    textTransform: 'uppercase',
                  }}>
                    {order.status?.replace(/_/g, ' ')}
                  </span>
                  {order.delivery_status === 'assigned' && order.status === 'confirmed' && (
                    <span style={{
                      fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '100px',
                      color: '#b3c2b9', background: '#b3c2b922', textTransform: 'uppercase',
                    }}>
                      Not Started
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '13px', color: '#b3c2b9' }}>
                  {order.shipping_address?.city || 'No address'}{order.shipping_address?.city && order.shipping_address?.state ? ', ' : ''}{order.shipping_address?.state || ''}
                </div>
              </div>
              <div className="delivery-order-action" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ fontFamily: 'monospace', fontSize: '18px', fontWeight: 700, color: '#dfbd89' }}>
                  {Number(order.total || 0).toLocaleString('en-EG')} EGP
                </div>
                {order.delivery_status === 'assigned' && order.status === 'confirmed' && (
                  <button onClick={(e) => handleStartDelivery(order.id, e)} disabled={starting === order.id} style={{
                    background: '#86aeb3', border: 'none', borderRadius: '8px',
                    padding: '8px 16px', color: '#fff', fontSize: '12px', fontWeight: 700,
                    cursor: 'pointer', opacity: starting === order.id ? 0.5 : 1,
                  }}>
                    {starting === order.id ? 'Starting...' : 'Start Delivery'}
                  </button>
                )}
                <button aria-label={`View order ${order.id?.slice(-8)}`} style={{ color: '#b3c2b9', fontSize: '20px', cursor: 'pointer', background: 'none', border: 0 }} onClick={() => navigate(`/delivery/orders/${order.id}`)}>›</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
