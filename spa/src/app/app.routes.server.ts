import { RenderMode, ServerRoute } from '@angular/ssr';

// All routes render on each request: every route in the app calls `/api/me`
// at bootstrap via `provideAppInitializer`. Build-time prerendering would
// try to hit the BFF without it running and produce a broken shell.
export const serverRoutes: ServerRoute[] = [
  {
    path: '**',
    renderMode: RenderMode.Server,
  },
];
