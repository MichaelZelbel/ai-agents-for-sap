# The life of an agent

An agent is not a project you finish. It is a thing you run, and it has a life: it is
born in shadow, earns suggest-only, then draft-first, then a narrow bounded autonomy,
always on evidence. It is calibrated, watched for drift, re-reviewed when its scope
changes, and one day retired. This package makes the two runnable parts of that story
concrete.

- **A manifest** (`AgentManifest`): the record you keep next to each agent and version.
  Its purpose, its four owners, its autonomy rung, its prompt and model version.
- **A gate** (`evaluate`): reads the agent's recent numbers and rules on it, honestly
  and deterministically. Autonomy is earned on evidence, never granted on a good feeling.

## The autonomy ladder

An agent climbs one rung at a time, and only on evidence. It never jumps.

1. **shadow** runs in parallel and proposes, but its output is not used; you compare it to the humans.
2. **suggest_only** drafts and suggests; a human does everything and the agent acts on nothing.
3. **draft_first** stages a draft; a human approves every one before anything is written.
4. **bounded_auto** handles a narrow, low-risk lane on its own; everything else still needs a human.

## Run it

```
python lifecycle/check.py                     # rule on the whole example fleet
python lifecycle/check.py --agent invoice-posting
```

It reads a fleet of example agents caught at different points in their lives and, for
each, prints where it is and what to do next: promote (climb one rung), hold (keep
gathering evidence), review (something is off, stop and look), or retire (let it go).
No key, no network.

## The gate, in one paragraph

Given a manifest and the metrics the operate chapter already tells you to keep (weeks at
the current rung, override rate, a clean audit, exceptions, monthly usage), the gate
rules in this order. **Retire** if a standard SAP capability now covers the job, or if it
is established but barely used. **Review** if the audit does not verify or humans reject
too many proposals; that is a calibration case, not a promotion case. **Promote** if it
has run long enough at its rung with a low override rate and a clean audit; the top rung,
where it acts on its own, asks for more. **Hold** otherwise, and keep proving it. The
thresholds are in `gate.py`, in plain numbers you can argue with.

## What this is, and is not

The gate is a discipline, not an oracle. It turns "should we give it more freedom?" from
a hallway opinion into a decision with reasons on the record. A human still makes the
call, signs it off, and owns it. And the numbers it reads are only as honest as the
monitoring behind them; keep the operate chapter's rhythm, or the gate is grading on
made-up marks.
