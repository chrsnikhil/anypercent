/**
 * The World IdP side of Agent Pass: discovery, RFC 8628 device authorization and one token poll,
 * through oauth4webapi (the standard low-level OAuth 2 / OIDC client that openid-client v6 is built
 * on). The poll loop itself lives in agentpass.ts because World's stop rules (503 ends the attempt,
 * never a retry) are stricter than a generic loop's.
 *
 * Nothing in this file logs. device_code and tokens stay in memory and are never returned to HTTP.
 */
import * as oauth from "oauth4webapi";
import { createRemoteJWKSet, type JWTVerifyGetKey } from "jose";

export interface Discovery {
  issuer: string;
  acrSupported: string[];
}

export interface DeviceStart {
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete?: string;
  expires_in: number;
  interval?: number;
}

export type PollResult =
  | { kind: "tokens"; idToken: string }
  | { kind: "error"; error?: string; status: number }
  | { kind: "network" };

/** What agentpass.ts needs from World IdP; tests swap in a fake. */
export interface DeviceGrantClient {
  /** Cached for a few minutes; `refresh` forces a fetch (the reachability probe). */
  discover(refresh?: boolean): Promise<Discovery>;
  start(): Promise<DeviceStart>;
  poll(deviceCode: string): Promise<PollResult>;
  keys(): JWTVerifyGetKey;
}

export interface WorldIdpOptions {
  issuer: string;
  clientId: string;
  clientSecret: string;
  /** Tests only: allow an http:// issuer on loopback. */
  allowInsecure?: boolean;
  timeoutMs?: number;
}

export class WorldIdp implements DeviceGrantClient {
  private as: oauth.AuthorizationServer | undefined;
  private jwks: JWTVerifyGetKey | undefined;
  private fetchedAt = 0;
  private readonly client: oauth.Client;
  private readonly auth: oauth.ClientAuth;

  constructor(private readonly opts: WorldIdpOptions) {
    this.client = { client_id: opts.clientId };
    // The registered method; fixed at registration. Basic form-encodes id and secret as World asks.
    this.auth = oauth.ClientSecretBasic(opts.clientSecret);
  }

  private reqOpts(): { signal: AbortSignal; [oauth.allowInsecureRequests]?: boolean } {
    return {
      signal: AbortSignal.timeout(this.opts.timeoutMs ?? 8000),
      ...(this.opts.allowInsecure ? { [oauth.allowInsecureRequests]: true } : {}),
    };
  }

  /** Discovery, cached for 5 minutes. `issuer` must match AGENTPASS_ISSUER. */
  async discover(refresh = false): Promise<Discovery> {
    if (!refresh && this.as && Date.now() - this.fetchedAt < 300_000) return this.summary(this.as);
    const issuerUrl = new URL(this.opts.issuer);
    const res = await oauth.discoveryRequest(issuerUrl, { algorithm: "oidc", ...this.reqOpts() });
    const as = await oauth.processDiscoveryResponse(issuerUrl, res);
    if (!as.device_authorization_endpoint || !as.token_endpoint || !as.jwks_uri) {
      throw new Error("discovery lacks the device grant endpoints or jwks_uri");
    }
    if (!this.as || this.as.jwks_uri !== as.jwks_uri) {
      // Cached key set with bounded refresh: a 30 s cooldown between refetches, 10 min max age.
      this.jwks = createRemoteJWKSet(new URL(as.jwks_uri), {
        timeoutDuration: 5000,
        cooldownDuration: 30_000,
        cacheMaxAge: 600_000,
      });
    }
    this.as = as;
    this.fetchedAt = Date.now();
    return this.summary(as);
  }

  private summary(as: oauth.AuthorizationServer): Discovery {
    const acr = (as as unknown as { acr_values_supported?: unknown }).acr_values_supported;
    return {
      issuer: as.issuer,
      acrSupported: Array.isArray(acr) ? acr.filter((v): v is string => typeof v === "string") : [],
    };
  }

  private async server(): Promise<oauth.AuthorizationServer> {
    if (!this.as) await this.discover();
    return this.as!;
  }

  async start(): Promise<DeviceStart> {
    const as = await this.server();
    const res = await oauth.deviceAuthorizationRequest(as, this.client, this.auth, { scope: "openid" }, this.reqOpts());
    const out = await oauth.processDeviceAuthorizationResponse(as, this.client, res);
    return {
      device_code: out.device_code,
      user_code: out.user_code,
      verification_uri: out.verification_uri,
      verification_uri_complete:
        typeof out.verification_uri_complete === "string" ? out.verification_uri_complete : undefined,
      expires_in: out.expires_in,
      interval: typeof out.interval === "number" ? out.interval : undefined,
    };
  }

  async poll(deviceCode: string): Promise<PollResult> {
    const as = await this.server();
    let res: Response;
    try {
      res = await oauth.deviceCodeGrantRequest(as, this.client, this.auth, deviceCode, this.reqOpts());
    } catch {
      return { kind: "network" };
    }
    let body: Record<string, unknown> = {};
    try {
      body = (await res.json()) as Record<string, unknown>;
    } catch {
      body = {};
    }
    if (res.status === 200 && typeof body.id_token === "string") {
      return { kind: "tokens", idToken: body.id_token };
    }
    return {
      kind: "error",
      error: typeof body.error === "string" ? body.error : undefined,
      status: res.status,
    };
  }

  keys(): JWTVerifyGetKey {
    if (!this.jwks) throw new Error("discovery has not run");
    return this.jwks;
  }
}
