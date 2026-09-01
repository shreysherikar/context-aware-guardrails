import { useId, useRef } from 'react';

/**
 * Reliable file picker for embedded browsers (Electron / Cursor webview).
 * Uses a native <label htmlFor> plus a full-area transparent input overlay
 * so the user's click lands directly on the input (required in many webviews).
 */
export default function FilePickInput({
  accept,
  disabled = false,
  wrapClassName = '',
  onFile,
  children,
  inputRef,
  id: idProp,
  multiple = false,
  onDragOver,
  onDragLeave,
  onDrop,
  ariaLabel,
}) {
  const autoId = useId();
  const inputId = idProp || autoId;
  const localRef = useRef(null);
  const ref = inputRef || localRef;

  function handleChange(e) {
    const file = multiple ? e.target.files : (e.target.files?.[0] || null);
    onFile?.(file);
    e.target.value = '';
  }

  return (
    <label
      htmlFor={inputId}
      className={`file-pick-label${wrapClassName ? ` ${wrapClassName}` : ''}${disabled ? ' is-disabled' : ''}`}
      aria-label={ariaLabel}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <input
        ref={ref}
        id={inputId}
        type="file"
        {...(accept ? { accept } : {})}
        multiple={multiple}
        disabled={disabled}
        className="file-pick-input"
        onChange={handleChange}
        tabIndex={-1}
      />
      <span className="file-pick-content">{children}</span>
    </label>
  );
}
