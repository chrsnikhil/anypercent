/**
 * The bridge's own TypeScript sources (apps/world-bridge/src/arkiv), loaded through tsx so the console's copies
 * are compared against the source of truth itself, never against a second copy. schema.ts resolves its SDK from
 * the bridge's node_modules: a checkout without them fails here, loudly, rather than skipping the comparison.
 */
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { tsImport } from "tsx/esm/api";

export const BRIDGE_ARKIV = fileURLToPath(new URL("../../../apps/world-bridge/src/arkiv/", import.meta.url));
const BRIDGE_SDK = fileURLToPath(new URL("../../../apps/world-bridge/node_modules/@arkiv-network/sdk/package.json", import.meta.url));

async function load(name) {
  if (!existsSync(BRIDGE_ARKIV + name)) throw new Error(`the bridge's ${name} is not at ${BRIDGE_ARKIV}`);
  return tsImport(BRIDGE_ARKIV + name, import.meta.url);
}

/** apps/world-bridge/src/arkiv/schema.ts (needs `npm ci` in apps/world-bridge). */
export async function bridgeSchema() {
  if (!existsSync(BRIDGE_SDK)) throw new Error("apps/world-bridge has no node_modules: run npm ci there to compare the schemas");
  return load("schema.ts");
}

/** apps/world-bridge/src/arkiv/spec-json.ts (imports nothing at run time). */
export async function bridgeSpecJson() {
  return load("spec-json.ts");
}
