/**
 * components/DocumentUploadCard.jsx  ★
 * Single document upload field with status badge, file preview, and S3 progress.
 */
import { useEffect, useRef, useState } from 'react';

const STATUS_STYLES = {
  pending:  { color: '#dfbd89', bg: '#dfbd8922', label: 'Under Review' },
  approved: { color: '#10b981', bg: '#10b98122', label: 'Approved' },
  rejected: { color: '#ef4444', bg: '#ef444422', label: 'Rejected' },
  none:     { color: '#b3c2b9', bg: '#b3c2b922', label: 'Not Uploaded' },
};

export function DocumentUploadCard({ label, name, accept, status = 'none', onFileSelect, uploading }) {
  const fileRef = useRef();
  const [filename, setFilename] = useState(null);
  const [preview,  setPreview]  = useState(null);
  const style = STATUS_STYLES[status] || STATUS_STYLES.none;

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const handleChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    if (file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      setPreview(url);
    } else {
      setPreview(null);
    }
    onFileSelect(name, file);
  };

  return (
    <div style={{
      background: '#142a27', border: '1px solid #2a4540', borderRadius: '12px',
      padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '14px', fontWeight: 600 }}>{label}</span>
        <span style={{
          fontSize: '11px', fontWeight: 700, padding: '2px 8px',
          borderRadius: '100px', color: style.color, background: style.bg,
          textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          {style.label}
        </span>
      </div>

      {preview && (
        <img src={preview} alt="preview" style={{
          width: '100%', height: '120px', objectFit: 'cover',
          borderRadius: '8px', border: '1px solid #2a4540',
        }} />
      )}

      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={uploading}
        style={{
          background: filename ? '#dfbd8911' : 'transparent',
          border: `2px dashed ${filename ? '#dfbd89' : '#2a4540'}`,
          borderRadius: '8px', padding: '14px', cursor: 'pointer',
          color: filename ? '#dfbd89' : '#b3c2b9', fontSize: '13px',
          fontFamily: 'inherit', transition: 'all 0.2s', textAlign: 'center',
        }}
      >
        {uploading ? '⏳ Uploading...' : filename
          ? `✓ ${filename}`
          : `+ Select ${label}`}
      </button>

      <input
        ref={fileRef} type="file" name={name}
        accept={accept} onChange={handleChange}
        style={{ display: 'none' }}
      />
      <p style={{ fontSize: '11px', color: '#b3c2b9', margin: 0 }}>
        Accepted: {accept.replace(/,/g, ', ')} · Max 10MB
      </p>
    </div>
  );
}
