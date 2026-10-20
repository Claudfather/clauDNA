# Trap classes

A safeguard's own explanation is a claim to check. Read its consumers and enforcement path, then use authorized run, alert, query or deploy history where needed. Record the observation window and unavailable evidence. Repeating a ticket's rationale does not upgrade confidence.

## 1. Safeguards that fail toward silence

**Look for:** exemptions and expiry dates; skipped or warn-only CI checks; empty selections returning success; missing configuration logging and returning; paused schedules disappearing from monitoring.

**Verify:** trace what reads the exception and what the gate actually prevents. Turn event-based exits (such as "after its first successful run") into a history check. Compare workflow events, branch/path filters and deployed state with the claimed behavior. Establish who detects a silent monitor or missing token. Check whether coupled config must be removed together to avoid reactivating one half.

**Counterexamples:** an intentional CI expiry can be a valid merge gate; a dateless manual exemption with an owner and compensating control is not automatically decay. Verify the control where possible; otherwise report it as unverified. A fixed date alone does not establish a defect.

**Remediation:** make the intended transition observable and route it to the responsible owner. Prefer a condition the system can evaluate over repeated manual renewal when the condition is measurable. Keep existing sound gates. Replay proposed alert enrollment against representative history when available so healthy runs do not become new pages.

## 2. Person dependence

**Look for:** production writes or deploys using a personal identity; owner maps and alert routes with silent defaults; credentials or operational steps that only one person can restore.

**Verify:** confirm the identity and its actual role, routing and recovery path. Check relevant login/email/chat aliases within scope; a matching name is not identity proof. Compare deployed configuration with the checkout. Missing roster access is a stated limit, not evidence that someone left.

**Counterexamples:** a team rotation, documented recovery path or deliberately accepted personal ownership can satisfy the requirement. Flag the concrete continuity failure, not every human name.

**Remediation:** recommend durable team/service ownership and explicit unresolved-owner handling where needed. Account migration, credential changes and offboarding actions require their own authorization; reassign dependents before removing a routing entry.

## 3. Dead-end outputs

**Look for:** jobs, exports, tables or artifacts whose consumers are unnamed; legacy writers and bridges; work repeatedly produced without an observable downstream effect.

**Verify:** distinguish the writer's own queries from reads, inspect all known in-scope consumers, and check paused launchers that may read again when resumed. State the history window and any external consumers that could not be checked. Quantify storage/runtime cost only from available measurements.

**Counterexamples:** no recent reads, no local reference or a paused reader alone does not prove safe retirement. A documented external consumer or retention obligation may justify the output.

**Remediation:** propose reversible writer/config retirement with owner agreement before removing data or code, accounting for dormant readers and rollback. An audit never deletes a candidate output.

## 4. Duplicated registries

**Look for:** owner/ID maps, allowlists, enums and copied metadata maintained in several places; documentation listing copies; equality checks that force unrelated metadata edits into a governance file.

**Verify:** find the current copies by distinctive keys, compare them and trace which consumers use each one. Check whether they are generated or intentionally independent. Trace the coupling even when values currently agree: what else does the next rename or ownership change trigger?

**Counterexamples:** generated copies with a generator and drift check are not independently maintained registries. Similar names or values alone do not prove shared ownership or harmful duplication.

**Remediation:** derive genuinely shared values from their existing owner and correct stale descriptions of the measured locations. Avoid creating another registry or validator merely to keep new copies synchronized.

## 5. Hidden blast radius

**Look for:** metadata in shared deploy paths; path/event-based CI modes; fan-out deployments; hooks whose empty input selects the whole tree; fixes that merge without reaching the running safeguard.

**Verify:** read the trigger and downstream workflow end to end, including its computed diff range. List the actual targets for the proposed edit; the last commit alone may not represent a multi-commit push. For hooks, trace the real input format, missing/empty arguments and target selection without running destructive formatters against the repository.

**Counterexamples:** a broad deploy can be intended, documented and affordable. Report a mismatch with the promised boundary or an unguarded side effect, not breadth alone.

**Remediation:** narrow the affected boundary where justified, guard empty selections, and state material side effects in the existing PR. Confirm that the safeguard fix itself ships through the real deployment path.
