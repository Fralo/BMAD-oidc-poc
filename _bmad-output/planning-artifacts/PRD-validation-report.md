---
validationTarget: '/Users/fralo/nearform/AINE_Training/BMAD_books/_bmad-output/planning-artifacts/PRD.md'
validationDate: '2026-05-13'
inputDocuments:
  - PRD.md
validationStepsCompleted:
  - step-v-01-discovery
  - step-v-02-format-detection
  - step-v-03-density-validation
  - step-v-04-brief-coverage-validation
  - step-v-05-measurability-validation
  - step-v-06-traceability-validation
  - step-v-07-implementation-leakage-validation
  - step-v-08-domain-compliance-validation
  - step-v-09-project-type-validation
  - step-v-10-smart-validation
  - step-v-11-holistic-quality-validation
  - step-v-12-completeness-validation
  - step-v-13-report-complete
validationStatus: COMPLETE
completenessSeverity: Warning
templateVariablesRemaining: 0
prdFrontmatterPresent: false
holisticQualityRating: 4/5 Good
overallStatus: Warning (usable; address top 3 improvements before locking in)
overallQualityRating: 4/5 Good
smartAverage: 4.56
smartFlagged: 0
projectTypeAssumed: web_app + api_backend hybrid
projectTypeSeverity: Warning
formatClassification: BMAD Standard
coreSectionsPresent: 6
densitySeverity: Pass
measurabilitySeverity: Warning
measurabilityViolations: 5
traceabilitySeverity: Warning
traceabilityIssues: 2
orphanFRs: 0
leakageSeverity: Pass
leakageBorderline: 1
---

# PRD Validation Report

**PRD Being Validated:** /Users/fralo/nearform/AINE_Training/BMAD_books/_bmad-output/planning-artifacts/PRD.md
**Validation Date:** 2026-05-13

## Input Documents

- PRD.md (Reading Time Estimator) — primary validation target, no frontmatter, no inputDocuments declared
- No additional reference documents supplied

## Validation Findings

## Format Detection

**PRD Structure (all Level 2 headers):**
1. ## 1. Overview
2. ## 2. Background and Motivation
3. ## 3. Goals
4. ## 4. Non-Goals
5. ## 5. Users and Roles
6. ## 6. System Components and Ownership
7. ## 7. Application Capabilities
8. ## 8. Architectural Constraints
9. ## 9. Operational and Quality Requirements
10. ## 10. Primary User Journeys
11. ## 11. Deliverables
12. ## 12. Out of Scope

**BMAD Core Sections Present:**
- Executive Summary: **Present** — covered by `## 1. Overview` (vision + primary purpose)
- Success Criteria: **Present** — covered by `## 3. Goals` (currently qualitative — see density-validation step)
- Product Scope: **Present** — split across `## 4. Non-Goals` and `## 12. Out of Scope`; positive-scope is implicit via `## 7. Application Capabilities`
- User Journeys: **Present** — covered by `## 10. Primary User Journeys`
- Functional Requirements: **Present** — covered by `## 7. Application Capabilities` (capability-level, no FR-ID structure)
- Non-Functional Requirements: **Present** — covered by `## 9. Operational and Quality Requirements`

**Format Classification:** BMAD Standard
**Core Sections Present:** 6/6

Note: All six core BMAD sections are addressed semantically, though the headings use the author's own naming (e.g., "Goals" instead of "Success Criteria", "Application Capabilities" instead of "Functional Requirements"). Mapping was performed against the section-name variants permitted by the BMAD format-detection rules. Section content quality is evaluated in subsequent validation passes.


## Information Density Validation

**Anti-Pattern Violations:**

**Conversational Filler:** 0 occurrences
- Scanned for: "the system will allow…", "it is important to note…", "in order to", "for the purpose of", "with regard to", "allows the user to", "enables users to", "will be able to"
- No matches found

**Wordy Phrases:** 0 occurrences
- Scanned for: "due to the fact that", "in the event of", "at this point in time", "in a manner that", "despite the fact that", "with the exception of", "a number of", "the majority of"
- No matches found

**Redundant Phrases:** 0 occurrences
- Scanned for: "future plans", "past history", "absolutely essential", "completely finish", "end result", "final outcome", "new innovation", "basic fundamentals", "each and every"
- No matches found

**Broader hedge/intensifier sweep:** matches against `simply / just / really / very / extremely / note that / please note` produced only substring false positives (e.g. `very` inside `every`); no genuine hedge or filler usage in the PRD.

**Total Violations:** 0

**Severity Assessment:** Pass

**Recommendation:** PRD demonstrates excellent information density with zero violations across all three anti-pattern categories. Voice is direct, declarative, and consistently in active form ("Users authenticate via…", "The BFF refreshes…"). No revision needed for density.

## Product Brief Coverage

**Status:** N/A — No Product Brief was provided as input

## Measurability Validation

### Functional Requirements

**Total FRs Analyzed:** 5 (from `## 7. Application Capabilities`, lines 50-54)

**FR1 (line 50):** "Users authenticate via the authorization server and obtain a browser session managed by the BFF."
- Format: minor — uses "Users authenticate" instead of preferred "Users can authenticate"
- Subjective adjectives: none
- Vague quantifiers: none
- Implementation leakage: none (component names are deliberate per §6)

**FR2 (line 51):** "Users perform full CRUD operations on their personal book list, where a book consists of a title, a page count, and a reading status."
- Format: minor — "Users perform" → "Users can perform"
- Subjective adjectives: none
- Vague quantifiers: none ("full CRUD" expands to Create/Read/Update/Delete — concrete)
- Implementation leakage: none
- Note: "reading status" lacks an enumerated value set (e.g., {to-read, reading, finished}); downstream UX/data-model work will need that

**FR3 (line 52):** "Users have a personal reading speed, expressed in pages-per-hour, stored on the resource server and adjustable by the user."
- Format: descriptive ("Users have") not action-oriented; the capability is "adjust" but it is buried
- Subjective adjectives: none
- Vague quantifiers: none
- Implementation leakage: "stored on the resource server" is architectural (intentional per §6); acceptable
- Note: missing valid range/default (e.g., 1–1000 pph)

**FR4 (line 53):** "Users can request a reading-time estimate for any book in their list. The estimate is computed by the resource server using the user's reading speed and the book's page count."
- Format: ✓ ("Users can request…")
- Subjective adjectives: none
- Vague quantifiers: none
- Implementation leakage: none (boundary statement intentional)
- Note: no performance criterion (latency target for the estimate response); no specification of estimate unit (minutes? hours? hours+minutes?) or rounding/precision

**FR5 (line 54):** "Users can log out, terminating both the browser session and the refresh token at the authorization server."
- Format: ✓
- Subjective adjectives: none
- Vague quantifiers: none
- Implementation leakage: none

**Format Violations:** 3 (FR1, FR2, FR3 do not use the recommended "[Actor] can [verb]" pattern)
**Subjective Adjectives Found:** 0
**Vague Quantifiers Found:** 0
**Implementation Leakage:** 0 (architectural references are deliberate per §6 and §8)

**FR Violations Total:** 3 (all format-only, mild)

**Additional FR-level observations (not counted as anti-pattern violations but flagged for downstream):**

- **No FR identifiers.** None of the capabilities have IDs (FR-001, FR-AUTH-01, etc.). Story breakdown and traceability will need them — Stories normally cite the FR they implement.
- **Missing acceptance-level details:** reading-status enum, reading-speed valid range and default, estimate unit and precision, max page-count and title-length bounds. These can land in stories, but flagging here so they aren't forgotten.
- **Boundary between §7 (capabilities) and §10 (journeys) is healthy** — §10 effectively supplies acceptance scenarios for §7. Recommend cross-linking when stories are created.

### Non-Functional Requirements

**Total NFRs Analyzed:** 5 (from `## 9. Operational and Quality Requirements`, lines 72-76)
Plus 9 architectural constraints in `## 8. Architectural Constraints` (lines 60-68) that function as NFRs in practice — covered separately below.

**NFR1 (line 72) — Containerized deployment.**
- Metric: "`docker-compose up` with no further setup"; "health checks gate inter-service dependencies"
- Measurement method: implicit (boolean — system either starts or does not)
- Context: ✓ (reproducibility goal stated in §3)
- Gap: "services start in the correct order" — "correct" is qualitative; recommend specifying the required dependency graph (e.g., DB → Keycloak → Resource Server → BFF → SPA)

**NFR2 (line 73) — Test coverage.**
- Metric: ✓ "≥70% code coverage", "≥5 E2E tests"
- Measurement method: coverage tool implicit, E2E count is countable
- Context: ✓
- Gap: "meaningful" coverage is a hedge — recommend defining the rule (e.g., excludes generated code, excludes `__init__.py`, branch coverage vs line coverage)

**NFR3 (line 74) — Accessibility.**
- Metric: ✓ "WCAG AA audit, zero critical violations"
- Measurement method: missing — which tool? axe-core, Lighthouse, Pa11y, manual review?
- Context: ✓ (course success criterion)
- Gap: tool unspecified → results can differ between tools

**NFR4 (line 75) — Security posture.**
- Metric: deliverable-based ("documented security review covering at minimum [list]")
- Measurement method: review-document existence + content checklist
- Context: ✓ (OAuth implementation is the architectural focus)
- Gap: no severity threshold (e.g., "zero high/critical findings unmitigated"). Currently the NFR is satisfied by *producing* the review, not by *passing* it.

**NFR5 (line 76) — Environment configuration.**
- Metric: ✓ Boolean ("selectable via env vars and compose profiles", "Secrets are not committed")
- Measurement method: gitleaks/scan implicit; env-file presence verifiable
- Context: ✓
- Gap: minor — secret-scanning tool not named, so the "not committed" check relies on convention.

**§8 Architectural Constraints functioning as NFRs (lines 60-68):**
All nine constraints are highly measurable:

- Token isolation (60): testable via browser dev-tools / cookie inspection
- BFF as confidential OAuth client (61): testable via Keycloak client config + flow inspection
- Transparent token refresh (62): testable via E2E test with forced token expiry
- Stateless resource server (63): testable via code review (no session middleware, no shared DB) + horizontal-scaling test
- JWKS-based validation (64): testable via key-rotation test
- Identity source of truth (65): testable by inspecting DB schemas (no users table outside Keycloak)
- Scope-enforced computation (66): testable by attempting access with wrong/missing scope
- BFF does not bypass resource server (67): testable by stopping resource server (already in §10 journey)
- Reproducible auth server config (68): testable by destroying Keycloak data and re-running `docker-compose up`

**Missing Metrics:** 0
**Incomplete Template:** 2 (NFR3 lacks tool spec; NFR4 lacks pass/fail threshold)
**Missing Context:** 0

**NFR Violations Total:** 2 (both moderate — easy to tighten)

### Overall Assessment

**Total Requirements:** 5 FRs + 5 NFRs + 9 architectural-constraint NFRs = 19
**Total Violations:** 3 (FR format) + 2 (NFR template) = 5

**Severity:** Warning (exactly at the 5–10 threshold)

**Recommendation:** Most violations are stylistic format issues, not measurability failures. The PRD demonstrates strong, testable requirements overall. Two concrete tightening actions before locking in:

1. Convert §7 capabilities to consistent "Users can [verb]" form and assign FR IDs (FR-AUTH-01, FR-BOOK-01, etc.) to enable downstream story traceability.
2. Tighten NFR3 (specify accessibility tool) and NFR4 (define security-review pass/fail threshold rather than just "documented").

## Traceability Validation

### Elements Extracted

**Executive Summary (§1):**
- Vision-A: Personal reading-list app with personalized reading-time estimates
- Vision-B (primary): Architectural demonstration of OAuth2/OIDC across cooperating services, with BFF acting as OAuth client against a separately-owned resource API
- Stated: book domain is deliberately minimal

**Success Criteria (§3 Goals):** G1–G6
- G1: Auth Code + PKCE with confidential client
- G2: Token Handler / BFF pattern (browser holds only HttpOnly session cookie)
- G3: Stateless JWT-protected resource API (no shared state with BFF)
- G4: OAuth scope-based authorization at resource server
- G5: User identity propagation via `sub` claim (no user table outside auth server)
- G6: Reproducibly deployable via `docker-compose up`

**User Journeys (§10):** J1–J6
- J1: First-time login
- J2: Manage books
- J3: Request reading-time estimate
- J4: Adjust reading speed
- J5: Logout and re-protection
- J6: Resource server unavailable (error path)

**Functional Requirements (§7):** FR1–FR5
- FR1: Authenticate + obtain BFF session
- FR2: CRUD on personal book list
- FR3: Personal reading speed (pages/hour, adjustable)
- FR4: Request reading-time estimate
- FR5: Logout (terminate session + refresh token)

**Architectural Constraints (§8):** C1–C9 (function as load-bearing NFRs)
- C1 Token isolation · C2 BFF confidential client · C3 Transparent refresh · C4 Stateless resource server · C5 JWKS validation · C6 Identity source of truth · C7 Scope-enforced · C8 BFF does not bypass resource server · C9 Reproducible auth-server config

### Chain Validation

**Executive Summary → Success Criteria:** Intact
- Vision-B → G1, G2, G3, G4, G5 directly (each architectural pillar maps to a goal)
- Course/team-reference motivation (§2) → G6 (deployability)
- Vision-A (reading-list app domain) intentionally **does not** generate Goals — §1 and §4 explicitly say the domain exists only to give the OAuth flow something to protect. Not a gap; an intentional scoping choice.

**Success Criteria → User Journeys:** Gaps Identified (soft)
- G1 (PKCE) ↔ J1 ✓
- G2 (no browser tokens) ↔ J1, J5 ✓ (token-absence is enforced at test level; user-visible side is covered)
- G3 (stateless JWT resource API) ↔ J3, J4 ✓ (both journeys hit the resource server)
- **G4 (scope-based authorization)** ↔ J3 (read estimate) and J4 (modify speed) implicitly exercise different scopes, but the scope distinction is *not surfaced* in the journey text. Soft gap — easy fix: add a sentence to §10 or split into two-scope acceptance.
- G5 (sub-claim propagation) ↔ J1 + J2 implicit (book list is per-user, keyed by `sub`). Not visible in user-facing flow text. Acceptable for a journey-level doc; explicit testing belongs to E2E.
- G6 (docker-compose up) ↔ operational, not journey-bearing. Traces to NFR1 instead — valid alternate trace.

**User Journeys → Functional Requirements:** Gaps Identified (soft)
- J1 → FR1 ✓
- J2 → FR2 ✓
- J3 → FR4 ✓
- J4 → FR3 ✓
- J5 → FR5 ✓
- **J6 (resource server unavailable)** → no positive FR; traces to constraint **C8** ("BFF does not bypass the resource server"). Acceptable as an error-path journey, but worth flagging: there is no §7 capability such as "the SPA displays a clear failure state when the resource server is unreachable", so error-handling becomes a constraint-driven implementation detail rather than a first-class capability.

**Scope → FR Alignment:** Intact
- Positive scope (FRs) — all five FRs lie inside §7's stated capability boundary ✓
- Non-Goals (§4): "thin book domain" satisfied by FR2's minimal model (title, page count, status); no recommendation/social/enrichment FRs ✓
- Out of Scope (§12): no FR conflicts with concurrent-edit, bulk import/export, auth-server downtime, or revocation-propagation exclusions ✓

### Orphan Elements

**Orphan Functional Requirements:** 0
All five FRs trace cleanly to at least one User Journey.

**Unsupported Success Criteria:** 0
All six Goals trace to either a Journey or an Operational/Architectural NFR.

**User Journeys Without FRs:** 1 (soft)
- J6 (error-path) traces to constraint C8 rather than an FR. Acceptable for an error-handling scenario, but consider promoting it to an FR (e.g., "Users see a clear error state when the resource server is unavailable") for traceability symmetry.

### Traceability Matrix

| FR  | Source Journey | Source Goal(s)            | Reinforcing Constraints |
|-----|----------------|----------------------------|--------------------------|
| FR1 | J1             | G1, G2                     | C1, C2                   |
| FR2 | J2             | G5 (per-user data)         | C6                       |
| FR3 | J4             | G3, G4 (mod-scope)         | C7                       |
| FR4 | J3             | G3, G4 (read-scope)        | C7, C8                   |
| FR5 | J5             | G2                         | C1                       |
| —   | J6 (orphan)    | (none — error-path)        | C8                       |

| Goal | Supporting Journey(s)        | Supporting FR / NFR |
|------|------------------------------|---------------------|
| G1   | J1                            | FR1                 |
| G2   | J1, J5                        | FR1, FR5; C1, C3    |
| G3   | J3, J4                        | FR3, FR4; C4, C5    |
| G4   | J3, J4 (implicit)             | FR3, FR4; C7        |
| G5   | J1, J2 (implicit)             | FR2; C6             |
| G6   | (operational, not a journey)  | NFR1; C9            |

**Total Traceability Issues:** 2 (soft)
1. G4's scope-distinction not surfaced in journey text
2. J6 (error-path journey) has no FR counterpart, only a constraint

**Severity:** Warning (chains are intact, but two soft gaps)

**Recommendation:** Two low-cost edits would tighten the chain:
1. Mention the two distinct scopes explicitly in J3 vs J4 (e.g., "reads `reading-speed:read`" vs "writes `reading-speed:write`").
2. Add an FR for "user-visible error handling when the resource server is unreachable" so J6 has a positive FR to trace to.

## Implementation Leakage Validation

### Context

This PRD is unusual: §1 states its **primary purpose is architectural**, and §3 Goals are explicitly stated in terms of patterns and protocols (Authorization Code + PKCE, Token Handler / BFF, stateless JWT, scope-based authorization, `sub`-claim propagation, `docker-compose up`). The technology and protocol names in this PRD are typically *load-bearing requirements*, not leakage, because the **demonstration of those patterns is the success criterion**. Below, each term is classified accordingly.

### Scan Results by Category

**Frontend Frameworks (React/Vue/Angular/etc.):** 0
**Backend Frameworks (Express/Django/Spring/etc.):** 0
**Cloud Platforms (AWS/GCP/Azure/etc.):** 0
**Specific Libraries (Redux/axios/lodash/etc.):** 0
**Data Formats (JSON/XML/YAML as implementation):** 0

**Databases:** 0 specific products named (generic "database" and "BFF Database" only — appropriate)

**Infrastructure:**
- `Docker` / `docker-compose` mentioned on lines 11, 22, 68, 72, 92, 94 → **CAPABILITY-RELEVANT (not leakage)**. §3 G6 explicitly states reproducible deployability via `docker-compose up` as a Goal. Course success criterion. Acceptable.

**Authorization-Server Product:**
- `Keycloak` mentioned on lines 42, 68, 92 → **BORDERLINE LEAKAGE (1 logical violation)**.
  - Line 42 hard-binds the authorization-server role to Keycloak in `## 6 System Components`.
  - Line 68 cites "the Keycloak realm" as an architectural constraint.
  - Line 92 lists "pre-configured Keycloak realm" as a deliverable.
  - **Why it's borderline:** the architectural learning outcomes (PKCE, JWT, JWKS, scopes, `sub` propagation) are provider-agnostic. The PRD could state "an OpenID Connect provider, supporting realm-style configuration import" and let architecture select Keycloak. Doing so would preserve goal G6 (deployability) while keeping the requirement abstract.
  - **Why it might be acceptable:** the realm-import reproducibility requirement is fairly Keycloak-specific in its exact shape, and the course curriculum likely fixes Keycloak as the teaching target.

**Protocol/Pattern terminology (PKCE, JWT, JWKS, OAuth2, Authorization Code flow, scopes, BFF, SPA):** All capability-relevant — these are the named patterns the project must demonstrate per §3 Goals.

### Summary

**Total Implementation Leakage Violations:** 1 (borderline) — `Keycloak` as a specific authorization-server product name.

**Severity:** Pass

**Recommendation:** The PRD is in good shape on implementation leakage. The only term that could be abstracted is **Keycloak**: consider replacing component-level mentions with "an OpenID Connect–compliant authorization server supporting declarative realm/client/scope import at container startup" and naming Keycloak in the architecture document instead. This is a stylistic improvement, not a defect — keeping Keycloak named is also defensible given the project's pedagogical context. All Docker/compose mentions remain in the PRD because they trace to an explicit Goal (G6).

**Note:** The PRD's use of OAuth/OIDC protocol and pattern names is **not leakage** in this context — those names are themselves the architectural learning outcomes the project exists to demonstrate.

## Domain Compliance Validation

**Domain:** general (no `classification.domain` in PRD frontmatter; the application domain is a personal book/reading list)
**Complexity:** Low (general/standard)
**Assessment:** N/A — No special domain-compliance requirements (no Healthcare, Fintech, GovTech, EdTech-records, or Legal-tech regulation applies)

**Note:** PII handling is light (display name + book records keyed by `sub`). Standard SPA/OAuth security concerns are already covered by NFR4 in §9 and the architectural constraints in §8. No GDPR-specific provisions are surfaced, but given the educational scope and lack of production deployment intent (§4), this is acceptable. If the team later deploys publicly, a GDPR/data-retention section would be warranted.

## Project-Type Compliance Validation

**Project Type:** No `classification.projectType` in frontmatter. Assumed: **multi-service web_app + api_backend hybrid**.
- User-facing surface = SPA + BFF → `web_app`
- Server-side surfaces = BFF API + Resource Server → `api_backend`
- Deployment artifact = `infrastructure` aspects

The PRD must be evaluated against the union of relevant project-type templates.

### Required Sections — web_app perspective

**User Journeys:** **Present** — §10 lists six concrete journeys, including an error-path journey. ✓

**UX/UI Requirements:** **Missing** — There is no §5/§7/§10 content specifying screen inventory, page structure, navigation model, component-level UI requirements, design tokens, or visual style. The PRD has §5 Users and Roles (a single line: "authenticated end user") and otherwise stays at capability level.
- **Mitigating context:** §4 explicitly Non-Goals "building a feature-rich reading-list product"; UX is intentionally minimal.
- **Recommendation:** even with minimal UX, the next BMAD step (`bmad-create-ux-design`) needs a baseline. Consider adding a one-paragraph "UX scope" — what screens exist, what data each shows — even at the cost of the deliberately-thin doctrine.

**Responsive Design:** **Not mentioned** — but §4 explicitly excludes mobile and offline. Responsive layout is therefore "free" (desktop browsers only, single layout) but the PRD should state that explicitly to avoid downstream architecture/UX questions. Soft gap.

### Required Sections — api_backend perspective

**Endpoint Specs:** **Missing** — No HTTP method/path/payload specifications. Capabilities are described at intent level.
- **Mitigating context:** §11 Deliverables lists "architecture document with component diagram and OAuth sequence diagrams" — endpoint shape is being deliberately deferred to the architecture phase. Acceptable PRD-level scoping.

**Auth Model:** **Present (excellent)** — §6 defines actors and trust boundaries; §8 specifies token isolation, PKCE, refresh-token handling, JWKS validation, scope enforcement, identity propagation. This is the strongest section of the PRD. ✓

**Data Schemas:** **Partial** —
- Book entity: name + page count + status — fields named but no types, no constraints (e.g., title length, page-count range, status enum values)
- Reading speed: "pages-per-hour" — no range, no default, no unit-conversion rules
- **Recommendation:** add a brief data-model section or land these constraints in stories during the planning phase.

**API Versioning:** **Not specified** — acceptable for a single-deploy demo.

### Required Sections — infrastructure perspective

**Infrastructure Components:** **Present** — §6 enumerates the five components. ✓
**Deployment:** **Present** — §9 NFR1 (containerized + `docker-compose up` + health-check ordering). ✓
**Monitoring:** **Not mentioned** — reasonable to skip for a capstone demo.
**Scaling:** **Not mentioned** — implicit single-user/demo profile; §4 implies it.

### Excluded Sections

For this hybrid, there are no sections in the PRD that violate exclusion rules:
- No misplaced mobile-app sections
- No misplaced library/SDK API-surface sections
- No misplaced ML-system sections

### Compliance Summary

| Project-type aspect           | Required-section coverage |
|-------------------------------|---------------------------|
| web_app                       | 1/3 (User Journeys present; UX/UI thin; Responsive not stated) |
| api_backend                   | 2/4 (Auth Model present; Data Schemas partial; Endpoint Specs deferred; Versioning absent) |
| infrastructure                | 2/4 (Components + Deployment; Monitoring/Scaling absent — acceptable for demo) |

**Excluded Sections Present:** 0 violations

**Severity:** Warning — UX/UI surface and data-schema details are the most material gaps. Most other absences are defensible deliberate-scope decisions.

**Recommendation:**
1. Add a short "UX Scope" section to the PRD: at minimum, list the screens (e.g., login redirect, book list, book detail, settings, error state) and what each displays. Even a paragraph satisfies downstream `bmad-create-ux-design` needs.
2. Add a one-line note explicitly excluding responsive/multi-viewport requirements (matching §4's mobile/offline exclusion).
3. Tighten the data model: title length cap, page-count range, status enum values, reading-speed range and default. Either inline in §7 or in a new "Data Model" subsection.

## SMART Requirements Validation

**Total Functional Requirements:** 5 (FR1–FR5 from §7)

### Scoring Summary

**All scores ≥ 3:** 100% (5/5)
**All scores ≥ 4:** 40% (2/5 — FR1 and FR5)
**Overall Average Score:** 4.56 / 5.0

### Scoring Table

| FR  | Specific | Measurable | Attainable | Relevant | Traceable | Avg  | Flag |
|-----|----------|------------|------------|----------|-----------|------|------|
| FR1 | 4        | 4          | 5          | 5        | 5         | 4.6  |      |
| FR2 | 3        | 4          | 5          | 5        | 5         | 4.4  |      |
| FR3 | 3        | 4          | 5          | 5        | 5         | 4.4  |      |
| FR4 | 3        | 4          | 5          | 5        | 5         | 4.4  |      |
| FR5 | 5        | 5          | 5          | 5        | 5         | 5.0  |      |

**Legend:** 1 = Poor · 3 = Acceptable · 5 = Excellent · Flag = score <3 in any category

### Improvement Suggestions

No FRs are flagged (all categories ≥ 3). However, three FRs sit at "Specific = 3" because they describe capability but leave data-model details open:

- **FR2 (book CRUD):** add field-level details — title length cap, page-count range, reading-status enum values (e.g., `{wants_to_read, reading, finished}`).
- **FR3 (reading speed):** add valid range (e.g., 10–1000 pages/hour), default value, and behavior when unset.
- **FR4 (estimate):** specify output format (hours? minutes? `Xh Ym`?), rounding/precision rule, and an acceptable latency target (e.g., p95 < 500 ms under demo load).

These map to the same gaps surfaced in the Measurability and Project-Type passes; addressing them once will lift all three scorecards.

### Overall Assessment

**Severity:** Pass (0% flagged FRs)

**Recommendation:** Functional Requirements demonstrate strong SMART quality overall. Tightening the data-model specificity on FR2, FR3, and FR4 would move them from 4.4 to ~4.8 each but is not strictly required at PRD level — these details can land in stories.

## Holistic Quality Assessment

### Document Flow & Coherence

**Assessment:** Good

**Strengths:**
- Linear, predictable structure: Overview → Motivation → Goals → Scope → Users → Components → Capabilities → Constraints → Quality → Journeys → Deliverables → Out of Scope. Easy for both human and LLM consumption.
- Tight thematic coherence: the architectural focus is restated in §1, reinforced in §3 (Goals), bounded in §4 (Non-Goals), locked down in §8 (Constraints), excluded in §12 (Out of Scope). The same idea appears five times in different framings — strong signal-discipline rather than redundancy.
- Strong section-to-section reinforcement: §6 ↔ §8 (components and the constraints that bind them); §7 ↔ §10 (capabilities and the journeys that exercise them); §3 ↔ §9 (goals and the operational quality bars that secure them).
- Self-aware authorial voice ("functional decomposition is the PM persona's job" in §7; "not open for the Architect persona to relax" in §8). These cues tell downstream BMAD agents exactly how to engage with the document.

**Areas for Improvement:**
- No table of contents or per-section traceability anchors. For a 12-section doc this is minor, but a TOC would help LLM agents that consume the PRD section-by-section.
- §7 and §10 say much of the same thing twice (capability + scenario). Healthy redundancy, but cross-references would make the relationship explicit (e.g., "FR4 → J3").
- §11 Deliverables mixes BMAD process artifacts (PRD, architecture, stories) with project deliverables (Dockerfiles, README). A short sub-headed split would clarify what's a BMAD output vs. a product output.

### Dual Audience Effectiveness

**For Humans:**
- Executive-friendly: Strong. §1 + §2 communicate vision and motivation in three short paragraphs; a non-engineer reviewer can grasp the project in under two minutes.
- Developer clarity: Strong on architectural intent (§6, §8) and operational constraints (§9). Weaker on domain detail (no data model, no API contracts) — but this is by design.
- Designer clarity: Weak. §5 is a single sentence, §10 lists journeys but does not enumerate screens, components, or interaction details. The downstream UX-design step will need to fill significant gaps.
- Stakeholder decision-making: Strong. The Non-Goals (§4) + Out of Scope (§12) pair makes "what we're not doing" easier to ratify than "what we are doing".

**For LLMs:**
- Machine-readable structure: Strong. ## headers, consistent bullet lists, **bold-prefix** convention for constraints/NFRs (`**Token isolation.**`, `**Containerized deployment.**`). Predictable parsing.
- UX-readiness: Weak. UX agent will have to invent the screen inventory; only the journeys constrain it.
- Architecture-readiness: Excellent. §6 + §8 give the architect persona a near-finished input. The architectural constraints are unusually specific for a PRD.
- Epic/Story-readiness: Good. Each FR + journey pair maps cleanly to a story arc, but the lack of FR IDs will force the story-creator persona to invent them.

**Dual Audience Score:** 4/5 — strong overall, with UX/designer clarity as the soft spot.

### BMAD PRD Principles Compliance

| Principle           | Status   | Notes |
|---------------------|----------|-------|
| Information Density | Met      | Zero anti-pattern hits in density pass. Direct, declarative voice throughout. |
| Measurability       | Partial  | FRs measurable in spirit; data-model details missing make exact testing harder. NFR3 lacks tool spec; NFR4 lacks pass/fail threshold. |
| Traceability        | Met      | No orphan FRs. Two soft chain gaps (G4 scope distinction; J6 error path → constraint). |
| Domain Awareness    | Met      | General domain; no regulatory frameworks apply. PII handling is light. |
| Zero Anti-Patterns  | Met      | Density pass clean. |
| Dual Audience       | Partial  | Strong for executives + architects; thin for designers. |
| Markdown Format     | Met      | Clean ## hierarchy, no nested header confusion. |

**Principles Met:** 5/7 fully, 2/7 partial. None failed.

### Overall Quality Rating

**Rating:** 4/5 — Good

This PRD is significantly above average for a capstone project. It would not look out of place as the input to a real architecture review. The main reasons it's not 5/5: (1) UX surface is intentionally thin in a way that downstream UX work cannot proceed without further input; (2) data-model details are absent at PRD level and will need to be invented in stories.

### Top 3 Improvements

1. **Add a minimal UX scope section (or fold it into §5/§7).**
   A single paragraph listing the screens (e.g., redirect-from-login, book list, book detail, settings, error states) and what each one shows is enough to unblock the UX-design step. This is the single highest-leverage change.

2. **Lock the data model.**
   Add either a Data Model subsection or inline annotations for: book.title length cap, book.page_count range, book.status enum values, reading_speed range/default/unit. This will improve SMART Specific scores from 3 → 4 on FR2/FR3/FR4 and prevent inconsistent assumptions during story generation.

3. **Assign FR identifiers and explicitly cross-link to journeys.**
   Convert §7 to a numbered FR list (FR-AUTH-01, FR-BOOK-01, FR-SPEED-01, FR-ESTIMATE-01, FR-LOGOUT-01) and add a one-line "Source journey: J*" to each. Stories normally cite the FR they implement; without IDs this traceability has to be reconstructed later.

### Summary

**This PRD is:** A high-discipline, architecturally-led PRD that nails the educational intent and gives the Architect persona an unusually complete brief, at the cost of leaving UX and data-model details thinner than ideal for downstream consumers.

**To make it great:** Tighten the UX scope, lock the data model, and assign FR IDs with explicit cross-links to journeys.

## Completeness Validation

### Template Completeness

**Template Variables Found:** 0 ✓
- Scanned for: `{var}`, `{{var}}`, `[TBD]`, `[TODO]`, `[placeholder]`, `XXX`, `TKTK`, `FIXME`
- No matches

### Content Completeness by Section

| Section | Status | Notes |
|---------|--------|-------|
| Executive Summary (§1)              | Complete   | Vision + primary purpose explicit |
| Background & Motivation (§2)        | Complete   | Course capstone + client mirror |
| Success Criteria / Goals (§3)       | Complete   | 6 goals stated |
| Non-Goals (§4)                      | Complete   | 5 exclusions |
| Users & Roles (§5)                  | Minimal    | Single role, one sentence — adequate but bare |
| System Components (§6)              | Complete   | 5 components + DB, with ownership |
| Application Capabilities / FRs (§7) | Complete*  | Content present; no FR IDs (flagged in measurability + holistic) |
| Architectural Constraints (§8)      | Complete   | 9 constraints, all measurable |
| Operational/Quality / NFRs (§9)     | Complete   | 5 NFRs |
| Primary User Journeys (§10)         | Complete   | 6 journeys including error path |
| Deliverables (§11)                  | Complete   | BMAD + product deliverables (could be sub-headed) |
| Out of Scope (§12)                  | Complete   | 5 explicit exclusions |

\* Content complete; missing IDs is a quality issue, not a completeness gap.

### Section-Specific Completeness

**Success Criteria Measurability:** Some
- G1, G2, G3, G5, G6 are clearly testable.
- G4 ("Demonstrate OAuth scope-based authorization enforced at the resource server") is measurable in spirit but does not state the specific scopes — these surface only in §8 C7 by inference.
- Each Goal is phrased as "Provide a working example of…" or "Demonstrate…" — verb framing is acceptable for an educational/demo project but slightly softer than typical PRD success-criteria phrasing.

**User Journeys Coverage:** Yes
- Single user role; all five primary flows + 1 error-path journey present.

**FRs Cover MVP Scope:** Yes
- The five FRs in §7 cover every Application Capability the project commits to. No capability gap.

**NFRs Have Specific Criteria:** Some
- NFR1 (deploy), NFR2 (coverage), NFR3 (a11y) — quantitative and specific.
- NFR4 (security review) — deliverable-based; no severity threshold.
- NFR5 (env config) — boolean.

### Frontmatter Completeness

**stepsCompleted:** Missing — PRD has no YAML frontmatter
**classification (domain, projectType):** Missing — no frontmatter
**inputDocuments:** Missing — no frontmatter
**date:** Missing — no frontmatter

**Frontmatter Completeness:** 0/4

The PRD is plain Markdown with no frontmatter block. For a hand-authored capstone PRD this is workable, but adding a small frontmatter section would help downstream BMAD skills (`bmad-validate-prd` already adapts to its absence; `bmad-create-architecture` may key off `classification.projectType`).

### Completeness Summary

**Overall Completeness:** 12/12 sections present (100% by structure)
**Critical Gaps:** 0
**Minor Gaps:** 2
1. PRD has no YAML frontmatter (classification, inputDocuments, date, stepsCompleted)
2. §5 Users & Roles is one sentence — technically complete for a single-role app, but verges on too thin

**Severity:** Warning — minor structural gaps; no blocker

**Recommendation:** Add a minimal YAML frontmatter block at the top of the PRD before locking it in:

```yaml
---
title: "Reading Time Estimator"
date: 2026-05-13
classification:
  domain: general
  projectType: web_app  # primary; also api_backend
inputDocuments: []
stepsCompleted: []
---
```

No other completeness blockers.

## Final Summary

### Overall Status: **Warning**

The PRD is usable and well above average for a capstone project. There are no critical blockers and no orphan requirements. Two themes account for almost all findings: (1) the deliberately-thin UX/data-model surface needs a small amount of tightening before downstream UX-design and story-creation can run cleanly; (2) the absence of FR identifiers and YAML frontmatter forces invention later in the pipeline.

### Quick Results

| Check                          | Result                    |
|--------------------------------|---------------------------|
| Format Detection               | BMAD Standard (6/6 core sections) |
| Information Density            | Pass (0 violations)       |
| Product Brief Coverage         | N/A (no brief)            |
| Measurability (FR + NFR)       | Warning (5 violations: 3 FR format, 2 NFR template) |
| Traceability                   | Warning (2 soft gaps; 0 orphans) |
| Implementation Leakage         | Pass (1 borderline — Keycloak) |
| Domain Compliance              | N/A (general domain)      |
| Project-Type Compliance        | Warning (web_app UX thin) |
| SMART FR Quality               | Pass (avg 4.56 / 5.0)     |
| Holistic Quality               | 4/5 Good                  |
| Completeness                   | Warning (no frontmatter)  |

### Critical Issues: **None**

### Warnings (in priority order)

1. **UX surface is thin** — no screen inventory, no responsive-design statement. Downstream UX design will need a baseline.
2. **Data model details are absent** — book.title length, book.page_count range, book.status enum, reading_speed range/default/unit, estimate format/precision/latency target.
3. **No FR identifiers and no YAML frontmatter** — both downstream traceability issues.
4. **NFR3 (Accessibility) missing tool spec; NFR4 (Security review) missing pass/fail threshold.**
5. **Traceability soft gaps** — G4 (scope distinction) implicit in journeys; J6 (error path) traces to a constraint rather than an FR.
6. **"Keycloak" named as the authorization-server product** — borderline implementation leakage; defensible given course context.

### Strengths

- Zero conversational filler / wordy phrases / redundancies.
- Vision-to-Goals coherence is tight and re-stated across §1, §3, §4, §8, §12.
- Architectural constraints (§8) are unusually specific and load-bearing — the architect persona gets a near-finished brief.
- All five FRs trace cleanly to a user journey; zero orphans.
- Out-of-scope discipline (§4 + §12) makes review/approval easy.
- §10 (journeys) includes an error-path scenario, which is rare at PRD level and very useful for E2E test planning.
- §9 NFR2 sets concrete coverage and E2E test minimums tied to the journeys in §10.

### Top 3 Improvements (from Holistic Quality)

1. **Add a minimal UX scope section** — list the screens (login redirect, book list, book detail, settings, error states) and what each shows. Highest-leverage single edit.
2. **Lock the data model** — title/page-count/status/reading-speed/estimate constraints. Lifts SMART Specific scores on FR2/3/4 from 3 → 4.
3. **Assign FR identifiers (FR-AUTH-01 …) and cross-link to journeys.** Enables story traceability without later reconstruction.

### Recommendation

**PRD is usable.** Address the top 3 improvements before locking in for the architecture phase. None of the warnings prevent moving forward, but each will compound downstream if not addressed in the PRD.

## Fixes Applied (post-validation)

The following mechanical fixes were applied to `PRD.md` after validation, with user approval:

1. **YAML frontmatter added** at the top of the PRD: `title`, `date`, `classification.domain`, `classification.projectType` (`[web_app, api_backend]`), `inputDocuments`, `stepsCompleted`. → Resolves completeness warning (frontmatter present: now true).

2. **FR identifiers assigned and journey cross-links added** in §7:
   - `FR-AUTH-01` → J1
   - `FR-BOOK-01` → J2
   - `FR-SPEED-01` → J4 (rephrased from "Users have…" to "Users can view and update…")
   - `FR-ESTIMATE-01` → J3
   - `FR-LOGOUT-01` → J5
   → Resolves the "no FR IDs" downstream-traceability issue and the SMART Specific=3 on FR3.

3. **FR phrasing normalized** to the "Users can …" form on FR1, FR2, FR3. → Resolves all 3 FR format violations from the Measurability pass.

4. **§10 journey identifiers added** (J1–J6) to match the new FR cross-links.

5. **§4 Non-Goals extended** with: "Responsive or multi-viewport SPA layout; the SPA targets desktop browsers only." → Resolves the project-type "responsive design not stated" gap.

6. **Keycloak abstracted** to "an OpenID Connect provider (Keycloak in this implementation)" in §6, and "the provider's realm" in §8 C9, and "pre-configured authorization-server realm" in §11. → Resolves the borderline implementation-leakage flag while preserving the reference-implementation note.

### Post-fix Status Delta

- Measurability format violations: 3 → 0
- Implementation leakage borderline: 1 → 0
- Project-type "responsive not stated" gap: closed
- Completeness frontmatter gap: closed
- Downstream traceability friction (FR IDs): resolved

### Remaining (Not Auto-Fixed)

These require content decisions and were intentionally left for the user / next BMAD step:

- **UX scope section** (screen inventory, what each screen shows) — belongs to `bmad-create-ux-design`
- **Data model details** (title length cap, page-count range, status enum values, reading-speed range/default/unit, estimate format/precision/latency target)
- **NFR3 accessibility tool** (axe-core / Lighthouse / Pa11y — your call)
- **NFR4 security-review pass/fail threshold** (e.g., "zero high/critical findings unmitigated")
- **FR for J6 error-handling** (or accept that J6 traces only to constraint C8)
- **G4 scope-distinction surfacing** in §10 (mention `reading-speed:read` vs `reading-speed:write`)

## Fixes Applied (round 2, 2026-05-14)

User selected a second batch of mechanical fixes plus an explicit scope decision (accessibility out of scope):

7. **FR-ERROR-01 added** to §7 with cross-link to J6. → Closes the J6 traceability soft gap (J6 now traces to a positive FR, not just constraint C8).

8. **OAuth scope names added to §8 C7 and §10 J3/J4.** Canonical scopes are now `reading-speed:read` (for retrieving the speed and computing estimates, used in J3) and `reading-speed:write` (for modifying the speed, used in J4). → Closes the G4 traceability soft gap by making the scope distinction explicit in both constraint and journey text.

9. **§11 Deliverables re-organized** into three sub-headed groups: "BMAD process artifacts" / "Product deliverables" / "Quality and compliance". Improves dual-audience parseability; no content semantics changed beyond accessibility deletion (see #10).

10. **Accessibility explicitly de-scoped.**
    - Removed NFR3 (WCAG AA audit) from §9.
    - Added explicit Non-Goal to §4: "Accessibility hardening: no WCAG conformance audit, no assistive-technology testing, no a11y-focused UX work. The SPA uses reasonable HTML semantics by default but is not assessed against any accessibility standard."
    - Removed "accessibility audit results" from §11 deliverables (now folded into the re-shaped §11).
    - Note: this is a project-level scope decision recorded as a [persistent project memory](file://memory/project_bmad_books_scope.md).

### Post-Round-2 Status Delta

- Traceability soft gaps: 2 → 0 (J6 has FR-ERROR-01; G4 scopes named)
- NFR3 (Accessibility): removed — no longer a measurability/template gap; matches an explicit Non-Goal
- §11 structure: improved (sub-headed, no longer mixes process artifacts with product deliverables)
- Total open warnings (excluding intentional content gaps): now limited to data-model details + NFR4 security threshold

### Still Not Auto-Fixed (intentional content decisions)

- **UX scope section** — belongs to `bmad-create-ux-design`
- **Data model details** (title length, page-count range, status enum, speed range/default/unit, estimate format/precision/latency)
- **NFR4 security-review pass/fail threshold** (e.g., "zero high/critical findings unmitigated")
