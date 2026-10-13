# Access and operations contract

Status: proposed specification conventions, pending product acceptance before implementation. Addresses R08–R10. This document defines observable behavior without selecting a framework, queue product, identity provider, or storage library.

## 1. Household authority

Every private resource carries a household identity. Authenticate the caller and check household membership or an explicit scoped grant on every API operation, job command, result read, and artifact retrieval. A client-supplied household ID is a selection, never proof of authority. Database constraints and storage paths supplement authorization; neither object-ID secrecy nor a hidden UI control is sufficient.

Application users and modeled household members are separate entities. A user can belong to multiple households, with a clear active-household indicator. Switching the UI context clears household-specific cached data and in-flight display updates. Each background request remains tied to its original authorized household.

| Action | Owner | Editor | Viewer | Read-only guest | Operations administrator |
|---|---|---|---|---|---|
| Read household plans and results | Yes | Yes | Yes | Granted scenario/revision only | No routine access |
| Edit plans or import observations | Yes | Yes | No | No | No |
| Run calculations within quota | Yes | Yes | No | No | No plan execution access |
| Cancel a job | Any household job | Own jobs | No | No | Operational cancel with metadata only |
| Download result CSV/PDF | Yes | Yes | Yes | Only if included in grant | No |
| Export full household JSON | Yes | No | No | No | No |
| Invite/change roles or create/revoke links | Yes | No | No | No | No |
| Publish sanitized scenario | Yes, after disclosure preview | No | No | No | No |
| Delete a plan | Yes | No | No | No | No routine financial-content deletion |
| Delete household | Yes, with explicit confirmation | No | No | No | Account-abuse removal under a separately audited administrative policy |
| Manage quotas, jobs, service health | Household usage view | Own job view | No | No | Yes, without financial payloads |
| Grant support access | Yes | No | No | No | Cannot self-grant |

Keep at least one owner while a household is active. Ownership transfer requires an accepted membership and an explicit transfer. An invitation is household-bound, expiring, single-use, and revocable; accepting it does not grant access to other households sharing an email domain.

Viewer download is a deliberate permission: revocation cannot erase a file already downloaded. The interface explains this when granting access. Account deletion and household deletion are distinct; deleting one user's login must not erase other members' shared household data implicitly.

## 2. Grants, links, and public examples

Guest grants identify an immutable scenario revision or explicitly selected result set, permitted artifact types, expiry, and optional password requirement. New revisions are excluded unless the owner deliberately changes the grant. Revocation takes effect on the next access check; an in-progress download that has already transmitted data cannot be recalled.

Avoid long-lived unrevocable storage URLs. The gateway must recheck access for each retrieval, and private response caching must respect logout/revocation. If short-lived signed object URLs are used, the residual access window is a documented limitation with an approved maximum, not a claim of immediate revocation.

Basic-calculator URLs are an explicit share action containing only the documented allowlisted inputs. Show that income, expenses, age, and asset inputs will be visible to anyone with the URL and may appear in browser history. Prefer URL fragments to keep values out of request paths; omit identity, account details, plan IDs, and financial timelines. Sharing a detailed plan uses a scoped access token, never embedded financial data. Tokens themselves must not appear in normal logs.

Public scenarios are separate copies. Proposed publication behavior replaces identities, dates, free text, and exact balances with user-reviewed synthetic examples, including consistent synthetic stream amounts; merely removing names is insufficient. The disclosure preview shows every public field, including derived charts and metadata. The private source remains unchanged, and later private edits do not update the public copy. Owners can unpublish their copies; downloaded public data cannot be recalled. The published content must not claim to preserve the private plan's exact results after sanitization.

## 3. Support and infrastructure trust

A support grant names the recipient, household, scope, reason, expiry, and granting owner. Proposed default is read-only access to selected revisions for a bounded period; editing requires a separate explicit grant. Owners can revoke support access and inspect an audit trail. Administrators cannot use an operational role to self-authorize financial access.

Audit grant creation, access, export, modification, expiry, and revocation with actor/resource IDs and timestamps. Audit records must not contain balances, income, document content, passwords, or tokens. Show operational failure categories without financial payloads; enhanced diagnostics require explicit scoped handling and retention.

Host/database operators can access stored plaintext through infrastructure privileges. This application permission model does not provide end-to-end encryption against those operators. Protect storage, backups, keys, and operational credentials according to the deployment's threat boundary; keep secrets outside version control and normal logs.

## 4. Job state and publication

| Current state | Permitted transition | Contract |
|---|---|---|
| Queued | Running, cancelled | Admission reserves quota; cancellation releases unused reservation |
| Running | Succeeded, failed, cancel-requested | Worker uses immutable input manifest; progress identifies completed versus planned work |
| Cancel-requested | Cancelled | Worker stops at a safe boundary; leases expire if it does not respond; no final successful publication |
| Running with lost worker lease | Queued retry, failed | Retry uses same run identity/settings; bounded attempts and backoff are recorded |
| Succeeded, failed, cancelled | No state rewrite | A user-requested rerun is a new job/run; prior terminal result is retained according to policy |

Proposed cancellation race rule: cancellation acceptance and final publication compete through one atomic state transition. If publication wins, the job is already succeeded and cancellation reports that fact. If cancellation wins, a late worker cannot publish success. Temporary artifacts from cancelled or superseded attempts are inaccessible and cleaned up under retention policy.

Worker leases and attempt IDs prevent stale attempts from overwriting current state. Retries may perform duplicate computation but must publish at most one committed result set. Commit financial results, manifest, and artifact references consistently; a missing artifact leaves a failed/incomplete state, not apparent success.

Progress reports completed units and total planned units where known. Optimization with an adaptive budget reports evaluations and its cap rather than a fabricated completion percentage. Partial results identify their status and are never substituted for completed success rates.

The scheduler enforces per-user and per-household active-job limits, queued-job limits, trial/evaluation caps, artifact-storage quotas, and global resource limits. Admission policy, queue ordering/fairness, reservation, usage charging on retries/cancellation, and administrator overrides must be configured and visible. A rejected job states the exceeded quota without exposing other households' workloads. Exact quota defaults and capacity targets await benchmarks.

The interactive baseline and worker baseline call the same versioned calculation semantics. Browser previews must either use that compatible engine or be labeled provisional until checked; a separate approximate formula cannot masquerade as the saved authoritative result.

## 5. Retention, export, and deletion

Publish a retention table before production use: private revisions, results, raw imports, temporary artifacts, access audits, public copies, and backups each require a purpose, retention duration, deletion mechanism, and owner/operator authority. Exact durations are deployment decisions; unset required values are a production-readiness failure.

Household export includes plan revisions, assumptions, observations, permitted results, and the dependency manifest in a versioned format. It excludes credentials, recovery secrets, other households' data, and unlicensed dataset contents. A JSON plan backup must round-trip plan semantics; it is not automatically a complete system backup or a licensed market-data bundle.

Deletion first revokes access and jobs, then removes active private records and artifacts, and schedules removal from caches and derived indexes. Record an opaque deletion marker sufficient to prevent a later backup restore from resurrecting access. Audit retention keeps minimal nonfinancial operational facts where policy requires it. The user-facing status distinguishes active-data deletion from backup expiry and states the maximum retention window.

Backups are not silently edited in place. They expire under the declared policy; on restore, apply deletion markers and revocations before serving requests. User-published copies are proposed to unpublish when their household is deleted; a deliberately separately donated synthetic example requires explicit consent and independent ownership. A standalone plan deletion shows linked public copies and their proposed disposition before confirmation.

Reproducibility lasts only while required inputs, dependency versions, engine artifacts, and licenses remain available. Deletion takes precedence over retaining private input snapshots. A result without sufficient dependencies must state that rerun is unavailable.

## 6. Offline operation and recovery

Normal operation uses bundled frontend assets, installed engine/rule/data versions, local persistence, and configured authentication. No external analytics, fonts, license checks, or mandatory bank APIs are required. Online updates are optional and separated from calculation. An operator can install a reviewed offline update bundle.

Local login is supported without SMTP. Proposed recovery uses one-time recovery codes generated at setup and stored by the user, plus an explicit operator-assisted identity recovery procedure with audit and session invalidation. Recovery does not itself grant household membership. Define secure bootstrap and last-owner recovery before release. Do not ship a universal default password.

An externally hosted identity provider may be unreachable without internet; deployments promising offline login must configure local login or a reachable local identity provider. UI wording must state this dependency. SMTP invitations can be replaced by owner-delivered one-time invitation tokens without making SMTP mandatory.

## 7. Backup, upgrades, and data updates

Back up PostgreSQL and file/object artifacts as one recoverable consistency set, together with manifests, configuration, and required engine/data versions. Manage secret-key recovery separately and protect both backups and key access. Automatic schedules require visible last-success status, failure reporting, and retention. Recovery-point and recovery-time objectives are explicit deployment targets established through a restore drill, not guessed sizing claims.

A restore drill reconstructs an isolated deployment, checks authentication and isolation, retrieves representative artifacts, applies deletion/revocation records, and reruns a pinned known fixture. Record measured loss window and restoration time. Restored jobs do not blindly resume before quota, lease, and publication consistency checks.

Application upgrades provide schema migration compatibility, pre-upgrade backup guidance, and a tested rollback or restore path. Never promise rollback through a destructive migration without a compatible recovery route. Old engine versions may be needed to reproduce retained runs; an update cannot rewrite their manifests.

Market/tax/mortality updates have provenance, integrity digests, license metadata, validation results, and operator review. Installation creates new immutable versions; plan reruns explicitly select them. Reject missing dependencies or incompatible versions before activation. Update rollback changes the selected version, not historical data files in place.

Logs include job IDs, state changes, duration, resource usage, and sanitized error categories. Health/readiness checks distinguish service liveness, database availability, storage access, and worker capacity without exposing financial values. Sizing benchmarks cover realistic plan complexity, trials, concurrent households, cancellation, and storage retention; record hardware and settings with measurements.

## 8. Operational walkthroughs

These are design-level acceptance cases, not executed infrastructure tests.

| Case | Expected behavior |
|---|---|
| Household A user guesses B's result ID | Read, export, and download deny access at the server; job existence is not disclosed unnecessarily |
| Viewer attempts a calculation or plan edit | Denied; possession of a read grant cannot enqueue spending-heavy work |
| Owner revokes guest link | Next authorized retrieval fails; any previously delivered data is outside recall |
| Operator inspects a failed job | Sees identifiers, timing, and sanitized cause; no financial input payload |
| Worker dies after writing temporary result | Lease retry reuses immutable inputs; only one attempt can commit the final result |
| Cancellation accepted before late worker completion | Job ends cancelled; temporary completion cannot publish success |
| Publication committed before cancellation | Cancellation reports already succeeded; committed output remains valid |
| Deleted household appears in an older backup | Restore applies deletion marker before service access and removes restored active data |
| SMTP and internet unavailable | Local login, saved plans, installed-data calculations, local exports, and documented recovery remain usable |
| Market update installed | Existing runs still reference old digests; new runs opt into the reviewed version |

Each walkthrough must eventually become an integration or restore test at its delivery stage. This specification review checks coherence of the proposed contracts only.
