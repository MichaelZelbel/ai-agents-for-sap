# Five Questions Before You Build

Score a candidate job. Mostly yes: build it. A no on question 2 or question 5 is a warning: that job may be too open-ended or too dangerous for a first agent. Pick an easier one and come back.

1. **Frequent?** Enough volume that automating it actually saves real time?
2. **Rule-checkable?** Could a deterministic guard catch a wrong answer?
3. **Approval point?** Is there a natural human gate, or can it be suggest-only?
4. **Data reachable?** An API, a document, or a message the agent can actually read?
5. **Recoverable?** Would a mistake be caught and fixed before it does harm?

Then three quick moves:

- **Map it to a shape.** Propose and post, classify and route, match and check, or suggest only (see the shapes card).
- **Pick the road.** Does it write to the system of record under rules only you know? Code. Otherwise low-code may do.
- **Set the dial.** Suggest-only for words and judgment. A tight guard plus a human approval for anything that writes.

---

From *AI Agents for SAP* by Michael Zelbel, Chapter 29.
