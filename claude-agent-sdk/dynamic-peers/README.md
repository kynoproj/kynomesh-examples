# Claude Agent SDK: a supervisor that discovers its workers

A travel-planning supervisor built with the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python) whose
worker agents are **not named in its code**. At startup it asks Kynomesh who its
peers are, reads each peer's `AgentCard`, and generates one tool per worker from
that card. Add or remove a worker in the `AgentSet` and the supervisor picks it
up without a code change or a new image. The workers are Claude agents too.

```mermaid
flowchart LR
    client([client]) -- A2A --> planner
    subgraph AgentSet["AgentSet: claude-travel (pattern: Supervisor)"]
        planner -- A2A --> flights
        planner -- A2A --> hotels
        planner -. "A2A (added/removed in the demo)" .-> weather
    end
```

The Claude Agent SDK does not speak A2A. Kynomesh's Python SDK runs each agent's
A2A server and makes the calls between agents; Claude only sees ordinary tools:

```mermaid
flowchart LR
    server["kynomesh.server<br/>(A2A server)"] --> exec["ClaudeExecutor"]
    exec -- "query(prompt)" --> cli["Claude Code CLI<br/>(bundled, subprocess)"]
    cli -- "MCP" --> tool["ask_flights, ask_hotels, ...<br/>(in-process SDK tools)"]
    tool --> peer["kynomesh.client.peer_client<br/>(A2A client)"] -- A2A --> worker["worker pod"]
```

| File                                        | Role                                                                                                                                         |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/claude_travel/discovery.py`            | `client.peers()` + `client.resolve_agent_card()` → `WorkerInfo` per peer. No names.                                                          |
| `src/claude_travel/supervisor.py`           | Builds one `ask_<peer>` SDK tool per worker, and the prompt's worker list, from those cards.                                                 |
| `src/claude_travel/agent.py`                | `locked_down_options` and `run_agent`: the Claude plumbing shared by every role.                                                             |
| `src/claude_travel/workers.py` / `tools.py` | The roles this image _can_ run (`flights`, `hotels`, `weather`) and their stub tools, plus the extra skills they can gain. No external APIs. |
| `src/claude_travel/main.py`                 | `--role planner` or a worker role. The manifest decides which workers exist.                                                                 |
| `manifests/agentset.yaml`                   | Planner + `flights` + `hotels`, with `driftReload` on.                                                                                       |
| `manifests/agentset-with-weather.yaml`      | The same plus `weather`.                                                                                                                     |

## How the pieces fit

- **Peers come from the topology.** With `pattern: Supervisor`, Kynomesh gives
  the entry agent a peer list of every other agent. The SDK reads it once per
  process, so the planner's worker set is fixed until its pod restarts.
- **Drift reload covers changed cards.** If a worker's `AgentCard` changes (for
  example it gains a skill), `driftReload` restarts the pods holding the stale
  card, and the planner rebuilds its tools from the new one. This is not instant
  (see step 4). See
  [Drift Reload](https://github.com/kynoproj/kynomesh/blob/main/docs/user-guide/reference/drift-reload.md).
- **Discovery warms each peer with `peer_client`.** That records the peer's card
  hash, which `driftReload` compares against. A peer this process never built a
  client for is "unknown" to drift detection, so without the warm-up a card
  change on a not-yet-called worker would go unnoticed.
- **Workers may not be up yet.** Every agent in the `AgentSet` starts at the
  same time, so a worker is often still starting when the planner looks for it.
  Discovery retries each worker for about a minute. If one is still unreachable,
  the planner exits with an error and Kubernetes restarts the pod, which tries
  again. The planner never serves with a worker missing.
- **A failing worker doesn't crash a run.** The planner's tool returns the error
  to the model as a tool error, so it can answer around it.
- **Every role is locked down** (see `agent.py`): `tools=[]` removes all
  built-in tools (Bash, Read, Write, ...), and only that role's own tools are
  allowed, with `permission_mode="dontAsk"`, no filesystem settings, and a turn
  limit.
- Each request spawns the Claude Code CLI bundled in the `claude-agent-sdk`
  wheel, so expect a few seconds of startup per request and a large image.

## Prerequisites

- Python 3.10+ and [uv](https://docs.astral.sh/uv/)
- An `ANTHROPIC_API_KEY`. Agents refuse to start without one.
- [`a2acli`](https://github.com/kynoproj/a2acli)
- Docker, `kubectl`, and a local Kubernetes cluster with
  [Kynomesh installed](https://github.com/kynoproj/kynomesh/blob/main/docs/quick-start.md)

## 1. Run the tests

```shell
uv run pytest    # no API calls
```

The planner needs the Kynomesh topology, which only exists in-cluster. A worker
runs locally:
`ANTHROPIC_API_KEY=... uv run python -m claude_travel.main --role flights`.

## 2. Deploy

```shell
make build                     # builds claude-travel:latest
# k3d:   k3d image import claude-travel:latest -c <cluster>
# kind:  kind load docker-image claude-travel:latest
kubectl create secret generic anthropic-api-key --from-literal=ANTHROPIC_API_KEY=...
make deploy
kubectl get agentset,agentdeploy
kubectl port-forward svc/claude-travel-ingress 8490
```

Ask it something. The planner logs the workers it found:

```shell
kubectl logs -l app.kubernetes.io/name=claude-travel-planner -c agent | grep discovered
a2acli -k -u https://localhost:8490 --override-host=localhost:8490 \
  send 'Plan a weekend in Tokyo: flights from SFO and a hotel'
a2acli -k -u https://localhost:8490 --override-host=localhost:8490 \
  send 'What is the weather in Tokyo this weekend?'      # no worker for this yet
```

## 3. Add a worker: no code change

```shell
kubectl apply -f manifests/agentset-with-weather.yaml
kubectl get pods -w                                      # planner restarts
kubectl logs -l app.kubernetes.io/name=claude-travel-planner -c agent | grep discovered
a2acli ... send 'What is the weather in Tokyo this weekend?'   # now answered
```

Remove it again with `kubectl apply -f manifests/agentset.yaml`. The planner
goes back to two workers.

## 4. Change a worker's card: drift reload

The workers read an optional `EXTRA_SKILLS` env var that turns on extra skills.
`price-comparison` teaches a worker to compare the options it finds and name the
cheapest one. It appears on the worker's card and changes how the worker
answers, like a new release of an agent that gained a skill.

```shell
kubectl patch agentset claude-travel --type=json -p='[
  {"op":"add","path":"/spec/agents/2/container/env/-",
   "value":{"name":"EXTRA_SKILLS","value":"price-comparison"}}]'
```

`/spec/agents/2` is `hotels`. Once its pods roll, Kynomesh detects that the
`hotels` card changed and restarts the planner, whose `ask_hotels` tool now
lists the new skill.

**Give it a few minutes.** The planner does not restart as soon as the `hotels`
pods are back, and that is expected, not a failure. Kynomesh waits for the
changed card to stay stable, and for the rollout to finish, before it restarts
the planner.

```shell
kubectl get pods -w                    # the planner restarts after a few minutes
```

Check the planner's pod age to confirm the restart. For the mechanism, see the
[AgentCard drift detection spec](https://kyno.sh/stable/development/specifications/agentcard-drift-reload/).

Then ask for a comparison. The planner's `ask_hotels` tool now advertises the
skill, and the `hotels` worker acts on it:

```shell
a2acli -k -u https://localhost:8490 --override-host=localhost:8490 \
  send 'What is the cheapest hotel in Tokyo, and how much does it save?'
```

Clean up with `make delete`.

Behind a TLS-intercepting proxy the image build fails certificate checks. Pass
the proxy CA: `make build CA_CERT=/path/to/ca.pem`.
