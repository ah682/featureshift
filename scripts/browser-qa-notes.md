# Browser verification

The two browser checks use the Chrome DevTools Protocol and Node's built-in
`fetch` and `WebSocket`. They need Node 22 or newer, Chrome, and a running local
FeatureShift demo. They do not install an npm dependency or use a personal
browser profile.

Start the documented demo first (`make demo`). In a separate terminal, start an
isolated headless Chrome instance:

```sh
google-chrome --headless=new --disable-gpu --disable-dev-shm-usage --remote-debugging-port=9227 --remote-debugging-address=127.0.0.1 --user-data-dir=/tmp/featureshift-qa-chrome about:blank
```

Use this isolated profile only for the local fixture application. Chrome's
sandbox remains enabled. The remote debugging port listens on loopback.

Run the checks from the repository:

```sh
node scripts/browser_qa.mjs
node scripts/browser_failure_qa.mjs
```

`FEATURESHIFT_URL` defaults to `http://127.0.0.1:8765`.
`CHROME_DEBUG_URL` defaults to `http://127.0.0.1:9227`.
Each script creates a fresh tab in the supplied debugger instance. A seeded
selector report must exist; start from the documented reset/demo workflow so it
is among the recent runs. A check failure exits with status 1.

`browser_qa.mjs` verifies the seeded selector, disabled upload mode, four report
tabs, keyboard tab navigation, five responsive widths, a newly executed
unaffected fixture, the intentional-change audit, a newly executed selector,
review acceptance and its persisted audit event, and all three actual artifact
downloads. It also records page exceptions and console errors.

`browser_failure_qa.mjs` executes the failed installation, wrong-version
evidence, and probe-timeout examples. It checks that these produce explicit
error/uncertainty states, then executes a selector to leave a useful report
visible.

Both checks **create local runs**. The first also accepts one finding in its own
new selector run with an explicit UI-verification reason. These are disposable
fixture records, not a production review. Run the documented reset and demo
seed workflow after verification to restore the three clean demonstration
reports. Stop the isolated Chrome process when finished.

Screenshots, machine-readable check results, and downloaded artifacts are saved
under `.featureshift/verification/`. The main result is `ui-checks.json`; negative
path results are `ui-failure-checks.json`. Screenshots must also be inspected by
a person or image-capable tool; dimensions alone do not verify visual quality.

The managed development shell may block loopback sockets. Run the same checks
with the shell's explicit execution approval when required; no temporary wrapper
or private development path is part of the project setup.
