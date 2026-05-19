import { HTTP_TRANSFER_CACHE_ORIGIN_MAP } from '@angular/common/http';
import { ApplicationConfig, mergeApplicationConfig } from '@angular/core';
import { provideServerRendering, withRoutes } from '@angular/ssr';

import { appConfig } from './app.config';
import { serverRoutes } from './app.routes.server';
import { SSR_API_TARGET } from './shared/http/ssr-api-target.token';

// `||` (not `??`) so empty-string env values fall back to the default; trim
// trailing slashes so `${target}${path}` and the origin-map key both stay
// canonical (`http://bff:8000`, never `http://bff:8000/`).
const bffInternalUrl = (process.env['BFF_INTERNAL_URL'] || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);
// The browser-visible origin the SSR result will hydrate against. Defaults
// to the SPA edge port (4000); Story 6.2 will keep this in sync with
// `SPA_HOST_PORT` if it's overridden in compose.
const spaPublicOrigin = (process.env['SPA_PUBLIC_ORIGIN'] || 'http://localhost:4000').replace(
  /\/+$/,
  '',
);

const serverConfig: ApplicationConfig = {
  providers: [
    provideServerRendering(withRoutes(serverRoutes)),
    { provide: SSR_API_TARGET, useValue: bffInternalUrl },
    // Align the HttpClient transfer-cache key between SSR (absolute BFF URL
    // after ssrApiUrlInterceptor rewrites) and CSR (same-origin relative).
    // Without this, the browser silently re-fires `/api/me` after hydration.
    {
      provide: HTTP_TRANSFER_CACHE_ORIGIN_MAP,
      useValue: { [bffInternalUrl]: spaPublicOrigin },
    },
  ],
};

export const config = mergeApplicationConfig(appConfig, serverConfig);
