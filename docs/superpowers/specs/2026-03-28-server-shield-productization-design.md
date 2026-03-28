# Server Shield Productization Design

## Goal

Productize the `server_shield` portion of the repository by turning the current one-off Pulumi entrypoint and ad-hoc text-file coordination into a single Python project with clear internal component boundaries, shared typed state/config libraries, operational guardrails, and a container runtime that safely executes all three server-side jobs on a schedule.

## Scope

This design covers only the server shield side.

Included:
- README cleanup for the server shield architecture section
- migration from text state files to JSON state files with Pydantic schemas
- shared config and state helper library used by all three server-side components
- relocation of Pulumi project files under a dedicated directory inside `server_shield`
- placeholder `chain_reader` and `chain_writer` components that currently act as hello-world jobs with proper bootstrap, config, and Sentry wiring
- removal of direct `.env` loading in application code
- shared environment parsing via `pydantic-settings`
- Sentry initialization for all three components
- a single Docker image that runs the three components once per minute with locking and a 20-minute timeout
- unit tests for shared code and Pulumi infrastructure composition

Excluded:
- client-side / validator-side work
- real chain reader business logic
- real chain writer business logic
- broader monorepo/package splitting beyond `server_shield`

## Current State

The current `server_shield` directory is a single Python project centered around `__main__.py`, which contains Pulumi infrastructure code and reads configuration directly from environment variables after calling `load_dotenv()`. Coordination between future components is described in the README as plain text-file exchange (`domains.txt`, `hosted_zone_domain.txt`, `nlb_ip.txt`), but only the Pulumi side currently exists in code. The directory root also mixes Pulumi project files, runtime code, lockfile data, and local state artifacts.

## Chosen Packaging Boundary

`server_shield` remains a single Python project for now.

Reasoning:
- matches the current scope of working only on the server shield
- keeps dependency management, imports, Docker packaging, and config simpler
- still allows clean internal package boundaries so the three components can evolve independently later
- avoids premature package fragmentation while two components remain placeholders

## Architecture

`server_shield` will become one Python project with four internal packages/directories of concern:

- `server_shield/shared`
  - owns shared configuration, state schemas, JSON file helpers, bootstrap behavior, and Sentry initialization
- `server_shield/pulumi_runner`
  - owns the Pulumi program entrypoint and any infrastructure-specific orchestration helpers
- `server_shield/chain_reader`
  - owns the current placeholder reader command
- `server_shield/chain_writer`
  - owns the current placeholder writer command
- `server_shield/pulumi_project`
  - owns `Pulumi.yaml`, stack configuration, and Pulumi program wiring in a dedicated directory separate from the runtime package root

The top-level runtime model remains “three independent scheduled jobs,” but they now share one typed library for state and configuration instead of using free-form files and duplicated environment lookups.

## File and Package Layout

Target structure:

```text
server_shield/
  pyproject.toml
  uv.lock
  Dockerfile
  docker/
    run_component.sh
    entrypoint.sh
  src/
    server_shield/
      shared/
        __init__.py
        config.py
        sentry.py
        state.py
        state_store.py
      pulumi_runner/
        __init__.py
        cli.py
        program.py
      chain_reader/
        __init__.py
        cli.py
      chain_writer/
        __init__.py
        cli.py
  pulumi_project/
    Pulumi.yaml
    Pulumi.<stack>.yaml
    __main__.py
  tests/
    shared/
    pulumi_runner/
    chain_reader/
    chain_writer/
```

Notes:
- `src/` layout is preferred so imports are explicit and testable.
- If a root `__main__.py` remains, it should only dispatch commands and should not contain infrastructure logic.
- The existing long Pulumi script should be split so resource construction becomes testable and easier to reason about.

## Shared State Model

All inter-component state files become JSON files with explicit Pydantic models. Files are always present after bootstrap, even before useful data exists.

This is a deliberate contract: components should decide whether to do work based on null/empty values, not based on whether a file exists.

### State File Invariants

- state files are created on bootstrap if absent
- each file always contains valid JSON matching its schema
- absence of upstream data is represented by `null` or an empty array, not by a missing file
- readers always receive typed models, never raw dictionaries
- writers persist atomically to avoid partial writes during scheduled execution

### Initial State Shapes

- `hosted_zone_domain.json`

```json
{ "domain": null }
```

- `nlb_ip.json`

```json
{ "ip": null }
```

- `desired_domains.json`

```json
{ "domains": [] }
```

- `blacklist.json`

```json
{ "domains": [] }
```

- `manifest.json`

```json
{ "manifest_url": null, "encrypted_addresses": [] }
```

The manifest schema is intentionally a placeholder but still explicit. It should be defined now so the contract is stable even before real chain reader logic exists.

### State Ownership

- `pulumi_runner`
  - reads `desired_domains.json`
  - writes `hosted_zone_domain.json`
  - writes `nlb_ip.json`
- `chain_reader`
  - reads `hosted_zone_domain.json`
  - reads `blacklist.json`
  - writes `desired_domains.json`
  - writes `manifest.json`
- `chain_writer`
  - reads `nlb_ip.json`
  - eventually writes on-chain axon information

### Shared State API

`server_shield/shared/state_store.py` exposes small, typed helpers rather than pushing raw file logic into each component. Expected helpers include functions equivalent to:

- `ensure_state_files()`
- `read_hosted_zone_domain()` / `write_hosted_zone_domain()`
- `read_nlb_ip()` / `write_nlb_ip()`
- `read_desired_domains()` / `write_desired_domains()`
- `read_blacklist()` / `write_blacklist()`
- `read_manifest()` / `write_manifest()`

Behavioral requirements:
- read helpers return typed Pydantic model instances
- bootstrap creates missing files with default null/empty values
- write helpers serialize consistently and atomically
- optional empty/default state is not treated as an error

## Component Behavior

### Pulumi Runner

The Pulumi runner keeps responsibility for provisioning and updating shield infrastructure, but its behavior becomes explicitly state-driven.

Rules:
- always perform the base infrastructure work needed for the shield
- always resolve and write the hosted zone domain
- always resolve and write the NLB public IP when infrastructure exposes one
- read `desired_domains.json` before creating WAF host allow rules
- if desired domains are empty, skip host-based WAF allow rules rather than failing
- continue to allow the manifest path routing behavior independent of desired domains

This means an initial run can provision the reusable infrastructure while deferring host-specific filtering until later scheduled runs.

### Chain Reader

For now, the chain reader remains a hello-world component, but it should still adopt the production structure.

Rules:
- load shared config
- initialize Sentry
- ensure state files exist
- read upstream state through typed helpers
- log a hello-world style message and exit cleanly
- keep placeholders for future state writes without implementing real chain integration yet

### Chain Writer

For now, the chain writer also remains a hello-world component, but it must obey dependency-gated no-op behavior.

Rules:
- load shared config
- initialize Sentry
- ensure state files exist
- read `nlb_ip.json`
- if `nlb_ip.ip` is `null`, exit quickly and successfully without doing further work
- if `nlb_ip.ip` is present, log a hello-world style message representing the future write path and exit cleanly

The desired behavior is a fast clean skip, not a warning-level failure.

## Configuration Model

Direct `.env` loading is removed from application code. Configuration comes only from process environment variables.

A single shared config module in `server_shield/shared/config.py` uses `pydantic-settings` to parse and validate all environment variables. Components access configuration through a single singleton-style accessor such as `get_config()`.

### Config Structure

The config object should be split into typed sections:

- common app settings
  - `env`
  - `log_level`
  - `sentry_dsn`
  - `state_dir`
- Pulumi runner settings
  - AWS region
  - hosted zone id
  - miner instance id
  - miner port
  - optional Pulumi stack/backend settings if needed by the chosen execution flow
- chain reader settings
  - subtensor address
  - netuid
- chain writer settings
  - wallet identifier settings
  - subtensor address
  - netuid
  - miner port

Design requirements:
- all three components import from the same config module
- environment parsing/validation happens once
- component code receives typed submodels, not ad-hoc `os.environ` lookups
- missing optional settings remain optional where appropriate, especially `sentry_dsn`

## Sentry

All three components initialize Sentry through a shared helper in `server_shield/shared/sentry.py`.

Requirements:
- shared `init_sentry(component_name)` function
- no-op when `SENTRY_DSN` is unset
- tag events with component name and environment
- safe to call on every scheduled run
- uncaught exceptions from any component must be reported to Sentry when `SENTRY_DSN` is set
- non-zero component exits must also result in a Sentry event when `SENTRY_DSN` is set

This keeps error reporting consistent without duplicating setup code.

## Pulumi Project Relocation

Pulumi project metadata should move under a dedicated `server_shield/pulumi_project/` directory.

Goals:
- leave room at the `server_shield` root for shared library code and non-Pulumi runtime pieces
- isolate Pulumi stack files from general package code
- make it clear which files belong to infrastructure execution versus application/runtime logic

The runtime command for the Pulumi component should explicitly point Pulumi at this project directory.

## State File Git Ignore Policy

Local state artifacts must not be committed.

The repository `.gitignore` should include the JSON state files or their containing state directory, replacing the current implicit/accidental handling of files like `domains.txt`.

At minimum, ignore the runtime state location used by:
- `hosted_zone_domain.json`
- `nlb_ip.json`
- `desired_domains.json`
- `blacklist.json`
- `manifest.json`

The ignore rule should be precise enough to avoid accidentally ignoring source-controlled examples or fixtures.

## Runtime Scheduling and Concurrency Model

The container runs all three components continuously.

### Scheduling Contract

Each component is attempted once per minute, with two operational guardrails:
- at most one instance of a given component may run at a time
- each run has a hard timeout of 20 minutes

Semantics:
- if a component is still running when the next minute arrives, the new attempt is skipped
- if a component exceeds 20 minutes, it is terminated and the lock is released
- this policy applies independently per component

### Implementation Approach

Use a lightweight shell-based supervisor instead of cron.

Per component loop:

```sh
while true; do
  run_component_with_lock_and_timeout <component>
  sleep 60
done
```

Behavior of `run_component_with_lock_and_timeout`:
- acquire a non-blocking per-component lock
- if lock acquisition fails, log that the run was skipped and return success
- if lock acquisition succeeds, execute the component command under a 20-minute timeout
- always release the lock on exit
- write logs to stdout/stderr so output from all three component loops is visible via `docker logs`
- prefix or otherwise identify log lines by component so interleaved output remains attributable
- when a component exits non-zero and `SENTRY_DSN` is set, emit a Sentry event before returning control to the loop

Rationale:
- easier to run correctly in containers than system cron
- easier to reason about logging and process lifecycle
- sufficient for the required “attempt every minute, never overlap, max 20 minutes” semantics

## Docker Image

One Docker image should contain:
- the Python project
- the Pulumi CLI/runtime needed for `pulumi up`
- the supervisor scripts that loop over the three components

Expected responsibilities:
- install Python dependencies
- install Pulumi CLI
- expose runtime environment variables to all components
- start the scheduler/supervisor entrypoint on container startup
- keep all component logs on the container's standard output/error streams so `docker logs` shows Pulumi runner, chain reader, and chain writer activity in one place

The image should run all three components, not require separate images per component.

## README Changes

The README section `### Miner part internal architecture` should be rewritten to reflect the new design.

The updated documentation should explain:
- the three server-side components and their current status
- the shared typed JSON state model
- the initial null/empty bootstrap behavior
- which component reads/writes which state files
- the fact that chain reader/writer are placeholders for now
- the scheduler behavior: once per minute, non-overlapping, 20-minute timeout
- the fact that config is expected via environment variables rather than application-side `.env` loading

References to text files such as `domains.txt` should be removed or replaced with the new JSON equivalents.

## Testing Strategy

### Shared Library Tests

Add unit tests for:
- config parsing via `pydantic-settings`
- state bootstrap creating valid JSON files with null/empty defaults
- state read/write helpers returning typed models
- atomic write behavior where feasible to test directly
- component skip/no-op conditions that depend on null state

### Pulumi Unit Tests

Add Pulumi unit tests for infrastructure composition.

Minimum required assertions:
- when desired domains are empty, host-based WAF allow rules are omitted
- the base infrastructure still includes the expected hosted zone/NLB/manifest path related resources in the empty-domains case
- resource construction remains valid when desired domains are populated

The goal is not end-to-end cloud deployment testing; it is deterministic unit coverage over the Pulumi program’s conditional composition.

### Component Tests

Add tests covering:
- chain reader bootstrap path and clean hello-world exit
- chain writer fast clean exit when `nlb_ip.ip` is `null`
- chain writer non-skip path when `nlb_ip.ip` has a value
- lock/timeout runner behavior if practical at the unit or shell level
- Sentry capture behavior for uncaught exceptions and non-zero exits when `SENTRY_DSN` is configured
- logging behavior sufficient to show component-attributed output on stdout/stderr

## Migration Notes

The implementation should preserve the spirit of the current infrastructure while improving maintainability.

Important migration constraints:
- do not rely on `.env` loading in code
- do not keep text state files as the primary runtime contract
- do not overbuild real chain integration yet
- keep the new component boundaries explicit even though two components are placeholders

## Risks and Mitigations

### Risk: state format churn

If the JSON schemas are vague now, future components may break compatibility.

Mitigation:
- define explicit Pydantic models now
- keep placeholder schemas valid and versionable
- route all access through shared helpers rather than raw JSON usage

### Risk: Pulumi refactor changes infrastructure behavior

Moving the Pulumi code into a testable module can accidentally alter resources.

Mitigation:
- add Pulumi unit tests before or during the refactor
- preserve existing functional behavior except for the intentional change around empty desired domains

### Risk: scheduler edge cases in container runtime

Long-running or hung jobs can accumulate or deadlock if locks and timeouts are not handled carefully.

Mitigation:
- use non-blocking locks
- use a hard 20-minute timeout per invocation
- keep the wrapper script simple and deterministic
- test skip/timeout behavior directly where practical

## Success Criteria

This work is complete when:
- `server_shield` is a single structured Python project with internal packages for shared code and all three components
- Pulumi files live under a dedicated subdirectory inside `server_shield`
- inter-component state uses JSON plus Pydantic schemas with null/empty bootstrap defaults
- shared config and Sentry initialization are used by all three components
- logs from all three components are visible through `docker logs` and remain attributable to the originating component
- uncaught exceptions and non-zero exits are sent to Sentry when `SENTRY_DSN` is configured
- chain reader and chain writer are placeholder commands with correct bootstrap and skip behavior
- runtime state files are gitignored
- README architecture documentation matches the new model
- a single Docker image can run all three component loops with one-minute attempts, non-overlap, and 20-minute timeouts
- unit tests cover shared code and Pulumi composition behavior
