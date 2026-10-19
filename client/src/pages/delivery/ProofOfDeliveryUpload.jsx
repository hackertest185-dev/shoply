/**
 * pages/delivery/ProofOfDeliveryUpload.jsx  ★
 * OTP entry + proof image upload — final delivery step.
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { OTPInput } from '../../components/OTPInput';
import { api } from '../../services/apiClient';

export default function ProofOfDeliveryUpload() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [otp,        setOtp]        = useState('');
  const [otpVerified, setOtpVerified] = useState(false);
  const [otpError,    setOtpError]    = useState('');
  const [attemptsLeft, setAttemptsLeft] = useState(3);
  const [proofFile,  setProofFile]  = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [done,       setDone]       = useState(false);
  const [error,      setError]      = useState('');

  const handleVerifyOtp = async () => {
    if (otp.length !== 4) { setOtpError('Enter all 4 digits.'); return; }
    setLoading(true); setOtpError('');
    try {
      await api.delivery.verifyOtp(orderId, { otp });
      setOtpVerified(true);
    } catch (err) {
      const errData = err.response?.data?.error;
      if (errData?.code === 'OTP_LOCKED') {
        setOtpError('Too many attempts. A new OTP was sent to the customer.');
        setAttemptsLeft(0);
      } else {
        setAttemptsLeft(errData?.attempts_remaining ?? attemptsLeft - 1);
        setOtpError(`Incorrect OTP. ${errData?.attempts_remaining ?? ''} attempt(s) remaining.`);
      }
      setOtp('');
    } finally { setLoading(false); }
  };

  const handleUploadProof = async () => {
    if (!proofFile) { setError('Please select a photo.'); return; }
    setLoading(true); setError('');
    try {
      const form = new FormData();
      form.append('proof_photo', proofFile);
      await api.delivery.uploadProof(orderId, form);
      setDone(true);
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Upload failed.');
    } finally { setLoading(false); }
  };

  if (done) return (
    <main style={{ maxWidth: '520px', margin: '80px auto', padding: '0 24px', textAlign: 'center' }}>
      <div style={{ fontSize: '64px', marginBottom: '16px' }}>✅</div>
      <h2 style={{ fontFamily: 'Cormorant Garamond, Georgia, serif', fontSize: '28px', marginBottom: '12px' }}>Delivery Confirmed</h2>
      <p style={{ color: '#b3c2b9', marginBottom: '24px' }}>The customer has been notified.</p>
      <button onClick={() => navigate('/delivery/dashboard')} style={{
        background: '#dfbd89', border: 'none', borderRadius: '10px',
        padding: '12px 28px', fontWeight: 700, cursor: 'pointer', color: '#091917',
      }}>← Back to Dashboard</button>
    </main>
  );

  return (
    <main style={{ maxWidth: '520px', margin: '0 auto', padding: '40px 24px 80px' }}>
      <button onClick={() => navigate(-1)} style={{
        background: 'none', border: 'none', color: '#b3c2b9', cursor: 'pointer',
        fontSize: '14px', marginBottom: '24px', fontFamily: 'inherit',
      }}>← Back</button>

      <h1 style={{ fontFamily: 'Cormorant Garamond, Georgia, serif', fontSize: '28px', marginBottom: '8px' }}>Confirm Delivery</h1>
      <p style={{ color: '#b3c2b9', marginBottom: '32px' }}>Order #{orderId?.slice(-8)}</p>

      {/* Step 1: OTP */}
      <div style={{ background: '#142a27', border: '1px solid #2a4540', borderRadius: '12px', padding: '24px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
          <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: otpVerified ? '#10b981' : '#dfbd89', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px', fontWeight: 800, color: '#091917' }}>
            {otpVerified ? '✓' : '1'}
          </div>
          <span style={{ fontWeight: 700 }}>Enter Customer OTP</span>
        </div>
        {!otpVerified ? (
          <>
            <OTPInput value={otp} onChange={setOtp} disabled={loading} error={otpError} />
            <button onClick={handleVerifyOtp} disabled={loading || otp.length < 4 || attemptsLeft === 0} style={{
              marginTop: '16px', width: '100%', background: '#dfbd89', border: 'none',
              borderRadius: '8px', padding: '12px', fontWeight: 700, cursor: 'pointer',
              color: '#091917', opacity: (loading || attemptsLeft === 0) ? 0.5 : 1,
            }}>
              {loading ? 'Verifying...' : 'Verify OTP'}
            </button>
          </>
        ) : (
          <p style={{ color: '#10b981', fontWeight: 600 }}>✓ OTP verified successfully</p>
        )}
      </div>

      {/* Step 2: Proof photo */}
      <div style={{
        background: '#142a27', border: '1px solid #2a4540', borderRadius: '12px', padding: '24px',
        opacity: otpVerified ? 1 : 0.4, pointerEvents: otpVerified ? 'auto' : 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
          <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: '#2a4540', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px', fontWeight: 800, color: '#b3c2b9' }}>2</div>
          <span style={{ fontWeight: 700 }}>Upload Proof Photo</span>
        </div>
        <input type="file" accept="image/jpeg,image/png" onChange={(e) => setProofFile(e.target.files?.[0])}
          style={{ width: '100%', marginBottom: '12px', color: '#b3c2b9' }} />
        {proofFile && <p style={{ fontSize: '13px', color: '#dfbd89' }}>Selected: {proofFile.name}</p>}
        {error && <p style={{ fontSize: '13px', color: '#ef4444' }}>{error}</p>}
        <button onClick={handleUploadProof} disabled={loading || !proofFile} style={{
          marginTop: '12px', width: '100%', background: '#10b981', border: 'none',
          borderRadius: '8px', padding: '12px', fontWeight: 700, cursor: 'pointer',
          color: '#fff', opacity: (!proofFile || loading) ? 0.5 : 1,
        }}>
          {loading ? 'Uploading...' : 'Confirm Delivery'}
        </button>
      </div>
    </main>
  );
}
