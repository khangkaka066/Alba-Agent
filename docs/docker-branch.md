# The `docker` branch

`main` is the desktop app (macOS, Apple Silicon, no Docker). This branch is `main` **plus** everything needed to run NexusAgent in Docker:
the three `docker-compose` files, `infra/production` (Caddy HTTPS proxy, daily Postgres backups), the three Dockerfiles, `apps/api/start.sh`,
`.dockerignore`, `scripts/quickstart.sh`, `scripts/smoke_test.py`, `scripts/run-local.sh`, `scripts/load_env.py` and the image workflow
(`.github/workflows/docker-images.yml`). It is the base for a server / web deployment and for a Windows build later.

## Rules that keep the two branches mergeable
1. **Shared code is changed on `main` only** (`apps/api`, `apps/web`, `packages/*`, `scripts/package`). Never edit `apps/desktop` here.
2. **Docker-only files are changed here only.** They do not exist on `main`.
3. Bring `main` in regularly: `git switch docker && git merge origin/main`.
4. The top-level documents (`README.md`, `README.vi.md`, `AGENTS.md`, `CONTRIBUTING.md`) are this branch's own; `.gitattributes` keeps them
   when `main` is merged, provided you run **once per clone**: `git config merge.ours.driver true`.
5. `.github/workflows/ci.yml` is identical on both branches (it runs on pushes to `main` and `docker`); only `docker-images.yml` is specific to this branch.

## Images
`docker-images.yml` builds the api, web and sandbox images for `linux/amd64` and `linux/arm64` on pull requests that touch them. It pushes to
`ghcr.io` only on a tag `docker-v*` or when started by hand with *publish* ticked. The registry name is lower-cased: the earlier workflow
used the repository name as it is (`Nexus-Agent`), which the registry rejects.

## Before using it for a public service
See "Before exposing it to the Internet" in `tasks/todo.md` (Phase 43): the compose files mount `/var/run/docker.sock` into the api and worker
containers, local mode must be off, and the stack has not been run on a server from this branch yet.
