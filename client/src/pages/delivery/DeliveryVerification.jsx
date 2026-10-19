/**
 * pages/delivery/DeliveryVerification.jsx  ★
 * Document upload page — accessible only to delivery agents with
 * verificationStatus: pending or rejected. Redirects approved agents.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/apiClient';
import { VerificationStatusBanner } from '../../components/VerificationStatusBanner';
import { DocumentUploadCard } from '../../components/DocumentUploadCard';
import { useVerificationStatus } from '../../hooks/useVerificationStatus';

export default function DeliveryVerification() {
  const navigate = useNavigate();
  const { verificationStatus, rejectionReason, loading } = useVerificationStatus();
  const [files, setFiles]       = useState({});
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess]   = useState(null);
  const [error, setError]       = useState(null);

  if (verificationStatus === 'approved') {
    navigate('/delivery/dashboard', { replace: true });
    return null;
  }

  const handleFileSelect = (name, file) => setFiles((prev) => ({ ...prev, [name]: file }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const required = ['national_id', 'driving_license', 'profile_photo'];
    const missing  = required.filter((k) => !files[k]);
    if (missing.length) {
      setError(`Please upload all required documents: ${missing.join(', ')}.`);
      return;
    }
    setUploading(true); setError(null);
    try {
      const form = new FormData();
      required.forEach((k) => form.append(k, files[k]));
      const res = await api.delivery.submitDocs(form);
      setSuccess(res.data.data.message);
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <div style={{ textAlign: 'center', padding: '80px', color: '#b3c2b9' }}>Loading...</div>;

  return (
    <main style={{ maxWidth: '640px', margin: '0 auto', padding: '40px 24px 80px' }}>
      <h1 style={{ fontFamily: 'Cormorant Garamond, Georgia, serif', fontSize: '32px', marginBottom: '8px' }}>
        Identity Verification
      </h1>
      <p style={{ color: '#b3c2b9', fontSize: '15px', marginBottom: '32px', lineHeight: 1.6 }}>
        To activate your delivery account, please upload the following documents.
        All files are encrypted and stored securely.
      </p>

      <VerificationStatusBanner status={verificationStatus} rejectionReason={rejectionReason} />

      {success ? (
        <div style={{ background: '#10b98111', border: '1px solid #10b98144', borderRadius: '12px', padding: '24px', textAlign: 'center' }}>
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>✅</div>
          <div style={{ fontWeight: 700, color: '#10b981', marginBottom: '8px' }}>Documents Submitted</div>
          <div style={{ color: '#b3c2b9', fontSize: '14px' }}>{success}</div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <DocumentUploadCard
            label="National ID"       name="national_id"
            accept=".pdf,.jpg,.jpeg,.png"
            status={verificationStatus === 'rejected' ? 'rejected' : verificationStatus === 'pending' ? 'pending' : 'none'}
            onFileSelect={handleFileSelect} uploading={uploading}
          />
          <DocumentUploadCard
            label="Driving License"   name="driving_license"
            accept=".pdf,.jpg,.jpeg,.png"
            status={verificationStatus === 'rejected' ? 'rejected' : verificationStatus === 'pending' ? 'pending' : 'none'}
            onFileSelect={handleFileSelect} uploading={uploading}
          />
          <DocumentUploadCard
            label="Profile Photo"     name="profile_photo"
            accept=".jpg,.jpeg,.png"
            status={verificationStatus === 'rejected' ? 'rejected' : verificationStatus === 'pending' ? 'pending' : 'none'}
            onFileSelect={handleFileSelect} uploading={uploading}
          />

          {error && (
            <div style={{ background: '#ef444411', border: '1px solid #ef444444', borderRadius: '8px', padding: '12px 16px', fontSize: '13px', color: '#ef4444' }}>
              {error}
            </div>
          )}

          <button type="submit" disabled={uploading} style={{
            background: '#dfbd89', border: 'none', borderRadius: '10px',
            padding: '14px', fontSize: '15px', fontWeight: 700, cursor: 'pointer',
            color: '#091917', opacity: uploading ? 0.6 : 1, marginTop: '8px',
          }}>
            {uploading ? 'Uploading...' : 'Submit Documents'}
          </button>
        </form>
      )}
    </main>
  );
}
