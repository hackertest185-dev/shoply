import { useState, useEffect } from 'react';
import { api } from '../services/apiClient';
import { useAuth } from './useAuth';

export function useVerificationStatus() {
  const { user } = useAuth();
  const [status, setStatus]             = useState(null);
  const [rejectionReason, setReason]    = useState(null);
  const [loading, setLoading]           = useState(false);

  useEffect(() => {
    if (user?.role !== 'delivery') return;
    setLoading(true);
    api.delivery.verificationStatus()
      .then(r => {
        setStatus(r.data.data.verification_status);
        setReason(r.data.data.rejection_reason);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user]);

  return { verificationStatus: status, rejectionReason, loading };
}
