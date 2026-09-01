const ALLOWED_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/webp']);

const EXT_TO_MIME = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.jfif': 'image/jpeg',
  '.pjpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.pdf': 'application/pdf',
};

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const MAX_PDF_BYTES = 10 * 1024 * 1024;

/** Shown in UI hints only — not passed to <input accept> (breaks Windows file dialogs). */
export const IMAGE_FORMAT_HINT = 'PNG, JPEG, or WEBP';
export const CHAT_ATTACHMENT_HINT = 'PNG, JPEG, WEBP, or PDF';

/** Resolve MIME from file.type or filename (Windows often leaves type empty). */
export function resolveImageMime(file) {
  if (!file) return null;
  const type = (file.type || '').toLowerCase().split(';')[0].trim();
  if (ALLOWED_IMAGE_TYPES.has(type)) return type;
  if (!type || type === 'application/octet-stream') {
    const ext = (file.name || '').toLowerCase().match(/\.[a-z0-9]+$/)?.[0];
    return ext ? EXT_TO_MIME[ext] || null : null;
  }
  return null;
}

export function resolveAttachmentKind(file) {
  if (!file) return null;
  const name = (file.name || '').toLowerCase();
  const type = (file.type || '').toLowerCase().split(';')[0].trim();
  if (type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf';
  if (resolveImageMime(file)) return 'image';
  return null;
}

export function validateImageFile(file) {
  if (!file) return 'No image selected.';
  const mime = resolveImageMime(file);
  if (!mime) {
    const name = file.name || 'this file';
    return `"${name}" is not supported. Use ${IMAGE_FORMAT_HINT}.`;
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return 'Image must be 10 MB or smaller.';
  }
  return null;
}

export function validateChatAttachment(file) {
  if (!file) return 'No file selected.';
  const kind = resolveAttachmentKind(file);
  if (!kind) {
    const name = file.name || 'this file';
    return `"${name}" is not supported. Use ${CHAT_ATTACHMENT_HINT}.`;
  }
  const maxBytes = kind === 'pdf' ? MAX_PDF_BYTES : MAX_IMAGE_BYTES;
  if (file.size > maxBytes) {
    return `${kind === 'pdf' ? 'PDF' : 'Image'} must be 10 MB or smaller.`;
  }
  return null;
}

/** Ensure FormData uploads carry a supported MIME type. */
export function prepareImageUpload(file) {
  const mime = resolveImageMime(file);
  if (!mime) return null;
  if ((file.type || '').toLowerCase().split(';')[0].trim() === mime) return file;
  return new File([file], file.name, { type: mime, lastModified: file.lastModified });
}

export function prepareChatUpload(file) {
  const kind = resolveAttachmentKind(file);
  if (!kind) return null;
  if (kind === 'pdf') {
    const type = (file.type || '').toLowerCase().split(';')[0].trim();
    if (type === 'application/pdf') return file;
    return new File([file], file.name, { type: 'application/pdf', lastModified: file.lastModified });
  }
  return prepareImageUpload(file);
}
