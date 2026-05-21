---
title: Reading Time Estimator
date: 2026-05-13
classification:
  domain: general
  projectType:
    - web_app
    - api_backend
inputDocuments: []
stepsCompleted:
  - bmad-validate-prd (Warning, 4/5 Good)
---

# Product Requirements Document: Reading Time Estimator

## 1. Overview

A personal reading-list application that lets users track books they want to read, are reading, or have finished, and request a personalized reading-time estimate for any book based on their own reading speed.

The primary purpose of this project is **architectural**: to implement and demonstrate a realistic OAuth2 / OIDC flow across multiple cooperating services, where a Backend-for-Frontend acts as an OAuth client on the user's behalf against a separately-owned resource API. The application domain is intentionally minimal to keep focus on the authentication and inter-service communication patterns.

## 2. Background and Motivation

This project is the capstone deliverable for an AI-native engineering course. It must be built using the BMAD framework end-to-end, with QA integrated from day one and the full system deployable via `docker-compose up`.

Beyond the course, the architecture mirrors a potential client engagement in which the team uses OIDC to call APIs hosted by the client. Reproducing that pattern in a controlled environment is an explicit secondary goal: the project doubles as a working reference for the team's broader work.

## 3. Goals

- Provide a working end-to-end example of the OAuth2 Authorization Code flow with a confidential OIDC client. PKCE is intentionally omitted: the `client_secret` held server-side is the trust anchor with the Authorization Server, and PKCE was designed to protect public clients that lack one — a confidential client gains no incremental protection. (See Architecture §A1.)
- Demonstrate the Token Handler / BFF pattern, in which access and refresh tokens never leave the server side and the browser holds only an HttpOnly session cookie.
- Demonstrate a stateless, JWT-protected resource API that has no shared session or database with the BFF and trusts only the authorization server's signature.
- Demonstrate OAuth scope-based authorization enforced at the resource server.
- Demonstrate user identity propagation across independently-owned services via the `sub` claim, with no user table outside the authorization server.
- Be reproducibly deployable end-to-end via `docker-compose up`, including a pre-configured authorization server.

## 4. Non-Goals

- Building a feature-rich reading-list product. The book domain is deliberately thin and exists to give the OAuth flow something to protect.
- Recommendation engines, social features, or third-party metadata enrichment.
- Multi-tenancy, admin roles, or organizational hierarchies beyond per-user data isolation.
- Mobile applications or offline support.
- Responsive or multi-viewport SPA layout; the SPA targets desktop browsers only.
- Accessibility hardening: no WCAG conformance audit, no assistive-technology testing, no a11y-focused UX work. The SPA uses reasonable HTML semantics by default but is not assessed against any accessibility standard.
- Production hardening beyond what the course's success criteria require.

## 5. Users and Roles

A single role: **authenticated end user**. Each user sees only their own books and only their own reading-speed profile. There is no admin role and no anonymous access to application data.

## 6. System Components and Ownership

The system is composed of four cooperating services plus a database. Ownership boundaries are a deliberate part of the design and should be preserved by the architecture.

- **Single Page Application (SPA)** — the user-facing client. Holds no tokens. Authenticates to the BFF via an HttpOnly session cookie. Communicates only with the BFF. Runs as an Angular SSR Node service whose Express server is the browser-facing edge; the BFF is internal-only on the compose network (Epic 6 split).
- **Backend for Frontend (BFF)** — a confidential OAuth client. Handles the OIDC login flow, holds access and refresh tokens server-side, exposes a cookie-authenticated API to the SPA, and owns the book domain and its database.
- **Authorization Server** — an OpenID Connect provider (Keycloak in this implementation). Issues ID tokens, access tokens, and refresh tokens; hosts the user database; serves the JWKS endpoint used by the resource server. Configured reproducibly via realm-style import at container startup.
- **Resource Server** — a stateless, JWT-protected API. Owns user reading-speed data and the reading-time computation. Has no shared state with the BFF and trusts only tokens signed by the authorization server.
- **BFF Database** — owned exclusively by the BFF, stores book records keyed by `sub`.

## 7. Application Capabilities

At the capability level (functional decomposition is the PM persona's job):

- **FR-AUTH-01.** Users can authenticate via the authorization server and obtain a browser session managed by the BFF. *Source journey: J1.*
- **FR-BOOK-01.** Users can perform full CRUD operations on their personal book list, where a book consists of a title, a page count, and a reading status. *Source journey: J2.*
- **FR-SPEED-01.** Users can view and update a personal reading speed, expressed in pages-per-hour, stored on the resource server. *Source journey: J4.*
- **FR-ESTIMATE-01.** Users can request a reading-time estimate for any book in their list. The estimate is computed by the resource server using the user's reading speed and the book's page count. *Source journey: J3.*
- **FR-LOGOUT-01.** Users can log out, terminating both the browser session and the refresh token at the authorization server. *Source journey: J5.*
- **FR-ERROR-01.** Users see a clear error state when the resource server is unavailable; the BFF surfaces the failure rather than fabricating a result. *Source journey: J6.*

## 8. Architectural Constraints

These constraints are load-bearing for the educational goals of the project and are not open for the Architect persona to relax:

- **Token isolation.** Access and refresh tokens must never be transmitted to, stored in, or accessible from the SPA or any browser-accessible storage.
- **BFF as confidential OAuth client.** The BFF is the OAuth client. Login uses the Authorization Code flow; the BFF authenticates to the Authorization Server with a `client_secret` that lives only on the backend (loaded from env at startup, never present in any browser-reachable artifact). PKCE is not used — the confidential-client secret is the trust anchor. The BFF holds tokens server-side, keyed by session.
- **Transparent token refresh.** The BFF refreshes expired access tokens using the refresh token and retries the in-flight request, without involving the SPA.
- **Stateless resource server.** The resource server maintains no session state, shares no database with the BFF, and authenticates every request solely by the JWT it carries.
- **JWKS-based validation.** The resource server validates JWTs by fetching and caching the authorization server's JWKS. Public keys are not hardcoded.
- **Identity source of truth.** No service other than the authorization server stores user account records. User-owned data on the BFF and resource server is keyed by the `sub` claim.
- **Scope-enforced computation.** Access to the resource server's endpoints is gated by OAuth scopes — `reading-speed:read` for retrieving the reading speed and computing estimates, `reading-speed:write` for modifying the reading speed. Scope enforcement happens at the resource server, not at the BFF.
- **BFF does not bypass the resource server.** When the resource server is unavailable, the BFF surfaces an error rather than computing a fallback locally. The boundary is meaningful and must remain so.
- **Reproducible authorization server configuration.** The provider's realm, clients, and scopes are version-controlled and imported at container startup. No manual configuration steps after `docker-compose up`.

## 9. Operational and Quality Requirements

- **Containerized deployment.** Every component, including the authorization server and the database, runs in Docker. The system is brought up by `docker-compose up` with no further setup. Health checks gate inter-service dependencies so that services start in the correct order.
- **Test coverage.** Minimum 70% meaningful code coverage across services. At least five end-to-end tests covering the primary user journeys, with the authentication flow exercised end-to-end rather than mocked.
- **Security posture.** A documented security review covering at minimum: token storage and transport, session cookie attributes, CSRF posture, JWT validation correctness, scope enforcement, and standard SPA concerns (XSS, injection).
- **Environment configuration.** Development and test configurations are selectable via environment variables and compose profiles. Secrets are not committed to the repository.

## 10. Primary User Journeys

These are the journeys the system must support end-to-end and that the E2E test suite must cover:

- **J1. First-time login.** Unauthenticated user opens the SPA, is redirected through the BFF to the authorization server, logs in, returns to the SPA authenticated, and sees their (initially empty) book list.
- **J2. Manage books.** User adds a book, sees it in the list, updates its status as their reading progresses, eventually deletes it.
- **J3. Request a reading-time estimate.** User selects a book, requests an estimate, sees the computed reading time. The request authorizes against the `reading-speed:read` scope.
- **J4. Adjust reading speed.** User opens a settings view, sees their current reading speed, updates it, requests a new estimate on the same book, observes a different result. The update authorizes against the `reading-speed:write` scope.
- **J5. Logout and re-protection.** User logs out, is returned to an unauthenticated state, and attempting to access protected views redirects back to login.
- **J6. Resource server unavailable.** User requests an estimate while the resource server is down; the SPA presents a clear error and the BFF does not fabricate a result.

## 11. Deliverables

### BMAD process artifacts

- This PRD.
- Architecture document with component diagram and OAuth sequence diagrams.
- Story breakdown with acceptance criteria.
- Test strategy spanning unit, integration, and E2E layers.

### Product deliverables

- Working application runnable via `docker-compose up`, including a pre-configured authorization-server realm.
- Dockerfiles for each service and a `docker-compose.yml` orchestrating the full topology with health checks and dependency ordering.
- README with setup instructions, an architecture overview, and an AI integration log documenting agent and MCP usage throughout the build.

### Quality and compliance

- Unit, integration, and end-to-end test suites meeting the coverage and journey requirements in §9.
- QA reports covering test coverage and a security review focused on the OAuth implementation.

## 12. Out of Scope

- Concurrent edits to the same book across sessions.
- Bulk import or export of books.
- Authorization server downtime handling beyond a graceful error to the user.
- Token revocation propagation beyond standard refresh-token invalidation on logout.
- Observability tooling: no distributed-tracing collector, metrics aggregator, or dashboards. The project does not deploy OTEL Collector, Jaeger, Prometheus, or Grafana. Structured logging is the only operational-visibility surface.
- PKCE (RFC 7636) on the OAuth Authorization Code flow. Deliberately omitted because the BFF is a confidential client. Adding PKCE in addition would be defense-in-depth, not a correctness requirement, and is out of scope for this educational reference.
- Any feature whose implementation would dilute the architectural focus of the project.
