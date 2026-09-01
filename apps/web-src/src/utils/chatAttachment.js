export const MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024;
export const CHAT_ATTACHMENT_HINT = 'Any file up to 10 MB';

const IMAGE_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.jfif', '.pjpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff',
]);

export function fileExtension(name) {
  return (name || '').toLowerCase().match(/\.[a-z0-9]+$/)?.[0] || '';
}

/** Whether the browser can show an inline thumbnail preview. */
export function canPreviewAttachment(file) {
  if (!file) return false;
  const type = (file.type || '').toLowerCase();
  if (type.startsWith('image/')) return true;
  return IMAGE_EXTENSIONS.has(fileExtension(file.name));
}

export function validateChatAttachment(file) {
  if (!file) return 'No file selected.';
  if (!file.name) return 'Choose a file with a name.';
  if (file.size > MAX_CHAT_FILE_BYTES) {
    return 'File must be 10 MB or smaller.';
  }
  return null;
}

export function prepareChatUpload(file) {
  if (!file || validateChatAttachment(file)) return null;
  return file;
}

export function attachmentLabel(file) {
  if (!file) return 'file';
  if (canPreviewAttachment(file)) return 'Image';
  const ext = fileExtension(file.name);
  if (ext === '.pdf') return 'PDF';
  if (ext === '.docx') return 'Word document';
  if (ext === '.xlsx' || ext === '.xlsm') return 'Excel spreadsheet';
  if (ext === '.csv') return 'CSV';
  if (ext === '.json') return 'JSON';
  if (ext) return ext.slice(1).toUpperCase();
  return 'File';
}
