// @ts-check
import fontScale from "./build/fontScale.mjs";

/** @type {import('postcss-load-config').Config} */
export default {
  plugins: [
    fontScale(),
    ...(process.env.NODE_ENV === "production"
      ? [(await import("cssnano")).default({})]
      : [])
  ]
};
