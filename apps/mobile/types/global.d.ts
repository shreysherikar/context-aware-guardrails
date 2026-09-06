// Ambient declarations for CSS imports used by the web build
// (global.css, *.module.css). Expo normally generates an equivalent
// declaration in expo-env.d.ts on first `expo start`, but that file is
// gitignored — this keeps `tsc --noEmit` and CI working on a fresh clone
// without requiring a dev server run first.

declare module '*.module.css' {
  const classes: { [key: string]: string };
  export default classes;
}

declare module '*.css';
