# The Four Agent Shapes

Almost every agent worth building is one of these four. In all of them, the AI only proposes, a deterministic guard decides, and autonomy is set by the risk of the job.

## 1. Propose and post

Read a document, let the AI propose a change, a guard checks it, a human approves, then it writes.

- AI's job: propose the action, such as a posting.
- Guard's job: balanced, allowed accounts, matches the source document.
- Autonomy: it acts, but only behind a human approval.
- Use it when: the job creates or changes a record.

## 2. Classify and route

The AI sorts an incoming thing into one of a few known categories, and firm rules send it down the matching path.

- AI's job: choose the category.
- Guard's job: accept only known categories, and do the routing itself.
- Autonomy: it sorts and routes; it does not change records.
- Use it when: the job decides which path something takes.

## 3. Match and check

The AI lines up records that are worded differently, and firm rules confirm the numbers agree.

- AI's job: match the items across documents.
- Guard's job: confirm quantities and amounts agree within tolerance.
- Autonomy: it produces a checked result for a human or a downstream step.
- Use it when: two or more records must agree before something proceeds.

## 4. Suggest only

The AI reads and drafts; a human decides whether to act. The agent takes no action itself.

- AI's job: classify the case and draft a reply.
- Guard's job: keep the category known, and prove nothing was acted on.
- Autonomy: the lowest. It suggests and stops.
- Use it when: the job is words and judgment, not a change to a record.

---

From *AI Agents for SAP* by Michael Zelbel, Appendix A.
