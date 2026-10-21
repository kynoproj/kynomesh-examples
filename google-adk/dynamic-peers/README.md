# Google ADK: a supervisor that discovers its workers

A travel-planning supervisor built with the
[Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) whose
worker agents are **not named in its code**. At startup it asks Kynomesh who its
peers are, reads each peer's `AgentCard`, and generates one tool per worker from
that card. Add or remove a worker in the `AgentSet` and the supervisor picks it
up without a code change or a new image. The workers are ADK agents too.

```mermaid
flowchart LR
    client([client]) -- A2A --> planner
    subgraph AgentSet["AgentSet: adk-travel (pattern: Supervisor)"]
        planner -- A2A --> flights
        planner -- A2A --> hotels
        planner -. "A2A (added/removed in the demo)" .-> weather
    end
```

ADK has its own A2A support, but this example does not use it. Kynomesh's Python
SDK runs each agent's A2A server and makes the calls between agents; ADK only
sees ordinary function tools:

```mermaid
flowchart LR
    server["kynomesh.server<br/>(A2A server)"] --> exec["AdkExecutor"]
    exec -- "runner.run_async" --> agent["LlmAgent<br/>(Gemini)"]
    agent --> tool["ask_flights, ask_hotels, ...<br/>(generated function tools)"]
    tool --> peer["kynomesh.client.peer_client<br/>(A2A client)"] -- A2A --> worker["worker pod"]
```

| File                                     | Role                                                                                                    |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `src/adk_travel/discovery.py`            | `client.peers()` + `client.resolve_agent_card()` → `WorkerInfo` per peer. No names.                     |
| `src/adk_travel/supervisor.py`           | Builds one `ask_<peer>` tool function per worker, and the instruction's worker list, from those cards.  |
| `src/adk_travel/agent.py`                | `build_runner` and `run_agent`: the ADK plumbing shared by every role.                                  |
| `src/adk_travel/workers.py` / `tools.py` | The roles this image _can_ run (`flights`, `hotels`, `weather`) and their stub tools. No external APIs. |
| `src/adk_travel/main.py`                 | `--role planner` or a worker role. The manifest decides which workers exist.                            |
| `manifests/agentset.yaml`                | Planner + `flights` + `hotels`, with `driftReload` on.                                                  |
| `manifests/agentset-with-weather.yaml`   | The same plus `weather`.                                                                                |

## How the pieces fit

- **Peers come from the topology.** With `pattern: Supervisor`, Kynomesh gives
  the entry agent a peer list of every other agent. The SDK reads it once per
  process, so the planner's worker set is fixed until its pod restarts.
- **Generated tools are ordinary functions.** ADK takes a tool's name from
  `__name__`, its description from the docstring and its argument schema from
  the type hints, so `peer_tools` sets those from each worker's card.
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
- **A failing worker doesn't crash a run.** The planner's tool returns
  `{"status": "error", ...}` to the model, so it can answer around it.
- **Requests are independent.** Each one runs in a fresh in-memory ADK session.
- Agents run on Gemini through the Gemini API. Set `GOOGLE_MODEL` to pick a
  model (default `gemini-2.5-flash`).

## Prerequisites

- Python 3.10+ and [uv](https://docs.astral.sh/uv/)
- A `GOOGLE_API_KEY` from
  [Google AI Studio](https://aistudio.google.com/apikey). Agents refuse to start
  without one.
- [`a2acli`](https://github.com/kynoproj/a2acli)
- Docker, `kubectl`, and a local Kubernetes cluster with
  [Kynomesh installed](https://github.com/kynoproj/kynomesh/blob/main/docs/quick-start.md)

## 1. Run the tests

```shell
uv run pytest    # no API calls
```

The planner needs the Kynomesh topology, which only exists in-cluster. A worker
runs locally:
`GOOGLE_API_KEY=... uv run python -m adk_travel.main --role flights`.

## 2. Deploy

```shell
make build                     # builds adk-travel:latest
# k3d:   k3d image import adk-travel:latest -c <cluster>
# kind:  kind load docker-image adk-travel:latest
kubectl create secret generic google-api-key --from-literal=GOOGLE_API_KEY=...
make deploy
kubectl get agentset,agentdeploy
kubectl port-forward svc/adk-travel-ingress 8490
```

Ask it something. The planner logs the workers it found:

```shell
kubectl logs -l app.kubernetes.io/name=adk-travel-planner -c agent | grep discovered
a2acli -k -u https://localhost:8490 --override-host=localhost:8490 \
  send 'Plan a weekend in Tokyo: flights from SFO and a hotel'
a2acli -k -u https://localhost:8490 --override-host=localhost:8490 \
  send 'What is the weather in Tokyo this weekend?'      # no worker for this yet
```

## 3. Add a worker: no code change

```shell
kubectl apply -f manifests/agentset-with-weather.yaml
kubectl get pods -w                                      # planner restarts
kubectl logs -l app.kubernetes.io/name=adk-travel-planner -c agent | grep discovered
a2acli ... send 'What is the weather in Tokyo this weekend?'   # now answered
```

Remove it again with `kubectl apply -f manifests/agentset.yaml`. The planner
goes back to two workers.

## 4. Change a worker's card: drift reload

The workers read an optional `EXTRA_SKILLS` env var that adds skills to their
card. It stands in for shipping a new version of an agent that gained a skill.

```shell
kubectl patch agentset adk-travel --type=json -p='[
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

Clean up with `make delete`.

Behind a TLS-intercepting proxy the image build fails certificate checks. Pass
the proxy CA: `make build CA_CERT=/path/to/ca.pem`.
