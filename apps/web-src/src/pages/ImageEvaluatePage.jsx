import { useState, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api';
import { Image as ImageIcon, Upload, X, RotateCcw, Info, FileImage } from 'lucide-react';
import ResultPanel from '../components/ResultPanel';
import FilePickInput from '../components/FilePickInput';
import {
  IMAGE_FORMAT_HINT,
  MAX_IMAGE_BYTES,
  prepareImageUpload,
  validateImageFile,
} from '../utils/imageFile';

function makeConvoId() {
  return `convo-${Date.now()}`;
}

function formatBytes(n) {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

function normalizeUploadFile(file) {
  if (!file) return null;
  return prepareImageUpload(file) || file;
}

function validateFile(file) {
  return validateImageFile(file);
}

/**
 * Image Evaluate page.
 * POST /guardrail/evaluate-image (multipart/form-data).
 * Fields: image (File) + conversation_id (string).
 */
export default function ImageEvaluatePage() {
  const { auth } = useAuth();
  const [file, setFile]         = useState(null);
  const [preview, setPreview]   = useState(null);
  const [convId, setConvId]     = useState(makeConvoId);
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);
  const [fileError, setFileError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  function selectFile(rawFile) {
    setFileError(null);
    setResult(null);
    setError(null);

    if (!rawFile) {
      setFile(null);
      setPreview(null);
      return;
    }

    const normalized = normalizeUploadFile(rawFile);
    const err = validateFile(normalized || rawFile);
    if (err || !normalized) {
      setFileError(err || 'Unsupported file type. Use PNG, JPEG, or WEBP.');
      setFile(null);
      setPreview(null);
      return;
    }

    setFile(normalized);
    const reader = new FileReader();
    reader.onload = (ev) => setPreview(ev.target.result);
    reader.readAsDataURL(normalized);
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!loading) setDragActive(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget === e.target) setDragActive(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (loading) return;
    selectFile(e.dataTransfer?.files?.[0] || null);
  }

  function clearFile() {
    setFile(null);
    setPreview(null);
    setFileError(null);
    setResult(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!auth || !file) return;

    const err = validateFile(file);
    if (err) { setFileError(err); return; }

    setLoading(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    const uploadFile = normalizeUploadFile(file) || file;
    fd.append('image', uploadFile, uploadFile.name);
    fd.append('conversation_id', convId);

    try {
      const data = await apiFetch('/guardrail/evaluate-image', {
        method: 'POST',
        body: fd,
        token: auth.token,
      });
      setResult(data);
    } catch (err) {
      if (err.type === 'unavailable' && err.body) {
        setResult(err.body);
        setError(`OCR temporarily unavailable: ${err.message}`);
      } else if (err.status === 400) {
        setError(err.message || 'Invalid or unsupported image.');
      } else {
        setError(err.message || 'Request failed.');
      }
    } finally {
      setLoading(false);
    }
  }

  const canSubmit = auth && file && !fileError && !loading;

  return (
    <div className="page-container">
      {/* ── Input card ── */}
      <div className="card glass">
        <div className="card-header">
          <div className="card-icon"><ImageIcon size={20} /></div>
          <div className="card-meta">
            <h2>Image Evaluate</h2>
            <p className="card-desc">
              Upload an image through the optical guardrail pipeline via{' '}
              <code>POST /guardrail/evaluate-image</code> (multipart).
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Conversation ID */}
          <div className="field">
            <label htmlFor="img-convid">Conversation ID</label>
            <div className="row">
              <input
                id="img-convid"
                type="text"
                value={convId}
                onChange={(e) => setConvId(e.target.value)}
                spellCheck="false"
                className="grow readonly"
              />
              <button
                type="button"
                className="btn ghost btn-sm"
                onClick={() => setConvId(makeConvoId())}
                title="Generate new conversation ID"
              >
                <RotateCcw size={12} /> New
              </button>
            </div>
          </div>

          {/* File picker */}
          <div className="field">
            <label htmlFor="img-file">Image ({IMAGE_FORMAT_HINT} · max 10 MB)</label>

            {!file ? (
              <FilePickInput
                inputRef={inputRef}
                id="img-file"
                disabled={loading}
                ariaLabel="Choose image file"
                wrapClassName={`file-drop-zone${dragActive ? ' is-drag-active' : ''}`}
                onFile={selectFile}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <FileImage size={20} style={{ marginBottom: 8, color: 'var(--text-muted)' }} />
                <div style={{ fontWeight: 500, fontSize: 13 }}>Click or drag an image here</div>
                <div style={{ fontSize: 12, marginTop: 4, color: 'var(--text-muted)' }}>
                  {IMAGE_FORMAT_HINT} · max {formatBytes(MAX_IMAGE_BYTES)}
                </div>
                <div style={{ fontSize: 11, marginTop: 8, color: 'var(--text-muted)' }}>
                  All files are shown in the picker — choose a PNG, JPEG, or WEBP image.
                </div>
              </FilePickInput>
            ) : (
              <div className="file-ready-panel">
                <div className="file-ready-header">
                  <span className="file-ready-badge">File loaded</span>
                  <button type="button" className="btn ghost btn-sm" onClick={clearFile}>
                    <X size={12} /> Clear
                  </button>
                </div>
                <p className="file-ready-name">
                  ContextGuard sees: <strong>{file.name}</strong> ({formatBytes(file.size)})
                </p>
                {preview && (
                  <div className="image-preview file-ready-preview">
                    <img src={preview} alt={`Preview of ${file.name}`} />
                  </div>
                )}
                <FilePickInput
                  inputRef={inputRef}
                  disabled={loading}
                  ariaLabel="Choose a different image"
                  wrapClassName="file-repick-wrap"
                  onFile={selectFile}
                >
                  <span className="btn ghost btn-sm">Choose a different image</span>
                </FilePickInput>
              </div>
            )}
            {fileError && <p className="error-text">{fileError}</p>}
          </div>

          <p className="hint muted" style={{ marginTop: 10 }}>
            Supported formats: {IMAGE_FORMAT_HINT} only (not PDF or Word documents).
            The image endpoint accepts <code>image</code> + <code>conversation_id</code> only.
          </p>

          <button
            type="submit"
            className="btn primary big"
            disabled={!canSubmit}
            aria-busy={loading}
          >
            {loading ? (
              <><span className="spinner-inline" /> Uploading…</>
            ) : (
              <><Upload size={15} /> Evaluate image</>
            )}
          </button>
        </form>

        {!auth && (
          <div className="info-box" style={{ marginTop: 16 }}>
            <Info size={14} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>Sign in to evaluate images.</span>
          </div>
        )}

        {error && !result && (
          <div className="error-box fade-in" style={{ marginTop: 14 }}>
            <span className="error-box-icon"><Info size={15} /></span>
            <div><strong>Error</strong> <span style={{ display: 'block', marginTop: 2 }}>{error}</span></div>
          </div>
        )}
        {error && result && (
          <div className="warning-box fade-in" style={{ marginTop: 14 }}>
            <Info size={14} />
            <span><strong>Warning</strong> {error}</span>
          </div>
        )}
      </div>

      {/* ── Result ── */}
      {result && (
        <div className="card glass fade-in">
          <div className="card-header">
            <div className="card-icon">
              <ImageIcon size={18} />
            </div>
            <div className="card-meta">
              <h2>Evaluation Result</h2>
              <p className="card-desc">Full optical pipeline output — OCR, risk, policy, and generation layers.</p>
            </div>
          </div>
          <ResultPanel
            data={result}
            conversationId={convId}
            token={auth?.token}
          />
        </div>
      )}
    </div>
  );
}
