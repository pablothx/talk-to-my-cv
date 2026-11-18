# The API container reaches native Ollama through a socat bridge on Linux

Step 8 adds the first app container (ADR-0001 deferred it to this step). It runs only the API: ingest, chat, eval and tests stay on the host. It reaches the stores by their compose service names and Ollama, which runs natively, through `host.docker.internal` (`extra_hosts: host-gateway`).

On Docker Desktop (macOS, Windows), `host.docker.internal` reaches services on the host's `127.0.0.1`. On Linux it resolves to the `docker0` address (172.17.0.1), and native Ollama listens only on `127.0.0.1`, so the connection is refused. We considered three fixes:

- **`OLLAMA_HOST=0.0.0.0` in Ollama's systemd unit** (Ollama's own FAQ). It needs sudo and a change outside the repo, and Ollama, which has no authentication, would then be reachable from the local network unless a firewall blocks it.
- **`network_mode: host` for the API.** On Linux it changes every address (stores on `localhost`, published ports), and it behaves differently on Docker Desktop.
- **A socat container (`ollama-bridge`)** with `network_mode: host` that listens on `docker0:11434` and forwards to `127.0.0.1:11434`. It needs no sudo, doesn't change the API's configuration, and only containers can reach it.

We chose the bridge. `make api-up` adds it on Linux only, behind the `bridge` compose profile.

## Consequences

- If Docker uses a different `docker0` address, `DOCKER_HOST_IP` overrides it.
- A learner who already set `OLLAMA_HOST=0.0.0.0` gets an "address in use" error from the bridge, and doesn't need it: `docker compose --profile api up -d api`.
- The image contains only `src/` and `config/`: `.dockerignore` is an allowlist, so `.env` and `kb/` (real personal data) never enter it.
