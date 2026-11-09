# Agentic SDLC Case Study: Spec-Driven Development

When requirements are unclear, time saved generating code can be lost in [repeated corrections](https://developer.microsoft.com/blog/spec-driven-development-spec-kit/). A mistaken assumption may affect several parts of the application, including its tests and documentation. As more features depend on that assumption, correcting it becomes harder. [IBM’s overview of SDD](https://www.ibm.com/think/topics/spec-driven-development) also describes how inconsistent implementations accumulate technical debt, making software harder to maintain.

Spec-driven development (SDD) uses an agreed specification to guide implementation and testing. Reviewing requirements before generating code gives developers an opportunity to identify conflicting assumptions while they are still easier to change. Acceptance scenarios describe the expected results, providing a reference for reviewing both the implementation and its tests. The specification is maintained as requirements evolve, so later development follows the updated decisions.

## From requirements to implementation

[GitHub Spec Kit](https://github.com/github/spec-kit/tree/ba8363f8ab56b2da456a81299cfdbfee1ef7b871) is an open-source toolkit for using spec-driven development with AI coding agents. Its templates and agent instructions take a project from defining requirements through technical planning to implementation tasks. I followed this sequence manually for the assignment, without installing Spec Kit’s CLI or using its automated workflow.

I used Spec Kit’s [specification template](https://github.com/github/spec-kit/blob/ba8363f8ab56b2da456a81299cfdbfee1ef7b871/templates/spec-template.md) to structure `SPEC.md`, with prioritized user scenarios, numbered requirements and acceptance examples describing the expected behavior. I also included explicit quality requirements, reasons for important decisions and a revision history, drawing on established requirements engineering practices (Wiegers and Beatty, [*Software Requirements*](https://www.microsoftpressstore.com/store/software-requirements-9780735679665), 3rd ed.).

Codex helped draft the requirements, which I checked against the assignment and revised before approving them as the basis for implementation. I then used the agreed specification to guide Codex’s tasks, with a separate technical plan explaining how the application would be built and `API.md` defining the endpoints, their inputs and their responses.

At the start of each task, including those continued in a new conversation, I instructed Codex to read the relevant requirements before proposing code changes. When requirements needed clarification or revision, Codex helped draft the changes, but I decided what to accept and record in `SPEC.md`.

## Example: requesting a different discount after approval

Suppose a reviewer approves a discount of 25 basis points, or 0.25 percentage points, and the relationship manager later wants to request 40. Changing the original request would make its approval appear to cover 40, even though the reviewer approved only 25. Under the [agreed rule](https://github.com/emfrg/blue-harvest-assignment/blob/ef0ad0143b5cd05a8653eb250585b64f2386907c/SPEC.md#L126-L136), the manager submits a separate request for 40, and 25 remains active while the new request awaits a decision or if it is declined. If the reviewer approves 40, it becomes the active discount while the earlier request and its approval remain unchanged.

During development, Codex proposed blocking further requests once an application had an approval. I asked it to consult `SPEC.md`, and it corrected its proposal to allow a new request for a different discount. Checking the proposal against the agreed rule caught the mistake before it became part of the API.

The [automated API test for this scenario](https://github.com/emfrg/blue-harvest-assignment/blob/735bad5aa0357153a49d7c8b373eb76c4118e8d3/tests/test_api.py#L258-L269) checks that a manager can submit a new request after an approval, that the previous discount stays in place until another request is approved, and that earlier requests and decisions remain in history.

## Development effort and benefits

GitHub Spec Kit describes code as the [“last-mile approach”](https://github.com/github/spec-kit/blob/ba8363f8ab56b2da456a81299cfdbfee1ef7b871/spec-driven.md#the-power-inversion): the specification defines what to build, and the technical plan guides how those requirements become code. Coding remains a demanding step, but the specification is where the intended behavior is agreed and maintained as the application evolves. This matched my experience: preparing the specification and reviewing Codex’s tests took substantially more time than writing the core application code.

Having the requirements, acceptance scenarios and success criteria in one place gave me a basis for reviewing the implementation as a whole. I checked both the code and the expected results in Codex’s tests against them, including whether the tests covered the agreed behavior. The quality requirements covered reliability, including whether saved data survived a restart. The delivery criteria required setup instructions and sample data that another engineer could use to run the main workflow.

For a team, the specification gives engineers and business stakeholders a common basis for deciding how the application should change. An engineer adding a feature can propose updates to the requirements and acceptance scenarios in `SPEC.md`, review them with the team and use the agreed changes to guide implementation and testing. Maintaining `SPEC.md` alongside the code gives the next engineer or coding agent the context to develop new features with less time spent clarifying requirements and correcting code based on conflicting assumptions.

## Limitations and next steps

Time constraints limited this assignment to a manual adaptation of SDD. Codex needed repeated instructions to consult `SPEC.md` and follow the agreed process, which meant additional revisions and closer review of its output. This limited how far I could let it proceed independently on a task before reviewing its decisions and results.

Spec Kit’s reusable [workflow commands](https://github.com/github/spec-kit/blob/ba8363f8ab56b2da456a81299cfdbfee1ef7b871/docs/reference/agentic-sdd.md) could give Codex clearer instructions about which documents to read, which tasks to complete and which checks to run at each stage. This could let it proceed more independently between agreed review points. Its review commands also check for contradictions between project documents and for code that does not meet the agreed requirements. Before approving a proposed correction, I would check that the agent had identified an actual problem and that its proposed fix matched the requirements.

The extent to which SDD reduces development time and rework would need to be measured across comparable tasks. I did not measure time savings, rework effort or the tokens used to restore agent context in this assignment. The time allocation below still offers an approximate comparison of the effort spent on core API development with that spent on setup, review, documentation and building a simple frontend on top of the backend service.

### Extending the workflow

- **Adopt the full Spec Kit workflow.** Integrate its agent commands, templates and consistency checks, with human review at each stage. A smaller first step would be a dedicated SDD skill that provides reusable instructions, reducing repeated prompting and helping the agent follow the process consistently.

- **Support team collaboration.** Let business stakeholders and engineers propose and review specification changes through pull requests. Agree who approves business rules and technical decisions, and record the reasons for those decisions so other contributors can understand and build on them.

- **Automate specification updates.** Add a plugin or workflow that uses requirements maintained in tools such as Jira or Trello to draft updates to `SPEC.md` for review and approval. This would reduce manual copying when the wider team changes its requirements.

- **Measure the effect on delivery.** Compare implementation and rework effort, repeated clarification and the tokens used to restore agent context across similar tasks. Include the time spent maintaining and reviewing the specification when assessing the overall savings.

## Time allocation

I spent approximately **28 hours** on the assignment.

| Period | Activities | Time |
|---|---|---:|
| Initial preparation | Specification preparation and review; progress logging, Git and sprint management | 3 h |
| Thursday | FastAPI and HTTP review; API, database and dependency setup; models; testing and idempotency review; API implementation | 6 h |
| Friday | API implementation review and user-facing wording | 2 h |
| Saturday | Tests and comments; frontend setup | 3 h |
| Sunday | Frontend specification, implementation and realistic flows; documentation, extra endpoints and cleanup | 6 h |
| Monday | Documentation and Agentic SDLC case write-up | 8 h |
| **Total** | | **28 h** |
