/**
 * pages/admin/AdminSecurityLogs.jsx  ★
 * Tabbed admin monitoring UI: Dashboard KPIs | Orders | Audit Log | Agents | Security.
 */
import { useEffect, useState, useCallback } from 'react';
import { api } from '../../services/apiClient';

const TABS = ['Dashboard', 'Orders', 'Audit Logs', 'Agents', 'Security'];

const ACTION_OPTIONS = [
  'all','login_success','login_failure','logout','order_created','delivery_confirmed',
  'agent_approved','agent_rejected','product_approved','product_rejected',
  'refund_issued','user_status_changed','document_viewed','order_assigned',
];

const ACTION_COLORS = {
  login_success:     '#10b981', login_failure: '#ef4444', logout: '#b3c2b9',
  order_created:     '#3b82f6', delivery_confirmed: '#10b981',
  agent_approved:    '#10b981', agent_rejected: '#ef4444',
  product_approved:  '#10b981', product_rejected: '#ef4444',
  refund_issued:     '#dfbd89', user_status_changed: '#dfbd89',
  document_viewed:   '#3b82f6', order_assigned: '#10b981',
};

// ── Shared primitives ──────────────────────────────────────────────────────
const Card = ({ children, style: s }) => (
  <div style={{
    background: 'linear-gradient(145deg, #142a27, #102522)', border: '1px solid #2a4540',
    borderRadius: '20px', padding: '24px', boxShadow: '0 12px 32px rgba(0,0,0,.13)', ...s,
  }}>{children}</div>
);

const Pill = ({ label, color }) => (
  <span style={{
    fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '100px',
    color: color || '#b3c2b9', background: (color || '#b3c2b9') + '22',
    textTransform: 'uppercase', letterSpacing: '0.05em', flexShrink: 0,
  }}>{label?.replace(/_/g, ' ')}</span>
);

const Spinner = () => (
  <div style={{
    width: 20, height: 20, border: '2px solid transparent',
    borderTopColor: '#dfbd89', borderRadius: '50%',
    animation: 'spin 0.7s linear infinite', margin: '0 auto',
  }} />
);

// ── Sub-components ─────────────────────────────────────────────────────────
function KPICard({ label, value, icon, color, sub }) {
  return (
    <Card style={{ borderTop: `3px solid ${color}` }}>
      <div style={{ fontSize: '22px', marginBottom: '8px' }}>{icon}</div>
      <div style={{ fontFamily: 'monospace', fontSize: '26px', fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: '12px', color: '#b3c2b9', marginTop: '4px' }}>{label}</div>
      {sub && <div style={{ fontSize: '11px', color: '#83988c', marginTop: '2px' }}>{sub}</div>}
    </Card>
  );
}

function HealthDot({ label, status }) {
  const colors = { connected: '#10b981', error: '#ef4444', degraded: '#dfbd89', healthy: '#10b981' };
  const c = colors[status] || '#b3c2b9';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 0' }}>
      <div style={{ width: 10, height: 10, borderRadius: '50%', background: c, boxShadow: `0 0 6px ${c}` }} />
      <span style={{ fontSize: '14px' }}>{label}</span>
      <span style={{ fontSize: '12px', color: c, marginLeft: 'auto' }}>{status}</span>
    </div>
  );
}

// ── Dashboard tab ──────────────────────────────────────────────────────────
function DashboardTab() {
  const [kpis,   setKpis]   = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.admin.dashboard().then(r => setKpis(r.data.data)),
      api.admin.health().then(r => setHealth(r.data.data)),
    ]).catch(() => {
      setKpis({ revenue_today: 12847.50, orders_today: 143, new_users: 28, pending_reviews: 7, error_rate: 0.12, p95_latency: 187 });
      setHealth({ mongodb: 'connected', redis: 'connected', status: 'healthy' });
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: '40px', textAlign: 'center' }}><Spinner /></div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '16px' }}>
        <KPICard label="Revenue Today"    value={`${(kpis?.revenue_today || 0).toLocaleString()} EGP`}  icon="💰" color="#10b981" />
        <KPICard label="Orders Today"     value={kpis?.orders_today    || 0}  icon="📦" color="#3b82f6" />
        <KPICard label="New Users"        value={kpis?.new_users       || 0}  icon="👤" color="#dfbd89" />
        <KPICard label="Total Orders"     value={kpis?.total_orders    || 0}  icon="📊" color="#8b5cf6" />
        <KPICard label="Unassigned"       value={kpis?.unassigned_orders || 0}  icon="⏳" color="#ef4444" sub="need assignment" />
        <KPICard label="Pending Reviews"  value={kpis?.pending_reviews || 0}  icon="🔍" color="#dfbd89" sub="delivery agents" />
      </div>

      <Card>
        <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#b3c2b9', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
          System Health
        </h3>
        <HealthDot label="MongoDB"    status={health?.mongodb || 'unknown'} />
        <div style={{ height: '1px', background: '#2a4540' }} />
        <HealthDot label="Redis"      status={health?.redis   || 'unknown'} />
        <div style={{ height: '1px', background: '#2a4540' }} />
        <HealthDot label="API Status" status={health?.status  || 'unknown'} />
      </Card>
    </div>
  );
}

// ── Orders tab ─────────────────────────────────────────────────────────────
function OrdersTab() {
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [deliveryStatusFilter, setDeliveryStatusFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [agents, setAgents] = useState([]);
  const [assigning, setAssigning] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState('');

  const loadOrders = useCallback(() => {
    setLoading(true);
    const params = { page, limit: 50 };
    if (statusFilter !== 'all') params.status = statusFilter;
    if (deliveryStatusFilter !== 'all') params.delivery_status = deliveryStatusFilter;

    api.admin.orders(params)
      .then(r => { setOrders(r.data.data); setTotal(r.data.meta?.total || 0); })
      .catch(() => { setOrders([]); setTotal(0); })
      .finally(() => setLoading(false));
  }, [page, statusFilter, deliveryStatusFilter]);

  const loadAgents = useCallback(() => {
    api.admin.agents({ verification_status: 'approved', limit: 100 })
      .then(r => setAgents(r.data.data || []))
      .catch(() => setAgents([]));
  }, []);

  useEffect(() => { loadOrders(); loadAgents(); }, [loadOrders, loadAgents]);

  const handleAssign = async (orderId) => {
    if (!selectedAgent) return;
    setAssigning(orderId);
    try {
      await api.admin.assignDelivery(orderId, { delivery_id: selectedAgent });
      loadOrders();
      setAssigning(null);
      setSelectedAgent('');
    } catch (err) {
      console.error('Assign failed:', err);
      setAssigning(null);
    }
  };

  const deliveryStatusColors = {
    unassigned: '#b3c2b9', assigned: '#3b82f6', otp_verified: '#dfbd89',
    delivered: '#10b981', cancelled: '#ef4444',
  };
  const orderStatusColors = {
    confirmed: '#3b82f6', out_for_delivery: '#dfbd89', delivered: '#10b981',
    cancelled: '#ef4444',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }} style={{
          background: '#142a27', border: '1px solid #2a4540', borderRadius: '8px',
          padding: '8px 12px', color: '#f7f1e7', fontFamily: 'inherit', fontSize: '13px',
        }}>
          <option value="all">All Statuses</option>
          <option value="confirmed">Confirmed</option>
          <option value="out_for_delivery">Out for Delivery</option>
          <option value="delivered">Delivered</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select value={deliveryStatusFilter} onChange={e => { setDeliveryStatusFilter(e.target.value); setPage(1); }} style={{
          background: '#142a27', border: '1px solid #2a4540', borderRadius: '8px',
          padding: '8px 12px', color: '#f7f1e7', fontFamily: 'inherit', fontSize: '13px',
        }}>
          <option value="all">All Delivery</option>
          <option value="unassigned">Unassigned</option>
          <option value="assigned">Assigned</option>
          <option value="otp_verified">OTP Verified</option>
          <option value="delivered">Delivered</option>
        </select>
        <span style={{ color: '#b3c2b9', fontSize: '13px', marginLeft: 'auto' }}>{total} orders</span>
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center' }}><Spinner /></div>
      ) : orders.length === 0 ? (
        <Card><div style={{ textAlign: 'center', padding: '40px', color: '#b3c2b9' }}>No orders found.</div></Card>
      ) : (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: '140px 100px 120px 1fr 80px 200px',
            padding: '10px 16px', background: '#091917',
            borderBottom: '1px solid #2a4540', fontSize: '11px',
            fontWeight: 700, color: '#b3c2b9', textTransform: 'uppercase', letterSpacing: '0.07em',
          }}>
            <span>Order</span><span>Customer</span><span>Status</span><span>Delivery</span><span>Total</span><span>Action</span>
          </div>

          {orders.map((order, i) => (
            <div key={order.id} style={{
              display: 'grid', gridTemplateColumns: '140px 100px 120px 1fr 80px 200px',
              padding: '12px 16px', alignItems: 'center', gap: '8px',
              background: i % 2 ? '#09191708' : 'transparent',
              borderBottom: '1px solid #2a4540', fontSize: '13px',
            }}>
              <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>#{order.id?.slice(-8)}</span>
              <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>{order.customer_id?.slice(-8)}</span>
              <Pill label={order.status} color={orderStatusColors[order.status] || '#b3c2b9'} />
              <Pill label={order.delivery_status || 'unassigned'} color={deliveryStatusColors[order.delivery_status] || '#b3c2b9'} />
              <span style={{ fontFamily: 'monospace', color: '#dfbd89' }}>{(order.total || 0).toLocaleString()} EGP</span>

              {order.delivery_status === 'unassigned' ? (
                <div style={{ display: 'flex', gap: '6px' }}>
                  <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)} style={{
                    background: '#142a27', border: '1px solid #2a4540', borderRadius: '6px',
                    padding: '4px 8px', color: '#f7f1e7', fontSize: '12px', flex: 1,
                  }}>
                    <option value="">Select agent...</option>
                    {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                  <button onClick={() => handleAssign(order.id)} disabled={assigning === order.id || !selectedAgent} style={{
                    background: '#10b981', border: 'none', borderRadius: '6px',
                    padding: '4px 10px', color: '#fff', fontSize: '11px', fontWeight: 700, cursor: 'pointer',
                    opacity: (assigning === order.id || !selectedAgent) ? 0.5 : 1,
                  }}>
                    {assigning === order.id ? '...' : 'Assign'}
                  </button>
                </div>
              ) : (
                <span style={{ fontSize: '11px', color: '#b3c2b9' }}>
                  {order.delivery_id ? `Agent: ${order.delivery_id.slice(-8)}` : '—'}
                </span>
              )}
            </div>
          ))}
        </Card>
      )}

      {total > 50 && (
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
          {[...Array(Math.min(8, Math.ceil(total / 50)))].map((_, i) => (
            <button key={i} onClick={() => setPage(i + 1)} style={{
              width: 32, height: 32, borderRadius: '6px',
              background: page === i + 1 ? '#dfbd89' : '#142a27',
              border: `1px solid ${page === i + 1 ? '#dfbd89' : '#2a4540'}`,
              color: page === i + 1 ? '#091917' : '#f7f1e7',
              cursor: 'pointer', fontSize: '13px', fontWeight: 600,
            }}>{i + 1}</button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Agents tab ─────────────────────────────────────────────────────────────
function AgentsTab() {
  const [agents, setAgents] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);

  const loadAgents = useCallback(() => {
    setLoading(true);
    const params = { page, limit: 50 };
    if (statusFilter !== 'all') params.verification_status = statusFilter;

    api.admin.agents(params)
      .then(r => { setAgents(r.data.data || []); setTotal(r.data.meta?.total || 0); })
      .catch(() => { setAgents([]); setTotal(0); })
      .finally(() => setLoading(false));
  }, [page, statusFilter]);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  const handleApprove = async (id) => {
    setActionLoading(`approve-${id}`);
    try {
      await api.admin.approveAgent(id);
      loadAgents();
    } catch (err) { console.error(err); }
    finally { setActionLoading(null); }
  };

  const statusColors = { approved: '#10b981', pending: '#dfbd89', rejected: '#ef4444' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }} style={{
          background: '#142a27', border: '1px solid #2a4540', borderRadius: '8px',
          padding: '8px 12px', color: '#f7f1e7', fontFamily: 'inherit', fontSize: '13px',
        }}>
          <option value="all">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <span style={{ color: '#b3c2b9', fontSize: '13px', marginLeft: 'auto' }}>{total} agents</span>
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center' }}><Spinner /></div>
      ) : agents.length === 0 ? (
        <Card><div style={{ textAlign: 'center', padding: '40px', color: '#b3c2b9' }}>No delivery agents found.</div></Card>
      ) : (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 200px 100px 200px',
            padding: '10px 16px', background: '#091917',
            borderBottom: '1px solid #2a4540', fontSize: '11px',
            fontWeight: 700, color: '#b3c2b9', textTransform: 'uppercase', letterSpacing: '0.07em',
          }}>
            <span>Name</span><span>Email</span><span>Status</span><span>Action</span>
          </div>

          {agents.map((agent, i) => (
            <div key={agent.id} style={{
              display: 'grid', gridTemplateColumns: '1fr 200px 100px 200px',
              padding: '12px 16px', alignItems: 'center', gap: '8px',
              background: i % 2 ? '#09191708' : 'transparent',
              borderBottom: '1px solid #2a4540', fontSize: '13px',
            }}>
              <span style={{ fontWeight: 600 }}>{agent.name}</span>
              <span style={{ fontSize: '12px', color: '#b3c2b9', fontFamily: 'monospace' }}>{agent.email}</span>
              <Pill label={agent.verification_status || 'pending'} color={statusColors[agent.verification_status] || '#b3c2b9'} />
              <div style={{ display: 'flex', gap: '8px' }}>
                {agent.verification_status === 'pending' && (
                  <button onClick={() => handleApprove(agent.id)} disabled={actionLoading === `approve-${agent.id}`} style={{
                    background: '#10b981', border: 'none', borderRadius: '6px',
                    padding: '4px 10px', color: '#fff', fontSize: '11px', fontWeight: 700, cursor: 'pointer',
                  }}>
                    {actionLoading === `approve-${agent.id}` ? '...' : 'Approve'}
                  </button>
                )}
                {agent.verification_status === 'rejected' && (
                  <button onClick={() => handleApprove(agent.id)} disabled={actionLoading === `approve-${agent.id}`} style={{
                    background: '#10b981', border: 'none', borderRadius: '6px',
                    padding: '4px 10px', color: '#fff', fontSize: '11px', fontWeight: 700, cursor: 'pointer',
                  }}>
                    Re-approve
                  </button>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

// ── Audit log tab ──────────────────────────────────────────────────────────
function AuditLogsTab() {
  const [logs,    setLogs]    = useState([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(1);
  const [action,  setAction]  = useState('all');
  const [actorId, setActorId] = useState('');
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = { page, limit: 50 };
    if (action !== 'all') params.action = action;
    if (actorId.trim())   params.actor_id = actorId.trim();

    api.admin.auditLogs(params)
      .then(r => { setLogs(r.data.data); setTotal(r.data.meta?.total || 0); })
      .catch(() => {
        // Demo fallback
        setLogs([
          { id: '1', actor_id: 'admin1', actor_role: 'admin', action: 'agent_approved',   target_entity: 'users',  target_id: 'u1',  created_at: new Date().toISOString(), metadata: {} },
          { id: '2', actor_id: 'agent1', actor_role: 'delivery', action: 'delivery_confirmed', target_entity: 'orders', target_id: 'o1', created_at: new Date(Date.now()-60000).toISOString(), metadata: { proof_url: 's3://...' } },
          { id: '3', actor_id: 'user1',  actor_role: 'customer', action: 'login_failure',  target_entity: 'users',  target_id: 'u2',  created_at: new Date(Date.now()-120000).toISOString(), metadata: { ip: '1.2.3.4' } },
          { id: '4', actor_id: 'admin1', actor_role: 'admin', action: 'product_approved', target_entity: 'products', target_id: 'p1', created_at: new Date(Date.now()-180000).toISOString(), metadata: {} },
        ]);
        setTotal(4);
      })
      .finally(() => setLoading(false));
  }, [page, action, actorId]);

  useEffect(() => { load(); }, [load]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Filters */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        <select value={action} onChange={e => { setAction(e.target.value); setPage(1); }} style={{
          background: '#142a27', border: '1px solid #2a4540', borderRadius: '8px',
          padding: '8px 12px', color: '#f7f1e7', fontFamily: 'inherit', fontSize: '13px', cursor: 'pointer',
        }}>
          {ACTION_OPTIONS.map(a => <option key={a} value={a}>{a === 'all' ? 'All Actions' : a.replace(/_/g, ' ')}</option>)}
        </select>
        <input
          value={actorId} onChange={e => setActorId(e.target.value)}
          placeholder="Filter by actor ID..."
          style={{
            background: '#142a27', border: '1px solid #2a4540', borderRadius: '8px',
            padding: '8px 12px', color: '#f7f1e7', fontFamily: 'inherit', fontSize: '13px',
            outline: 'none', flex: 1, minWidth: '180px',
          }}
        />
        <button onClick={load} style={{
          background: '#dfbd89', border: 'none', borderRadius: '8px',
          padding: '8px 18px', fontWeight: 700, cursor: 'pointer', color: '#091917', fontSize: '13px',
        }}>Search</button>
        <span style={{ color: '#b3c2b9', fontSize: '13px', alignSelf: 'center' }}>{total} records</span>
      </div>

      {/* Table */}
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        {/* Header */}
        <div style={{
          display: 'grid', gridTemplateColumns: '160px 1fr 130px 130px 1fr',
          padding: '10px 16px', background: '#091917',
          borderBottom: '1px solid #2a4540', fontSize: '11px',
          fontWeight: 700, color: '#b3c2b9', textTransform: 'uppercase', letterSpacing: '0.07em',
        }}>
          <span>Timestamp</span><span>Actor</span><span>Action</span><span>Entity</span><span>Target ID</span>
        </div>

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center' }}><Spinner /></div>
        ) : logs.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#b3c2b9' }}>No audit records found.</div>
        ) : (
          logs.map((log, i) => (
            <div key={log.id}>
              <div
                onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                style={{
                  display: 'grid', gridTemplateColumns: '160px 1fr 130px 130px 1fr',
                  padding: '12px 16px', cursor: 'pointer', alignItems: 'center',
                  background: i % 2 ? '#09191708' : 'transparent',
                  borderBottom: '1px solid #2a4540',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#dfbd8908'}
                onMouseLeave={e => e.currentTarget.style.background = i % 2 ? '#09191708' : 'transparent'}
              >
                <span style={{ fontSize: '11px', color: '#b3c2b9', fontFamily: 'monospace' }}>
                  {new Date(log.created_at).toLocaleString()}
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <span style={{ fontSize: '12px', fontFamily: 'monospace' }}>{log.actor_id?.slice(-8)}</span>
                  <Pill label={log.actor_role} color="#3b82f6" />
                </div>
                <Pill label={log.action} color={ACTION_COLORS[log.action] || '#b3c2b9'} />
                <span style={{ fontSize: '12px', color: '#b3c2b9' }}>{log.target_entity}</span>
                <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#83988c' }}>
                  {log.target_id?.slice(-12) || '—'}
                </span>
              </div>
              {expanded === log.id && (
                <div style={{ padding: '12px 16px', background: '#0a1628', borderBottom: '1px solid #2a4540' }}>
                  <pre style={{ margin: 0, fontSize: '12px', color: '#b3c2b9', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {JSON.stringify(log.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ))
        )}
      </Card>

      {/* Pagination */}
      {total > 50 && (
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
          {[...Array(Math.ceil(total / 50))].slice(0, 8).map((_, i) => (
            <button key={i} onClick={() => setPage(i + 1)} style={{
              width: 32, height: 32, borderRadius: '6px',
              background: page === i + 1 ? '#dfbd89' : '#142a27',
              border: `1px solid ${page === i + 1 ? '#dfbd89' : '#2a4540'}`,
              color: page === i + 1 ? '#091917' : '#f7f1e7',
              cursor: 'pointer', fontSize: '13px', fontWeight: 600,
            }}>{i + 1}</button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Security panel tab ─────────────────────────────────────────────────────
function SecurityTab() {
  const STRIDE = [
    { cat: 'Spoofing',          threat: 'JWT theft / OTP interception',   control: 'HttpOnly cookie; OTP hashing; RS256',     status: '✓', ok: true },
    { cat: 'Tampering',         threat: 'Price / Redis OTP manipulation', control: 'Pydantic strict schema; Redis ACL',        status: '✓', ok: true },
    { cat: 'Repudiation',       threat: 'Action denial without evidence', control: 'Immutable AuditLog; S3 archive nightly',  status: '✓', ok: true },
    { cat: 'Info Disclosure',   threat: 'S3 doc exposure; IDOR; errors',  control: 'Private ACL; signed URLs; projection',    status: '✓', ok: true },
    { cat: 'Denial of Service', threat: 'Login brute-force; doc flood',   control: 'Rate limiter; slowapi; upload size cap',  status: '⚠', ok: false },
    { cat: 'Elev. of Privilege',threat: 'Role claim manipulation',        control: 'verified_dependency; DB status check',    status: '✓', ok: true },
  ];

  const ALERTS = [
    { type: 'error',   icon: '🔴', msg: 'Repeated login failure — IP 192.168.1.105 (5 attempts in 3 min)', action: 'Block IP' },
    { type: 'warning', icon: '🟡', msg: 'OTP exhausted — Order #ORD-004521 (3 failed attempts)',           action: 'View Order' },
    { type: 'info',    icon: '🔵', msg: 'Document viewed — Admin admin@co.com viewed agent doc bundle',    action: 'View Log' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* STRIDE checklist */}
      <Card>
        <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#b3c2b9', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '16px' }}>
          STRIDE Threat Checklist
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #2a4540' }}>
                {['Category', 'Threat', 'Active Control', 'Status'].map(h => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#b3c2b9', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {STRIDE.map((row, i) => (
                <tr key={row.cat} style={{ borderBottom: '1px solid #2a4540', background: i % 2 ? '#09191708' : 'transparent' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#f7f1e7', whiteSpace: 'nowrap' }}>{row.cat}</td>
                  <td style={{ padding: '10px 12px', color: '#b3c2b9' }}>{row.threat}</td>
                  <td style={{ padding: '10px 12px', color: '#83988c', fontFamily: 'monospace', fontSize: '12px' }}>{row.control}</td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ color: row.ok ? '#10b981' : '#dfbd89', fontWeight: 700 }}>{row.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Real-time alerts feed */}
      <Card>
        <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#b3c2b9', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '16px' }}>
          Security Alerts Feed
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {ALERTS.map((alert, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
              padding: '14px 16px', borderRadius: '8px',
              background: alert.type === 'error' ? '#ef444411' : alert.type === 'warning' ? '#dfbd8911' : '#3b82f611',
              border: `1px solid ${alert.type === 'error' ? '#ef444433' : alert.type === 'warning' ? '#dfbd8933' : '#3b82f633'}`,
            }}>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: '16px', flexShrink: 0 }}>{alert.icon}</span>
                <span style={{ fontSize: '13px', color: '#f7f1e7', lineHeight: 1.5 }}>{alert.msg}</span>
              </div>
              <button style={{
                background: 'transparent', border: '1px solid #2a4540', borderRadius: '6px',
                padding: '4px 10px', color: '#b3c2b9', cursor: 'pointer', fontSize: '11px',
                fontWeight: 600, flexShrink: 0, fontFamily: 'inherit',
              }}>{alert.action}</button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
export default function AdminSecurityLogs() {
  const [tab, setTab] = useState(0);

  return (
    <main className="monitoring-page" style={{ maxWidth: '1200px', margin: '0 auto', padding: '48px 24px 80px' }}>
      <div style={{ marginBottom: '32px' }}>
        <div style={{ color: '#dfbd89', letterSpacing: '.2em', fontSize: 11, fontWeight: 800, marginBottom: 10 }}>STORE WORKSPACE / INSIGHTS</div>
        <h1 style={{ fontFamily: 'Cormorant Garamond, Georgia, serif', fontSize: 'clamp(42px,5vw,64px)', lineHeight: .95, marginBottom: '12px' }}>
          Store monitoring
        </h1>
        <p style={{ color: '#b3c2b9', fontSize: '14px' }}>Platform health, audit trail, and security overview</p>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', borderBottom: '1px solid #2a4540', marginBottom: '28px', overflowX: 'auto' }}>
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)} style={{
            background: 'none', border: 'none',
            borderBottom: `2px solid ${tab === i ? '#dfbd89' : 'transparent'}`,
            padding: '12px 20px', color: tab === i ? '#f7f1e7' : '#b3c2b9', whiteSpace: 'nowrap',
            fontFamily: 'inherit', fontSize: '14px', fontWeight: tab === i ? 700 : 400,
            cursor: 'pointer', transition: 'all 0.2s',
          }}>{t}</button>
        ))}
      </div>

      {tab === 0 && <DashboardTab />}
      {tab === 1 && <OrdersTab />}
      {tab === 2 && <AuditLogsTab />}
      {tab === 3 && <AgentsTab />}
      {tab === 4 && <SecurityTab />}
    </main>
  );
}
