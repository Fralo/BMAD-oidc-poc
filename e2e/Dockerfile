# Story 1.11: Playwright runner image used by the `e2e` compose profile.
# Pinned to Node 20 LTS (Playwright 1.49.x requires Node >=18; choose 20 for stability).
# Only chromium is installed to keep the image lean — the AC scopes the harness
# to a single browser project.
FROM node:20-bookworm-slim AS playwright

# `--with-deps` pulls the OS libs chromium needs (libnss3, libxss1, etc.) so the
# final image runs out of the box. `playwright install` itself downloads only the
# chromium binary into the default cache location (/root/.cache/ms-playwright).
WORKDIR /e2e

# 1) Install npm deps first to maximize layer cache reuse on fixture/spec churn.
COPY package.json package-lock.json ./
RUN npm ci

# 2) Install only the chromium browser + its OS dependencies.
RUN npx playwright install --with-deps chromium

# 3) Copy the rest of the e2e source (fixtures/, tests/, playwright.config.ts).
COPY . .

# The runner is one-shot; compose `restart: "no"` honors that.
# `--pass-with-no-tests` makes the empty-tests/ baseline (Story 1.11) exit 0
# even though Playwright >=1.49 exits 1 on no-tests-found by default. Once
# Story 1.13 lands real specs, this flag becomes a no-op.
CMD ["npx", "playwright", "test", "--pass-with-no-tests"]
