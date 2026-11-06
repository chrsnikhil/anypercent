/* "remotion" for the browser build: everything as is, except staticFile, which answers from the asset pack unpacked by
   the page (window.__ANY_ASSETS: published path -> blob URL), so the single HTML file needs no server. web/build.mjs
   points every import of "remotion" here, and this file's import of "remotion-real" at the package itself. */
import { staticFile as packaged } from "remotion-real";

export * from "remotion-real";

export const staticFile = (path: string): string => {
  const assets = (window as unknown as { __ANY_ASSETS?: Record<string, string> }).__ANY_ASSETS;
  const key = path.replace(/^\/+/, "");
  if (assets && assets[key]) return assets[key];
  return packaged(path);
};
