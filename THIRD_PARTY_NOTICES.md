# Third-party notices

The application source is clean-room and no external library source has been vendored. Runtime and direct dependencies are built into the Compose images. Preserve each distribution’s upstream copyright/license files when redistributing; the root notices below preserve project-level attributions and standard license text.

| Distribution | Declared use | License family | Copyright attribution | Upstream license |
| --- | --- | --- | --- | --- |
| Python 3.11 | API and sandbox runtime | Python-2.0 / PSF License 2 | Python Software Foundation and earlier contributors | <https://docs.python.org/3/license.html> |
| Node.js 22 | Next.js runtime | MIT with separately licensed bundled components | Copyright Node.js contributors | <https://github.com/nodejs/node/blob/main/LICENSE> |
| PostgreSQL 16 | Database container | PostgreSQL License | Portions Copyright © 1996–2026, The PostgreSQL Global Development Group; Portions Copyright © 1994, The Regents of the University of California | <https://www.postgresql.org/about/licence/> |
| Redis 7.2 | Cache container | BSD-3-Clause | Copyright (c) 2006–2020, Salvatore Sanfilippo | <https://github.com/redis/redis/blob/7.2/COPYING> |
| Qdrant | Vector database container | Apache-2.0 | Upstream contributors; image attribution files remain intact | <https://github.com/qdrant/qdrant/blob/master/LICENSE> |
| Caddy 2 | Automatic HTTPS reverse proxy | Apache-2.0 | Matthew Holt and Caddy contributors | <https://github.com/caddyserver/caddy/blob/master/LICENSE> |
| GitHub Actions (checkout, setup-python, setup-node) | MIT | GitHub action contributors | <https://github.com/actions/checkout/blob/main/LICENSE> |
| Docker GitHub Actions (QEMU, Buildx, registry login, build-push) | Apache-2.0 | Docker contributors | <https://github.com/docker/build-push-action/blob/master/LICENSE> |

Python-2.0 is included in the expanded dependency policy. PostgreSQL and Node.js are base runtimes rather than npm/PyPI application packages; Node.js bundles separately licensed components whose notices remain in the distribution image.

## API, worker, and Python package dependencies

The API and worker install the pinned direct distributions in `apps/api/requirements.txt`. Python source is built from the Nexus monorepo; third-party package source is installed from upstream wheels and remains unmodified. Preserve the wheel license files in the image when redistributing.

| Library | License | Copyright attribution | Upstream notice |
| --- | --- | --- | --- |
| FastAPI | MIT | Sebastián Ramírez and contributors | <https://github.com/fastapi/fastapi/blob/master/LICENSE> |
| Starlette | BSD-3-Clause | Encode contributors | <https://github.com/encode/starlette/blob/master/LICENSE.md> |
| Uvicorn | BSD-3-Clause | Encode contributors | <https://github.com/encode/uvicorn/blob/master/LICENSE.md> |
| Pydantic | MIT | Pydantic Services Inc. and contributors | <https://github.com/pydantic/pydantic/blob/main/LICENSE> |
| SQLAlchemy and Alembic | MIT | SQLAlchemy authors; Alembic by Michael Bayer and contributors | <https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE> |
| asyncpg | Apache-2.0 | MagicStack and contributors | <https://github.com/MagicStack/asyncpg/blob/master/LICENSE> |
| cryptography | Apache-2.0 OR BSD-3-Clause | Python Cryptographic Authority and contributors | <https://github.com/pyca/cryptography/blob/main/LICENSE> |
| LiteLLM | MIT | Berri AI and contributors | <https://github.com/BerriAI/litellm/blob/main/LICENSE> |
| AutoGen agentchat/core/ext | MIT | Microsoft Corporation and contributors | <https://github.com/microsoft/autogen/blob/main/LICENSE> |
| CrewAI | MIT | CrewAI, Inc. and contributors | <https://github.com/crewAIInc/crewAI/blob/main/LICENSE> |
| Celery, Kombu, billiard, py-amqp, vine | BSD-3-Clause | Celery contributors | <https://github.com/celery/celery/blob/main/LICENSE> |
| redis-py | MIT | Redis contributors | <https://github.com/redis/redis-py/blob/master/LICENSE> |
| Qdrant Python client | Apache-2.0 | Qdrant contributors | <https://github.com/qdrant/qdrant-client/blob/master/LICENSE> |
| LlamaIndex core | MIT | LlamaIndex contributors | <https://github.com/run-llama/llama_index/blob/main/LICENSE> |
| MCP Python SDK 1.26.0 | MIT | Model Context Protocol contributors | <https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE> |
| pypdf | BSD-3-Clause | pypdf contributors | <https://github.com/py-pdf/pypdf/blob/main/LICENSE> |
| python-docx | MIT | Steve Canny and contributors | <https://github.com/python-openxml/python-docx/blob/master/LICENSE> |
| pandas 2.2.3 | BSD-3-Clause | pandas development team and contributors | <https://github.com/pandas-dev/pandas/blob/main/LICENSE> |
| matplotlib 3.9.2 | PSF-based license | Matplotlib development team and contributors | <https://github.com/matplotlib/matplotlib/blob/main/LICENSE> |
| openpyxl 3.1.5 | MIT | See upstream contributor notices | <https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/3.1/LICENCE.rst> |
| Pillow 11.0.0 | MIT-CMU (HPND) permissive | Jeffrey A. Clark and contributors | <https://github.com/python-pillow/Pillow/blob/main/LICENSE> |
| Electron 33 (desktop app) | MIT; bundles Chromium (BSD-3-Clause and component licenses) and FFmpeg (LGPL, dynamically linked) | Electron contributors; GitHub Inc. | <https://github.com/electron/electron/blob/main/LICENSE> |
| electron-builder 25 (desktop packaging, dev only) | MIT | Vladimir Krivosheev and contributors | <https://github.com/electron-userland/electron-builder/blob/master/LICENSE> |
| FFmpeg (Debian package, sandbox image) | LGPL-2.1+ / GPL-2+ depending on build; separate executable, never linked or imported | FFmpeg developers | <https://ffmpeg.org/legal.html> |
| Chromium (Debian package, sandbox image) | BSD-3-Clause with bundled components under their own licenses; separate executable | The Chromium Authors | <https://chromium.googlesource.com/chromium/src/+/main/LICENSE> |
| pytest 9.2.0 | MIT | Holger Krekel and pytest contributors | <https://github.com/pytest-dev/pytest/blob/main/LICENSE> |
| jsonschema | MIT | Julian Berman and contributors | <https://github.com/python-jsonschema/jsonschema/blob/main/COPYING> |
| HTTPX | BSD-3-Clause | Encode contributors | <https://github.com/encode/httpx/blob/master/LICENSE.md> |

The Compose API applies database migrations before startup. The worker includes the same application packages and runs queued tasks plus routine scheduling.

## Phase 6 web application dependencies

The web source uses Next.js 15, React 19, the flow canvas library, and Tailwind CSS. The installed frontend graph is checked by `scripts/check-npm-licenses.mjs`; the Docker build runs the check before `next build`. The production image disables optional packages and uses unoptimized images so it does not include the optional native LGPL image optimizer. No dependency source is vendored.

| Library | Direct package license | Copyright attribution | Upstream notice |
|---|---|---|---|
| Next.js | MIT | Vercel and contributors | <https://github.com/vercel/next.js/blob/canary/license.md> |
| React and React DOM | MIT | Meta Platforms, Inc. and contributors | <https://github.com/facebook/react/blob/main/LICENSE> |
| @xyflow/react | MIT | XYFlow contributors | <https://github.com/xyflow/xyflow/blob/main/LICENSE> |
| Tailwind CSS | MIT | Tailwind Labs, Inc. and contributors | <https://github.com/tailwindlabs/tailwindcss/blob/main/LICENSE> |
| TypeScript | Apache-2.0 | Microsoft Corporation | <https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt> |
| ESLint and eslint-config-next | MIT | OpenJS Foundation and Vercel contributors | <https://github.com/eslint/eslint/blob/main/LICENSE> |
| PostCSS and Autoprefixer | MIT | Andrey Sitnik and contributors | <https://github.com/postcss/postcss/blob/main/LICENSE> |
| React and Node type declarations | MIT | DefinitelyTyped contributors | <https://github.com/DefinitelyTyped/DefinitelyTyped/blob/master/LICENSE> |

The current lockfile resolves these additional license families and packages:

| Package(s) | License | Attribution / source |
|---|---|---|
| `@ungap/structured-clone@1.4.0` | ISC | Andrea Giammarchi and contributors; <https://github.com/ungap/structuredClone> |
| `anymatch@3.1.3`, `electron-to-chromium@1.5.467`, `eslint-import-resolver-typescript@3.10.1`, `flatted@3.4.4`, `fs.realpath@1.0.0`, `glob-parent@5.1.2` and `@6.0.2`, `glob@7.2.3`, `inflight@1.0.6`, `inherits@2.0.4`, `isexe@2.0.0`, `minimatch@3.1.5`, `once@1.4.0`, `picocolors@1.1.1`, `rimraf@3.0.2`, `semver@6.3.1` and `@7.8.5`, `which@2.0.2`, `wrappy@1.0.2`, `yaml@2.9.1` | ISC | Copyright notices are included in each package's upstream `LICENSE` file. |
| `argparse@2.0.1` | Python-2.0 | Python Software Foundation; <https://github.com/nodeca/argparse> |
| `axe-core@4.14.0` | MPL-2.0, unmodified file-level dependency | Deque Systems, Inc.; <https://github.com/dequelabs/axe-core/blob/develop/LICENSE> |
| `caniuse-lite@1.0.30001820` | CC-BY-4.0 | Can I Use contributors; <https://github.com/andreruffert/caniuse-lite> |
| `language-subtag-registry@0.3.23` | CC0-1.0 | Contributors; <https://github.com/mattcg/language-subtag-registry> |
| `type-fest@0.20.2` | MIT OR CC0-1.0 | Sindre Sorhus; <https://github.com/sindresorhus/type-fest> |

The lockfile records optional `@img/sharp-libvips-*` packages under LGPL-3.0-or-later for multiple host platforms. Compose uses `pnpm install --no-optional`, and `next/image` is configured with optimization disabled, so these optional packages are not included in the production runtime image. MPL-2.0 files are used only as unmodified third-party files; their file-level terms remain applicable.

## Complete installed npm dependency inventory

The host platform resolves 340 reachable npm packages from the frozen lockfile; the ARM64 production image built with optional packages disabled resolves 331. This inventory records each package version in the host lockfile graph and its declared license metadata. Package upstream copyright holders and full notices are preserved in each package's upstream `LICENSE`/`NOTICE` files inside the distribution; the tables above identify principal project attributions.

| Package and version | Declared license |
|---|---|
| [`@alloc/quick-lru@5.3.0`](https://www.npmjs.com/package/@alloc/quick-lru@5.3.0) | MIT |
| [`@eslint-community/eslint-utils@4.10.1`](https://www.npmjs.com/package/@eslint-community/eslint-utils@4.10.1) | MIT |
| [`@eslint-community/regexpp@4.12.2`](https://www.npmjs.com/package/@eslint-community/regexpp@4.12.2) | MIT |
| [`@eslint/eslintrc@2.1.4`](https://www.npmjs.com/package/@eslint/eslintrc@2.1.4) | MIT |
| [`@eslint/js@8.57.1`](https://www.npmjs.com/package/@eslint/js@8.57.1) | MIT |
| [`@humanwhocodes/config-array@0.13.0`](https://www.npmjs.com/package/@humanwhocodes/config-array@0.13.0) | Apache-2.0 |
| [`@humanwhocodes/module-importer@1.0.1`](https://www.npmjs.com/package/@humanwhocodes/module-importer@1.0.1) | Apache-2.0 |
| [`@humanwhocodes/object-schema@2.0.3`](https://www.npmjs.com/package/@humanwhocodes/object-schema@2.0.3) | BSD-3-Clause |
| [`@img/colour@1.1.0`](https://www.npmjs.com/package/@img/colour@1.1.0) | MIT |
| [`@img/sharp-darwin-arm64@0.35.5`](https://www.npmjs.com/package/@img/sharp-darwin-arm64@0.35.5) | Apache-2.0 |
| [`@img/sharp-libvips-darwin-arm64@1.3.4`](https://www.npmjs.com/package/@img/sharp-libvips-darwin-arm64@1.3.4) | LGPL-3.0-or-later |
| [`@jridgewell/gen-mapping@0.3.13`](https://www.npmjs.com/package/@jridgewell/gen-mapping@0.3.13) | MIT |
| [`@jridgewell/resolve-uri@3.1.2`](https://www.npmjs.com/package/@jridgewell/resolve-uri@3.1.2) | MIT |
| [`@jridgewell/sourcemap-codec@1.6.0`](https://www.npmjs.com/package/@jridgewell/sourcemap-codec@1.6.0) | MIT |
| [`@jridgewell/trace-mapping@0.3.31`](https://www.npmjs.com/package/@jridgewell/trace-mapping@0.3.31) | MIT |
| [`@next/env@15.5.28`](https://www.npmjs.com/package/@next/env@15.5.28) | MIT |
| [`@next/eslint-plugin-next@15.5.28`](https://www.npmjs.com/package/@next/eslint-plugin-next@15.5.28) | MIT |
| [`@next/swc-darwin-arm64@15.5.28`](https://www.npmjs.com/package/@next/swc-darwin-arm64@15.5.28) | MIT |
| [`@nodelib/fs.scandir@2.1.5`](https://www.npmjs.com/package/@nodelib/fs.scandir@2.1.5) | MIT |
| [`@nodelib/fs.stat@2.0.5`](https://www.npmjs.com/package/@nodelib/fs.stat@2.0.5) | MIT |
| [`@nodelib/fs.walk@1.2.8`](https://www.npmjs.com/package/@nodelib/fs.walk@1.2.8) | MIT |
| [`@nolyfill/is-core-module@1.0.39`](https://www.npmjs.com/package/@nolyfill/is-core-module@1.0.39) | MIT |
| [`@rtsao/scc@1.1.0`](https://www.npmjs.com/package/@rtsao/scc@1.1.0) | MIT |
| [`@rushstack/eslint-patch@1.16.1`](https://www.npmjs.com/package/@rushstack/eslint-patch@1.16.1) | MIT |
| [`@swc/helpers@0.5.15`](https://www.npmjs.com/package/@swc/helpers@0.5.15) | Apache-2.0 |
| [`@types/json5@0.0.29`](https://www.npmjs.com/package/@types/json5@0.0.29) | MIT |
| [`@types/node@22.20.5`](https://www.npmjs.com/package/@types/node@22.20.5) | MIT |
| [`@types/react-dom@19.3.0`](https://www.npmjs.com/package/@types/react-dom@19.3.0) | MIT |
| [`@types/react@19.3.0`](https://www.npmjs.com/package/@types/react@19.3.0) | MIT |
| [`@typescript-eslint/eslint-plugin@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/eslint-plugin@8.72.1) | MIT |
| [`@typescript-eslint/parser@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/parser@8.72.1) | MIT |
| [`@typescript-eslint/project-service@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/project-service@8.72.1) | MIT |
| [`@typescript-eslint/scope-manager@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/scope-manager@8.72.1) | MIT |
| [`@typescript-eslint/tsconfig-utils@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/tsconfig-utils@8.72.1) | MIT |
| [`@typescript-eslint/type-utils@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/type-utils@8.72.1) | MIT |
| [`@typescript-eslint/types@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/types@8.72.1) | MIT |
| [`@typescript-eslint/typescript-estree@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/typescript-estree@8.72.1) | MIT |
| [`@typescript-eslint/utils@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/utils@8.72.1) | MIT |
| [`@typescript-eslint/visitor-keys@8.72.1`](https://www.npmjs.com/package/@typescript-eslint/visitor-keys@8.72.1) | MIT |
| [`@ungap/structured-clone@1.4.0`](https://www.npmjs.com/package/@ungap/structured-clone@1.4.0) | ISC |
| [`@unrs/resolver-binding-darwin-arm64@1.12.2`](https://www.npmjs.com/package/@unrs/resolver-binding-darwin-arm64@1.12.2) | MIT |
| [`@xyflow/react@12.12.0`](https://www.npmjs.com/package/@xyflow/react@12.12.0) | MIT |
| [`@xyflow/system@0.0.83`](https://www.npmjs.com/package/@xyflow/system@0.0.83) | MIT |
| [`acorn-jsx@5.3.2`](https://www.npmjs.com/package/acorn-jsx@5.3.2) | MIT |
| [`acorn@8.19.0`](https://www.npmjs.com/package/acorn@8.19.0) | MIT |
| [`ajv@6.15.0`](https://www.npmjs.com/package/ajv@6.15.0) | MIT |
| [`ansi-regex@5.0.1`](https://www.npmjs.com/package/ansi-regex@5.0.1) | MIT |
| [`ansi-styles@4.3.0`](https://www.npmjs.com/package/ansi-styles@4.3.0) | MIT |
| [`any-promise@1.3.0`](https://www.npmjs.com/package/any-promise@1.3.0) | MIT |
| [`anymatch@3.1.3`](https://www.npmjs.com/package/anymatch@3.1.3) | ISC |
| [`arg@5.0.2`](https://www.npmjs.com/package/arg@5.0.2) | MIT |
| [`argparse@2.0.1`](https://www.npmjs.com/package/argparse@2.0.1) | Python-2.0 |
| [`aria-query@5.3.2`](https://www.npmjs.com/package/aria-query@5.3.2) | Apache-2.0 |
| [`array-buffer-byte-length@1.0.2`](https://www.npmjs.com/package/array-buffer-byte-length@1.0.2) | MIT |
| [`array-includes@3.2.0`](https://www.npmjs.com/package/array-includes@3.2.0) | MIT |
| [`array.prototype.findlast@1.2.5`](https://www.npmjs.com/package/array.prototype.findlast@1.2.5) | MIT |
| [`array.prototype.findlastindex@1.2.6`](https://www.npmjs.com/package/array.prototype.findlastindex@1.2.6) | MIT |
| [`array.prototype.flat@1.3.3`](https://www.npmjs.com/package/array.prototype.flat@1.3.3) | MIT |
| [`array.prototype.flatmap@1.3.3`](https://www.npmjs.com/package/array.prototype.flatmap@1.3.3) | MIT |
| [`array.prototype.tosorted@1.1.4`](https://www.npmjs.com/package/array.prototype.tosorted@1.1.4) | MIT |
| [`arraybuffer.prototype.slice@1.0.4`](https://www.npmjs.com/package/arraybuffer.prototype.slice@1.0.4) | MIT |
| [`ast-types-flow@0.0.8`](https://www.npmjs.com/package/ast-types-flow@0.0.8) | MIT |
| [`async-function@1.0.0`](https://www.npmjs.com/package/async-function@1.0.0) | MIT |
| [`autoprefixer@10.6.2`](https://www.npmjs.com/package/autoprefixer@10.6.2) | MIT |
| [`available-typed-arrays@1.0.7`](https://www.npmjs.com/package/available-typed-arrays@1.0.7) | MIT |
| [`axe-core@4.14.0`](https://www.npmjs.com/package/axe-core@4.14.0) | MPL-2.0 |
| [`axobject-query@4.1.0`](https://www.npmjs.com/package/axobject-query@4.1.0) | Apache-2.0 |
| [`balanced-match@1.0.2`](https://www.npmjs.com/package/balanced-match@1.0.2) | MIT |
| [`baseline-browser-mapping@2.11.34`](https://www.npmjs.com/package/baseline-browser-mapping@2.11.34) | Apache-2.0 |
| [`binary-extensions@2.3.0`](https://www.npmjs.com/package/binary-extensions@2.3.0) | MIT |
| [`brace-expansion@1.1.21`](https://www.npmjs.com/package/brace-expansion@1.1.21) | MIT |
| [`braces@3.0.3`](https://www.npmjs.com/package/braces@3.0.3) | MIT |
| [`browserslist@4.29.5`](https://www.npmjs.com/package/browserslist@4.29.5) | MIT |
| [`call-bind-apply-helpers@1.0.2`](https://www.npmjs.com/package/call-bind-apply-helpers@1.0.2) | MIT |
| [`call-bind@1.0.9`](https://www.npmjs.com/package/call-bind@1.0.9) | MIT |
| [`call-bound@1.0.4`](https://www.npmjs.com/package/call-bound@1.0.4) | MIT |
| [`camelcase-css@2.0.1`](https://www.npmjs.com/package/camelcase-css@2.0.1) | MIT |
| [`caniuse-lite@1.0.30001820`](https://www.npmjs.com/package/caniuse-lite@1.0.30001820) | CC-BY-4.0 |
| [`chalk@4.1.2`](https://www.npmjs.com/package/chalk@4.1.2) | MIT |
| [`chokidar@3.6.0`](https://www.npmjs.com/package/chokidar@3.6.0) | MIT |
| [`client-only@0.0.1`](https://www.npmjs.com/package/client-only@0.0.1) | MIT |
| [`color-convert@2.0.1`](https://www.npmjs.com/package/color-convert@2.0.1) | MIT |
| [`color-name@1.1.4`](https://www.npmjs.com/package/color-name@1.1.4) | MIT |
| [`commander@4.1.1`](https://www.npmjs.com/package/commander@4.1.1) | MIT |
| [`concat-map@0.0.1`](https://www.npmjs.com/package/concat-map@0.0.1) | MIT |
| [`cross-spawn@7.0.6`](https://www.npmjs.com/package/cross-spawn@7.0.6) | MIT |
| [`cssesc@3.0.0`](https://www.npmjs.com/package/cssesc@3.0.0) | MIT |
| [`damerau-levenshtein@1.0.8`](https://www.npmjs.com/package/damerau-levenshtein@1.0.8) | BSD-2-Clause |
| [`data-view-buffer@1.0.2`](https://www.npmjs.com/package/data-view-buffer@1.0.2) | MIT |
| [`data-view-byte-length@1.0.2`](https://www.npmjs.com/package/data-view-byte-length@1.0.2) | MIT |
| [`data-view-byte-offset@1.0.1`](https://www.npmjs.com/package/data-view-byte-offset@1.0.1) | MIT |
| [`debug@3.2.7`](https://www.npmjs.com/package/debug@3.2.7) | MIT |
| [`debug@4.4.3`](https://www.npmjs.com/package/debug@4.4.3) | MIT |
| [`deep-is@0.1.4`](https://www.npmjs.com/package/deep-is@0.1.4) | MIT |
| [`define-data-property@1.1.4`](https://www.npmjs.com/package/define-data-property@1.1.4) | MIT |
| [`define-properties@1.2.1`](https://www.npmjs.com/package/define-properties@1.2.1) | MIT |
| [`detect-libc@2.1.2`](https://www.npmjs.com/package/detect-libc@2.1.2) | Apache-2.0 |
| [`didyoumean@1.2.2`](https://www.npmjs.com/package/didyoumean@1.2.2) | Apache-2.0 |
| [`dlv@1.1.3`](https://www.npmjs.com/package/dlv@1.1.3) | MIT |
| [`doctrine@2.1.0`](https://www.npmjs.com/package/doctrine@2.1.0) | Apache-2.0 |
| [`doctrine@3.0.0`](https://www.npmjs.com/package/doctrine@3.0.0) | Apache-2.0 |
| [`dunder-proto@1.0.1`](https://www.npmjs.com/package/dunder-proto@1.0.1) | MIT |
| [`electron-to-chromium@1.5.467`](https://www.npmjs.com/package/electron-to-chromium@1.5.467) | ISC |
| [`emoji-regex@9.2.2`](https://www.npmjs.com/package/emoji-regex@9.2.2) | MIT |
| [`es-abstract-get@1.0.0`](https://www.npmjs.com/package/es-abstract-get@1.0.0) | MIT |
| [`es-abstract@1.24.2`](https://www.npmjs.com/package/es-abstract@1.24.2) | MIT |
| [`es-define-property@1.0.1`](https://www.npmjs.com/package/es-define-property@1.0.1) | MIT |
| [`es-errors@1.3.0`](https://www.npmjs.com/package/es-errors@1.3.0) | MIT |
| [`es-iterator-helpers@1.4.0`](https://www.npmjs.com/package/es-iterator-helpers@1.4.0) | MIT |
| [`es-object-atoms@1.1.2`](https://www.npmjs.com/package/es-object-atoms@1.1.2) | MIT |
| [`es-set-tostringtag@2.1.0`](https://www.npmjs.com/package/es-set-tostringtag@2.1.0) | MIT |
| [`es-shim-unscopables@1.1.0`](https://www.npmjs.com/package/es-shim-unscopables@1.1.0) | MIT |
| [`es-to-primitive@1.3.4`](https://www.npmjs.com/package/es-to-primitive@1.3.4) | MIT |
| [`escalade@3.2.0`](https://www.npmjs.com/package/escalade@3.2.0) | MIT |
| [`escape-string-regexp@4.0.0`](https://www.npmjs.com/package/escape-string-regexp@4.0.0) | MIT |
| [`eslint-config-next@15.5.28`](https://www.npmjs.com/package/eslint-config-next@15.5.28) | MIT |
| [`eslint-import-resolver-node@0.3.10`](https://www.npmjs.com/package/eslint-import-resolver-node@0.3.10) | MIT |
| [`eslint-import-resolver-typescript@3.10.1`](https://www.npmjs.com/package/eslint-import-resolver-typescript@3.10.1) | ISC |
| [`eslint-module-utils@2.14.0`](https://www.npmjs.com/package/eslint-module-utils@2.14.0) | MIT |
| [`eslint-plugin-import@2.32.0`](https://www.npmjs.com/package/eslint-plugin-import@2.32.0) | MIT |
| [`eslint-plugin-jsx-a11y@6.10.2`](https://www.npmjs.com/package/eslint-plugin-jsx-a11y@6.10.2) | MIT |
| [`eslint-plugin-react-hooks@5.2.0`](https://www.npmjs.com/package/eslint-plugin-react-hooks@5.2.0) | MIT |
| [`eslint-plugin-react@7.37.5`](https://www.npmjs.com/package/eslint-plugin-react@7.37.5) | MIT |
| [`eslint-scope@7.2.2`](https://www.npmjs.com/package/eslint-scope@7.2.2) | BSD-2-Clause |
| [`eslint-visitor-keys@3.4.3`](https://www.npmjs.com/package/eslint-visitor-keys@3.4.3) | Apache-2.0 |
| [`eslint@8.57.1`](https://www.npmjs.com/package/eslint@8.57.1) | MIT |
| [`espree@9.6.1`](https://www.npmjs.com/package/espree@9.6.1) | BSD-2-Clause |
| [`esquery@1.7.0`](https://www.npmjs.com/package/esquery@1.7.0) | BSD-3-Clause |
| [`esrecurse@4.3.0`](https://www.npmjs.com/package/esrecurse@4.3.0) | BSD-2-Clause |
| [`estraverse@5.3.0`](https://www.npmjs.com/package/estraverse@5.3.0) | BSD-2-Clause |
| [`esutils@2.0.3`](https://www.npmjs.com/package/esutils@2.0.3) | BSD-2-Clause |
| [`fast-deep-equal@3.1.3`](https://www.npmjs.com/package/fast-deep-equal@3.1.3) | MIT |
| [`fast-glob@3.3.3`](https://www.npmjs.com/package/fast-glob@3.3.3) | MIT |
| [`fast-json-stable-stringify@2.1.0`](https://www.npmjs.com/package/fast-json-stable-stringify@2.1.0) | MIT |
| [`fast-levenshtein@2.0.6`](https://www.npmjs.com/package/fast-levenshtein@2.0.6) | MIT |
| [`fdir@6.5.0`](https://www.npmjs.com/package/fdir@6.5.0) | MIT |
| [`file-entry-cache@6.0.1`](https://www.npmjs.com/package/file-entry-cache@6.0.1) | MIT |
| [`fill-range@7.1.1`](https://www.npmjs.com/package/fill-range@7.1.1) | MIT |
| [`find-up@5.0.0`](https://www.npmjs.com/package/find-up@5.0.0) | MIT |
| [`flat-cache@3.2.0`](https://www.npmjs.com/package/flat-cache@3.2.0) | MIT |
| [`flatted@3.4.4`](https://www.npmjs.com/package/flatted@3.4.4) | ISC |
| [`for-each@0.3.5`](https://www.npmjs.com/package/for-each@0.3.5) | MIT |
| [`fraction.js@5.3.4`](https://www.npmjs.com/package/fraction.js@5.3.4) | MIT |
| [`fs.realpath@1.0.0`](https://www.npmjs.com/package/fs.realpath@1.0.0) | ISC |
| [`fsevents@2.3.3`](https://www.npmjs.com/package/fsevents@2.3.3) | MIT |
| [`function-bind@1.1.2`](https://www.npmjs.com/package/function-bind@1.1.2) | MIT |
| [`function.prototype.name@1.2.0`](https://www.npmjs.com/package/function.prototype.name@1.2.0) | MIT |
| [`functions-have-names@1.2.3`](https://www.npmjs.com/package/functions-have-names@1.2.3) | MIT |
| [`generator-function@2.0.1`](https://www.npmjs.com/package/generator-function@2.0.1) | MIT |
| [`get-intrinsic@1.3.0`](https://www.npmjs.com/package/get-intrinsic@1.3.0) | MIT |
| [`get-proto@1.0.1`](https://www.npmjs.com/package/get-proto@1.0.1) | MIT |
| [`get-symbol-description@1.1.0`](https://www.npmjs.com/package/get-symbol-description@1.1.0) | MIT |
| [`get-tsconfig@4.14.3`](https://www.npmjs.com/package/get-tsconfig@4.14.3) | MIT |
| [`glob-parent@5.1.2`](https://www.npmjs.com/package/glob-parent@5.1.2) | ISC |
| [`glob-parent@6.0.2`](https://www.npmjs.com/package/glob-parent@6.0.2) | ISC |
| [`glob@7.2.3`](https://www.npmjs.com/package/glob@7.2.3) | ISC |
| [`globals@13.24.0`](https://www.npmjs.com/package/globals@13.24.0) | MIT |
| [`globalthis@1.0.4`](https://www.npmjs.com/package/globalthis@1.0.4) | MIT |
| [`gopd@1.2.0`](https://www.npmjs.com/package/gopd@1.2.0) | MIT |
| [`graphemer@1.4.0`](https://www.npmjs.com/package/graphemer@1.4.0) | MIT |
| [`has-bigints@1.1.0`](https://www.npmjs.com/package/has-bigints@1.1.0) | MIT |
| [`has-flag@4.0.0`](https://www.npmjs.com/package/has-flag@4.0.0) | MIT |
| [`has-property-descriptors@1.0.2`](https://www.npmjs.com/package/has-property-descriptors@1.0.2) | MIT |
| [`has-proto@1.2.0`](https://www.npmjs.com/package/has-proto@1.2.0) | MIT |
| [`has-symbols@1.1.0`](https://www.npmjs.com/package/has-symbols@1.1.0) | MIT |
| [`has-tostringtag@1.0.2`](https://www.npmjs.com/package/has-tostringtag@1.0.2) | MIT |
| [`hasown@2.0.4`](https://www.npmjs.com/package/hasown@2.0.4) | MIT |
| [`ignore@5.3.2`](https://www.npmjs.com/package/ignore@5.3.2) | MIT |
| [`imurmurhash@0.1.4`](https://www.npmjs.com/package/imurmurhash@0.1.4) | MIT |
| [`inflight@1.0.6`](https://www.npmjs.com/package/inflight@1.0.6) | ISC |
| [`inherits@2.0.4`](https://www.npmjs.com/package/inherits@2.0.4) | ISC |
| [`internal-slot@1.1.0`](https://www.npmjs.com/package/internal-slot@1.1.0) | MIT |
| [`is-array-buffer@3.0.5`](https://www.npmjs.com/package/is-array-buffer@3.0.5) | MIT |
| [`is-async-function@2.1.1`](https://www.npmjs.com/package/is-async-function@2.1.1) | MIT |
| [`is-bigint@1.1.0`](https://www.npmjs.com/package/is-bigint@1.1.0) | MIT |
| [`is-binary-path@2.1.0`](https://www.npmjs.com/package/is-binary-path@2.1.0) | MIT |
| [`is-boolean-object@1.2.2`](https://www.npmjs.com/package/is-boolean-object@1.2.2) | MIT |
| [`is-bun-module@2.0.0`](https://www.npmjs.com/package/is-bun-module@2.0.0) | MIT |
| [`is-callable@1.2.7`](https://www.npmjs.com/package/is-callable@1.2.7) | MIT |
| [`is-core-module@2.17.0`](https://www.npmjs.com/package/is-core-module@2.17.0) | MIT |
| [`is-data-view@1.0.2`](https://www.npmjs.com/package/is-data-view@1.0.2) | MIT |
| [`is-date-object@1.1.0`](https://www.npmjs.com/package/is-date-object@1.1.0) | MIT |
| [`is-document.all@1.0.0`](https://www.npmjs.com/package/is-document.all@1.0.0) | MIT |
| [`is-extglob@2.1.1`](https://www.npmjs.com/package/is-extglob@2.1.1) | MIT |
| [`is-finalizationregistry@1.1.1`](https://www.npmjs.com/package/is-finalizationregistry@1.1.1) | MIT |
| [`is-generator-function@1.1.2`](https://www.npmjs.com/package/is-generator-function@1.1.2) | MIT |
| [`is-glob@4.0.3`](https://www.npmjs.com/package/is-glob@4.0.3) | MIT |
| [`is-map@2.0.3`](https://www.npmjs.com/package/is-map@2.0.3) | MIT |
| [`is-negative-zero@2.0.3`](https://www.npmjs.com/package/is-negative-zero@2.0.3) | MIT |
| [`is-number-object@1.1.1`](https://www.npmjs.com/package/is-number-object@1.1.1) | MIT |
| [`is-number@7.0.0`](https://www.npmjs.com/package/is-number@7.0.0) | MIT |
| [`is-path-inside@3.0.3`](https://www.npmjs.com/package/is-path-inside@3.0.3) | MIT |
| [`is-regex@1.2.1`](https://www.npmjs.com/package/is-regex@1.2.1) | MIT |
| [`is-set@2.0.3`](https://www.npmjs.com/package/is-set@2.0.3) | MIT |
| [`is-shared-array-buffer@1.0.4`](https://www.npmjs.com/package/is-shared-array-buffer@1.0.4) | MIT |
| [`is-string@1.1.1`](https://www.npmjs.com/package/is-string@1.1.1) | MIT |
| [`is-symbol@1.1.1`](https://www.npmjs.com/package/is-symbol@1.1.1) | MIT |
| [`is-typed-array@1.1.15`](https://www.npmjs.com/package/is-typed-array@1.1.15) | MIT |
| [`is-weakmap@2.0.2`](https://www.npmjs.com/package/is-weakmap@2.0.2) | MIT |
| [`is-weakref@1.1.1`](https://www.npmjs.com/package/is-weakref@1.1.1) | MIT |
| [`is-weakset@2.0.4`](https://www.npmjs.com/package/is-weakset@2.0.4) | MIT |
| [`isarray@2.0.5`](https://www.npmjs.com/package/isarray@2.0.5) | MIT |
| [`isexe@2.0.0`](https://www.npmjs.com/package/isexe@2.0.0) | ISC |
| [`iterator.prototype@1.1.5`](https://www.npmjs.com/package/iterator.prototype@1.1.5) | MIT |
| [`jiti@1.21.7`](https://www.npmjs.com/package/jiti@1.21.7) | MIT |
| [`js-tokens@4.0.0`](https://www.npmjs.com/package/js-tokens@4.0.0) | MIT |
| [`js-yaml@4.3.2`](https://www.npmjs.com/package/js-yaml@4.3.2) | MIT |
| [`json-buffer@3.0.1`](https://www.npmjs.com/package/json-buffer@3.0.1) | MIT |
| [`json-schema-traverse@0.4.1`](https://www.npmjs.com/package/json-schema-traverse@0.4.1) | MIT |
| [`json-stable-stringify-without-jsonify@1.0.1`](https://www.npmjs.com/package/json-stable-stringify-without-jsonify@1.0.1) | MIT |
| [`json5@1.0.2`](https://www.npmjs.com/package/json5@1.0.2) | MIT |
| [`jsx-ast-utils@3.3.5`](https://www.npmjs.com/package/jsx-ast-utils@3.3.5) | MIT |
| [`keyv@4.5.4`](https://www.npmjs.com/package/keyv@4.5.4) | MIT |
| [`language-subtag-registry@0.3.23`](https://www.npmjs.com/package/language-subtag-registry@0.3.23) | CC0-1.0 |
| [`language-tags@1.0.9`](https://www.npmjs.com/package/language-tags@1.0.9) | MIT |
| [`levn@0.4.1`](https://www.npmjs.com/package/levn@0.4.1) | MIT |
| [`lilconfig@3.1.4`](https://www.npmjs.com/package/lilconfig@3.1.4) | MIT |
| [`lines-and-columns@1.2.4`](https://www.npmjs.com/package/lines-and-columns@1.2.4) | MIT |
| [`locate-path@6.0.0`](https://www.npmjs.com/package/locate-path@6.0.0) | MIT |
| [`lodash.merge@4.6.2`](https://www.npmjs.com/package/lodash.merge@4.6.2) | MIT |
| [`loose-envify@1.4.0`](https://www.npmjs.com/package/loose-envify@1.4.0) | MIT |
| [`math-intrinsics@1.1.0`](https://www.npmjs.com/package/math-intrinsics@1.1.0) | MIT |
| [`merge2@1.4.1`](https://www.npmjs.com/package/merge2@1.4.1) | MIT |
| [`micromatch@4.0.8`](https://www.npmjs.com/package/micromatch@4.0.8) | MIT |
| [`minimatch@3.1.5`](https://www.npmjs.com/package/minimatch@3.1.5) | ISC |
| [`minimist@1.2.8`](https://www.npmjs.com/package/minimist@1.2.8) | MIT |
| [`ms@2.1.3`](https://www.npmjs.com/package/ms@2.1.3) | MIT |
| [`mz@2.7.0`](https://www.npmjs.com/package/mz@2.7.0) | MIT |
| [`nanoid@3.3.20`](https://www.npmjs.com/package/nanoid@3.3.20) | MIT |
| [`napi-postinstall@0.3.7`](https://www.npmjs.com/package/napi-postinstall@0.3.7) | MIT |
| [`natural-compare@1.4.0`](https://www.npmjs.com/package/natural-compare@1.4.0) | MIT |
| [`next@15.5.28`](https://www.npmjs.com/package/next@15.5.28) | MIT |
| [`node-exports-info@1.6.2`](https://www.npmjs.com/package/node-exports-info@1.6.2) | MIT |
| [`node-releases@2.0.61`](https://www.npmjs.com/package/node-releases@2.0.61) | MIT |
| [`normalize-path@3.0.0`](https://www.npmjs.com/package/normalize-path@3.0.0) | MIT |
| [`object-assign@4.1.1`](https://www.npmjs.com/package/object-assign@4.1.1) | MIT |
| [`object-hash@3.0.0`](https://www.npmjs.com/package/object-hash@3.0.0) | MIT |
| [`object-inspect@1.13.4`](https://www.npmjs.com/package/object-inspect@1.13.4) | MIT |
| [`object-keys@1.1.1`](https://www.npmjs.com/package/object-keys@1.1.1) | MIT |
| [`object.assign@4.1.7`](https://www.npmjs.com/package/object.assign@4.1.7) | MIT |
| [`object.entries@1.1.9`](https://www.npmjs.com/package/object.entries@1.1.9) | MIT |
| [`object.fromentries@2.0.8`](https://www.npmjs.com/package/object.fromentries@2.0.8) | MIT |
| [`object.groupby@1.0.3`](https://www.npmjs.com/package/object.groupby@1.0.3) | MIT |
| [`object.values@1.2.1`](https://www.npmjs.com/package/object.values@1.2.1) | MIT |
| [`once@1.4.0`](https://www.npmjs.com/package/once@1.4.0) | ISC |
| [`optionator@0.9.4`](https://www.npmjs.com/package/optionator@0.9.4) | MIT |
| [`own-keys@1.0.2`](https://www.npmjs.com/package/own-keys@1.0.2) | MIT |
| [`p-limit@3.1.0`](https://www.npmjs.com/package/p-limit@3.1.0) | MIT |
| [`p-locate@5.0.0`](https://www.npmjs.com/package/p-locate@5.0.0) | MIT |
| [`path-exists@4.0.0`](https://www.npmjs.com/package/path-exists@4.0.0) | MIT |
| [`path-is-absolute@1.0.1`](https://www.npmjs.com/package/path-is-absolute@1.0.1) | MIT |
| [`path-key@3.1.1`](https://www.npmjs.com/package/path-key@3.1.1) | MIT |
| [`path-parse@1.0.7`](https://www.npmjs.com/package/path-parse@1.0.7) | MIT |
| [`picocolors@1.1.1`](https://www.npmjs.com/package/picocolors@1.1.1) | ISC |
| [`picomatch@2.3.2`](https://www.npmjs.com/package/picomatch@2.3.2) | MIT |
| [`picomatch@4.0.7`](https://www.npmjs.com/package/picomatch@4.0.7) | MIT |
| [`pirates@4.0.7`](https://www.npmjs.com/package/pirates@4.0.7) | MIT |
| [`possible-typed-array-names@1.1.0`](https://www.npmjs.com/package/possible-typed-array-names@1.1.0) | MIT |
| [`postcss-import@15.1.0`](https://www.npmjs.com/package/postcss-import@15.1.0) | MIT |
| [`postcss-js@4.1.0`](https://www.npmjs.com/package/postcss-js@4.1.0) | MIT |
| [`postcss-load-config@6.0.1`](https://www.npmjs.com/package/postcss-load-config@6.0.1) | MIT |
| [`postcss-nested@6.2.0`](https://www.npmjs.com/package/postcss-nested@6.2.0) | MIT |
| [`postcss-selector-parser@6.1.5`](https://www.npmjs.com/package/postcss-selector-parser@6.1.5) | MIT |
| [`postcss-value-parser@4.2.0`](https://www.npmjs.com/package/postcss-value-parser@4.2.0) | MIT |
| [`postcss@8.4.31`](https://www.npmjs.com/package/postcss@8.4.31) | MIT |
| [`postcss@8.5.32`](https://www.npmjs.com/package/postcss@8.5.32) | MIT |
| [`prelude-ls@1.2.1`](https://www.npmjs.com/package/prelude-ls@1.2.1) | MIT |
| [`prop-types@15.8.1`](https://www.npmjs.com/package/prop-types@15.8.1) | MIT |
| [`punycode@2.3.1`](https://www.npmjs.com/package/punycode@2.3.1) | MIT |
| [`react-dom@19.3.1`](https://www.npmjs.com/package/react-dom@19.3.1) | MIT |
| [`react-is@16.13.1`](https://www.npmjs.com/package/react-is@16.13.1) | MIT |
| [`react@19.3.1`](https://www.npmjs.com/package/react@19.3.1) | MIT |
| [`read-cache@1.0.2`](https://www.npmjs.com/package/read-cache@1.0.2) | MIT |
| [`readdirp@3.6.0`](https://www.npmjs.com/package/readdirp@3.6.0) | MIT |
| [`reflect.getprototypeof@1.0.10`](https://www.npmjs.com/package/reflect.getprototypeof@1.0.10) | MIT |
| [`regexp.prototype.flags@1.5.4`](https://www.npmjs.com/package/regexp.prototype.flags@1.5.4) | MIT |
| [`resolve-pkg-maps@1.0.0`](https://www.npmjs.com/package/resolve-pkg-maps@1.0.0) | MIT |
| [`resolve@1.22.13`](https://www.npmjs.com/package/resolve@1.22.13) | MIT |
| [`resolve@2.0.0-next.7`](https://www.npmjs.com/package/resolve@2.0.0-next.7) | MIT |
| [`rimraf@3.0.2`](https://www.npmjs.com/package/rimraf@3.0.2) | ISC |
| [`safe-array-concat@1.1.4`](https://www.npmjs.com/package/safe-array-concat@1.1.4) | MIT |
| [`safe-push-apply@1.0.0`](https://www.npmjs.com/package/safe-push-apply@1.0.0) | MIT |
| [`safe-regex-test@1.1.0`](https://www.npmjs.com/package/safe-regex-test@1.1.0) | MIT |
| [`scheduler@0.28.0`](https://www.npmjs.com/package/scheduler@0.28.0) | MIT |
| [`semver@6.3.1`](https://www.npmjs.com/package/semver@6.3.1) | ISC |
| [`semver@7.8.5`](https://www.npmjs.com/package/semver@7.8.5) | ISC |
| [`set-function-length@1.2.2`](https://www.npmjs.com/package/set-function-length@1.2.2) | MIT |
| [`set-function-name@2.0.2`](https://www.npmjs.com/package/set-function-name@2.0.2) | MIT |
| [`set-proto@1.0.0`](https://www.npmjs.com/package/set-proto@1.0.0) | MIT |
| [`sharp@0.35.5`](https://www.npmjs.com/package/sharp@0.35.5) | Apache-2.0 |
| [`shebang-command@2.0.0`](https://www.npmjs.com/package/shebang-command@2.0.0) | MIT |
| [`shebang-regex@3.0.0`](https://www.npmjs.com/package/shebang-regex@3.0.0) | MIT |
| [`side-channel-list@1.0.1`](https://www.npmjs.com/package/side-channel-list@1.0.1) | MIT |
| [`side-channel-map@1.0.1`](https://www.npmjs.com/package/side-channel-map@1.0.1) | MIT |
| [`side-channel-weakmap@1.0.2`](https://www.npmjs.com/package/side-channel-weakmap@1.0.2) | MIT |
| [`side-channel@1.1.1`](https://www.npmjs.com/package/side-channel@1.1.1) | MIT |
| [`source-map-js@1.2.2`](https://www.npmjs.com/package/source-map-js@1.2.2) | BSD-3-Clause |
| [`stable-hash@0.0.5`](https://www.npmjs.com/package/stable-hash@0.0.5) | MIT |
| [`stop-iteration-iterator@1.1.0`](https://www.npmjs.com/package/stop-iteration-iterator@1.1.0) | MIT |
| [`string.prototype.includes@2.0.1`](https://www.npmjs.com/package/string.prototype.includes@2.0.1) | MIT |
| [`string.prototype.matchall@4.1.0`](https://www.npmjs.com/package/string.prototype.matchall@4.1.0) | MIT |
| [`string.prototype.repeat@1.0.0`](https://www.npmjs.com/package/string.prototype.repeat@1.0.0) | MIT |
| [`string.prototype.trim@1.2.11`](https://www.npmjs.com/package/string.prototype.trim@1.2.11) | MIT |
| [`string.prototype.trimend@1.0.10`](https://www.npmjs.com/package/string.prototype.trimend@1.0.10) | MIT |
| [`string.prototype.trimstart@1.0.8`](https://www.npmjs.com/package/string.prototype.trimstart@1.0.8) | MIT |
| [`strip-ansi@6.0.1`](https://www.npmjs.com/package/strip-ansi@6.0.1) | MIT |
| [`strip-bom@3.0.0`](https://www.npmjs.com/package/strip-bom@3.0.0) | MIT |
| [`styled-jsx@5.1.6`](https://www.npmjs.com/package/styled-jsx@5.1.6) | MIT |
| [`sucrase@3.35.1`](https://www.npmjs.com/package/sucrase@3.35.1) | MIT |
| [`supports-color@7.2.0`](https://www.npmjs.com/package/supports-color@7.2.0) | MIT |
| [`supports-preserve-symlinks-flag@1.0.0`](https://www.npmjs.com/package/supports-preserve-symlinks-flag@1.0.0) | MIT |
| [`tailwindcss@3.4.19`](https://www.npmjs.com/package/tailwindcss@3.4.19) | MIT |
| [`text-table@0.2.0`](https://www.npmjs.com/package/text-table@0.2.0) | MIT |
| [`thenify-all@1.6.0`](https://www.npmjs.com/package/thenify-all@1.6.0) | MIT |
| [`thenify@3.3.1`](https://www.npmjs.com/package/thenify@3.3.1) | MIT |
| [`tinyglobby@0.2.17`](https://www.npmjs.com/package/tinyglobby@0.2.17) | MIT |
| [`to-regex-range@5.0.1`](https://www.npmjs.com/package/to-regex-range@5.0.1) | MIT |
| [`ts-interface-checker@0.1.13`](https://www.npmjs.com/package/ts-interface-checker@0.1.13) | Apache-2.0 |
| [`tsconfig-paths@3.15.0`](https://www.npmjs.com/package/tsconfig-paths@3.15.0) | MIT |
| [`type-check@0.4.0`](https://www.npmjs.com/package/type-check@0.4.0) | MIT |
| [`type-fest@0.20.2`](https://www.npmjs.com/package/type-fest@0.20.2) | (MIT OR CC0-1.0) |
| [`typed-array-buffer@1.0.3`](https://www.npmjs.com/package/typed-array-buffer@1.0.3) | MIT |
| [`typed-array-byte-length@1.0.3`](https://www.npmjs.com/package/typed-array-byte-length@1.0.3) | MIT |
| [`typed-array-byte-offset@1.0.5`](https://www.npmjs.com/package/typed-array-byte-offset@1.0.5) | MIT |
| [`typed-array-length@1.0.8`](https://www.npmjs.com/package/typed-array-length@1.0.8) | MIT |
| [`typescript@5.9.3`](https://www.npmjs.com/package/typescript@5.9.3) | Apache-2.0 |
| [`unbox-primitive@1.1.0`](https://www.npmjs.com/package/unbox-primitive@1.1.0) | MIT |
| [`unrs-resolver@1.12.2`](https://www.npmjs.com/package/unrs-resolver@1.12.2) | MIT |
| [`update-browserslist-db@1.3.4`](https://www.npmjs.com/package/update-browserslist-db@1.3.4) | MIT |
| [`uri-js@4.4.1`](https://www.npmjs.com/package/uri-js@4.4.1) | BSD-2-Clause |
| [`util-deprecate@1.0.2`](https://www.npmjs.com/package/util-deprecate@1.0.2) | MIT |
| [`which-boxed-primitive@1.1.1`](https://www.npmjs.com/package/which-boxed-primitive@1.1.1) | MIT |
| [`which-builtin-type@1.2.1`](https://www.npmjs.com/package/which-builtin-type@1.2.1) | MIT |
| [`which-collection@1.0.2`](https://www.npmjs.com/package/which-collection@1.0.2) | MIT |
| [`which-typed-array@1.1.24`](https://www.npmjs.com/package/which-typed-array@1.1.24) | MIT |
| [`which@2.0.2`](https://www.npmjs.com/package/which@2.0.2) | ISC |
| [`word-wrap@1.2.5`](https://www.npmjs.com/package/word-wrap@1.2.5) | MIT |
| [`wrappy@1.0.2`](https://www.npmjs.com/package/wrappy@1.0.2) | ISC |
| [`yaml@2.9.1`](https://www.npmjs.com/package/yaml@2.9.1) | ISC |
| [`yocto-queue@0.1.0`](https://www.npmjs.com/package/yocto-queue@0.1.0) | MIT |

## Standard MIT permission and warranty notice


Copyright (c) the respective upstream copyright holders, as identified in each distribution's license file.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Standard Apache-2.0 notice

Copyright (c) the respective upstream copyright holders, as identified in each distribution's license file.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use the relevant distribution except in compliance with the License. You may obtain a copy of the License at <https://www.apache.org/licenses/LICENSE-2.0>. Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

## Programs bundled in the desktop installer

The desktop installer (`apps/desktop`, built by `scripts/package/build_runtime.py`) ships unmodified upstream programs next to the application. Each keeps its own license, which applies to that program only:

- PostgreSQL 16 (PostgreSQL License), from the zonky.io embedded-postgres-binaries distribution.
- Redis 7.2.4 (BSD 3-Clause), built from the upstream source release. Later Redis versions use different licenses and are not bundled.
- Qdrant 1.12.6 (Apache-2.0), upstream release binary.
- CPython 3.12 (Python Software Foundation License), from python-build-standalone, with the Python packages listed in `apps/api/requirements.txt` under their own licenses.
- Electron (MIT) and the Node.js runtime it embeds.
- Node.js 22 LTS and npm (MIT, with the licenses of npm's own dependencies inside `node/lib/node_modules/npm`), upstream release binary, for commands that agents run. Separate from the Node.js inside Electron.
- Git 2.56.0 (GNU GPL version 2), built from the unmodified upstream source with `scripts/package/build_runtime.py`, for commands that agents run.
- FFmpeg 9.0.2 (GNU LGPL version 2.1 or later), built from the unmodified upstream source with `--disable-gpl --disable-nonfree` and without any third-party codec library, for commands that agents run. H.264 and AAC use the operating system's VideoToolbox and AudioToolbox.

### Source code of the GPL and LGPL programs

Git and FFmpeg are separate programs that the application starts as commands; they are not linked into it and the application's own code is not under their licenses. Their complete corresponding source is the upstream release below, unmodified, and the exact build commands are in `scripts/package/build_runtime.py` and `scripts/package/runtime.json` (which pins the source archive by SHA-256). Anyone who received the installer may obtain that source from the addresses below, and from the publisher of this installer on request, for at least three years after the release:

- Git 2.56.0: https://mirrors.edge.kernel.org/pub/software/scm/git/git-2.56.0.tar.xz
- FFmpeg 9.0.2: https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz

The licenses are in the `COPYING` files of those archives. FFmpeg is relinkable: its libraries are linked statically into `ffmpeg` and `ffprobe`; rebuilding them from the same source with the same commands produces equivalent programs, and the files in the app's `runtime/tools/bin` folder can be replaced by ones built that way. The license texts of Node.js, Git and FFmpeg are shipped beside each program (`LICENSE*` files in `runtime/node`, `runtime/git`, `runtime/tools`).

A Chromium-based browser is not shipped. The `headless-browser` command uses Google Chrome, Chromium, Microsoft Edge or Brave when one is installed in `/Applications`, and says so when none is.
