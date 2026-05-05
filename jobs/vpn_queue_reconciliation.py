"""Reconcile SHMS tenant-scoped VPN queues and job assignments."""

import re

from nautobot.apps.jobs import BooleanVar, Job, MultiObjectVar, register_jobs
from nautobot.extras.models import Job as JobModel
from nautobot.extras.models import JobQueue, JobQueueAssignment
from nautobot.tenancy.models import Tenant


VPN_QUEUE_PREFIX = "vpn-"
VPN_LEGACY_QUEUE = "vpn"
VPN_GENERIC_QUEUE = "vpn-generic"
name = "VPN management"

# These names should remain aligned with the actual user-facing job names in SHMS.
# Control-plane jobs stay on the default queue and are intentionally NOT assigned
# to tenant VPN queues.
VPN_CONTROL_JOB_NAMES = [
    "Control VPN",
    "Reconcile VPN Tenant Queues",
]

# These jobs actually need a tenant-scoped VPN worker and should be assigned to
# every tenant queue created by this reconciler. The list is based on the
# legacy SHMS `vpn` queue plus the current SHMS job names where they have
# drifted from the older labels.
VPN_BOUND_JOB_NAMES = [
    # Core onboarding / discovery / sync flows.
    "Customer Onboarding Workflow",
    "Sync Devices From Network (custom)",
    "Sync Network Data From Network, extended to include Tenant",
    "Sync Devices From Network - Cisco ASA",
    "Sync Network Data From ASA",
    "Sync Devices from FMC",
    "Sync Network Data From FMC",
    "Sync Devices From Network - FortiGate",
    "Sync Network Data From FortiGate",
    "Scan network and create cables",
    "Scan network for new devices not present in NB",
    "Find Unmanaged Switch Candidates",
    "Create Diagram with Unmanaged Switches",
    "LAN Mapper",
    "Network crawler, which given IP addresses, will crawl the network and create output",
    "Materialize Unreachable Devices",
    "Script to update devices in ENA-ONs SCADA network",
    # Post-processing and data shaping.
    "Assign Tenant by Primary IP",
    "Validate and Cleanup Cables",
    "Extract Domain Names from Backups",
    "Update Cisco Device Domain Names",
    "Enriches device data",
    "Enrich device data",
    "Network Lifecycle Cleanup",
    "Cleanup Inactive Devices",
    # Reporting and export jobs that were historically run on the VPN worker.
    "Create NSOT Excel",
    "Create device coverage dictionary and export to excel",
    "Export NB inventory to excel for use in other scripts",
    "Find Unused Interfaces (Counters)",
    "Generate Migration Bundle",
    "Refresh coverage and EOX",
    "Summarize Unused Interface Capacity",
    "Bulk Device Management",
    # Plugin-owned jobs that still need tenant queue assignment in SHMS.
    "Backup Configurations",
    "VMWare vSphere (custom)",
    "VMWare vSphere ⟹ Nautobot",
]


def _tenant_queue_slug(value: str) -> str:
    """Create a deterministic, human-readable queue slug for a tenant name."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def tenant_queue_name(tenant: Tenant) -> str:
    """Return the canonical VPN queue name for a tenant."""
    slug = _tenant_queue_slug(tenant.name)
    if slug:
        return f"{VPN_QUEUE_PREFIX}{slug}"
    return f"{VPN_QUEUE_PREFIX}tenant-{str(tenant.id)[:8]}"


class ReconcileVpnTenantQueues(Job):
    """Create tenant-scoped VPN queues and assign VPN-capable jobs to them."""

    tenants = MultiObjectVar(
        model=Tenant,
        required=False,
        description="Restrict reconciliation to these tenants. Leave blank for all tenants.",
    )
    include_generic_queue = BooleanVar(
        default=True,
        description="Ensure the shared fallback queue vpn-generic exists.",
    )
    cleanup_unselected_tenant_queues = BooleanVar(
        default=False,
        description=(
            "Delete SHMS-managed tenant VPN queues that are not selected in this run. "
            "Use only after reviewing the dry-run output."
        ),
    )
    dry_run = BooleanVar(
        default=True,
        description="Log intended changes without modifying Nautobot.",
    )

    class Meta:
        name = "Reconcile VPN Tenant Queues"
        description = "Create tenant-based VPN queues and assign VPN-capable jobs to them."
        has_sensitive_variables = False
        task_queues = ["default"]
        soft_time_limit = 300
        time_limit = 600

    def _get_target_tenants(self, tenants):
        selected = list(tenants) if tenants else list(Tenant.objects.order_by("name"))
        self.logger.info("Selected %s tenant(s) for queue reconciliation.", len(selected))
        return selected

    def _get_vpn_jobs(self):
        configured_jobs = list(JobModel.objects.filter(name__in=VPN_BOUND_JOB_NAMES).order_by("name"))
        found_names = {job.name for job in configured_jobs}
        missing = [name for name in VPN_BOUND_JOB_NAMES if name not in found_names]
        legacy_jobs = list(
            JobModel.objects.filter(job_queue_assignments__job_queue__name=VPN_LEGACY_QUEUE)
            .exclude(name__in=VPN_CONTROL_JOB_NAMES)
            .distinct()
            .order_by("name")
        )
        jobs_by_name = {job.name: job for job in configured_jobs}
        legacy_only = []

        for job in legacy_jobs:
            if job.name not in jobs_by_name:
                legacy_only.append(job.name)
            jobs_by_name[job.name] = job

        jobs = [jobs_by_name[name] for name in sorted(jobs_by_name)]

        for name in missing:
            self.logger.warning("VPN-capable job '%s' is not installed in SHMS.", name)

        if legacy_only:
            self.logger.info(
                "Including %s VPN job(s) from legacy queue %s: %s",
                len(legacy_only),
                VPN_LEGACY_QUEUE,
                ", ".join(legacy_only),
            )

        self.logger.info("Found %s installed VPN-bound job(s) to assign.", len(jobs))
        self.logger.info(
            "Control-plane jobs intentionally left on the default queue: %s",
            ", ".join(VPN_CONTROL_JOB_NAMES),
        )
        return jobs

    def _current_managed_vpn_jobs(self):
        """Return jobs already attached to any SHMS-managed VPN queue."""
        managed_queue_names = [VPN_LEGACY_QUEUE, VPN_GENERIC_QUEUE]
        managed_queue_names.extend(JobQueue.objects.filter(name__startswith=VPN_QUEUE_PREFIX).values_list("name", flat=True))
        return list(
            JobModel.objects.filter(job_queue_assignments__job_queue__name__in=managed_queue_names)
            .exclude(name__in=VPN_CONTROL_JOB_NAMES)
            .distinct()
            .order_by("name")
        )

    def _ensure_queue(self, *, name, tenant, dry_run):
        queue = JobQueue.objects.filter(name=name).first()
        created = queue is None

        if queue is None:
            self.logger.info(
                "%s queue %s (tenant=%s).",
                "Would create" if dry_run else "Creating",
                name,
                getattr(tenant, "name", None),
            )
            if dry_run:
                return None, True
            queue = JobQueue.objects.create(
                name=name,
                description=f"Tenant-scoped VPN queue for {tenant.name}" if tenant else "Generic VPN queue",
                queue_type="celery",
                tenant=tenant,
            )
            return queue, True

        desired_description = (
            f"Tenant-scoped VPN queue for {tenant.name}" if tenant else "Generic VPN queue"
        )
        changes = []
        if queue.queue_type != "celery":
            changes.append(("queue_type", queue.queue_type, "celery"))
        if queue.description != desired_description:
            changes.append(("description", queue.description, desired_description))
        if queue.tenant_id != getattr(tenant, "id", None):
            changes.append(("tenant", queue.tenant_id, getattr(tenant, "id", None)))

        if changes:
            self.logger.info(
                "%s queue %s with %s.",
                "Would update" if dry_run else "Updating",
                name,
                ", ".join(f"{field}={old!r}->{new!r}" for field, old, new in changes),
            )
            if not dry_run:
                queue.queue_type = "celery"
                queue.description = desired_description
                queue.tenant = tenant
                queue.save()

        return queue, created

    def _ensure_assignments(self, *, queue, queue_name, jobs, dry_run):
        for job in jobs:
            exists = JobQueueAssignment.objects.filter(job=job, job_queue=queue).exists() if queue else False
            if exists:
                continue
            self.logger.info(
                "%s assignment: job=%s queue=%s.",
                "Would create" if dry_run else "Creating",
                job.name,
                queue_name,
            )
            if not dry_run:
                JobQueueAssignment.objects.create(job=job, job_queue=queue)

    def _persist_job_queue_override(self, *, jobs, managed_queues, dry_run):
        managed_queue_ids = {queue.id for queue in managed_queues if queue is not None}
        managed_queue_names = sorted(queue.name for queue in managed_queues if queue is not None)

        for job in jobs:
            current_queues = list(job.job_queues.order_by("name"))
            preserved_queues = [
                queue for queue in current_queues if queue.id not in managed_queue_ids and not queue.name.startswith(VPN_QUEUE_PREFIX)
            ]
            desired_queues = {queue.id: queue for queue in preserved_queues}
            for queue in managed_queues:
                if queue is not None:
                    desired_queues[queue.id] = queue

            desired_queue_list = sorted(desired_queues.values(), key=lambda queue: queue.name)
            desired_queue_ids = {queue.id for queue in desired_queue_list}
            current_queue_ids = {queue.id for queue in current_queues}

            needs_override = not job.job_queues_override
            needs_queue_update = current_queue_ids != desired_queue_ids

            if not needs_override and not needs_queue_update:
                continue

            self.logger.info(
                "%s persistent queue override for job=%s queues=%s.",
                "Would configure" if dry_run else "Configuring",
                job.name,
                ", ".join(managed_queue_names),
            )
            if dry_run:
                continue

            job.job_queues_override = True
            job.save()
            job.job_queues.set(desired_queue_list)

    def _cleanup_stale_queues(self, *, expected_names, dry_run):
        stale_queues = JobQueue.objects.filter(name__startswith=VPN_QUEUE_PREFIX).exclude(name=VPN_GENERIC_QUEUE).exclude(
            name__in=expected_names
        )
        for queue in stale_queues.order_by("name"):
            self.logger.warning(
                "%s stale queue %s.",
                "Would delete" if dry_run else "Deleting",
                queue.name,
            )
            if not dry_run:
                queue.delete()

    def run(
        self,
        tenants=None,
        include_generic_queue=True,
        cleanup_unselected_tenant_queues=False,
        dry_run=True,
    ):
        target_tenants = self._get_target_tenants(tenants)
        jobs_by_name = {job.name: job for job in self._get_vpn_jobs()}
        for job in self._current_managed_vpn_jobs():
            jobs_by_name[job.name] = job
        jobs = [jobs_by_name[name] for name in sorted(jobs_by_name)]
        expected_tenant_queue_names = []
        managed_queues = []

        for tenant in target_tenants:
            queue_name = tenant_queue_name(tenant)
            expected_tenant_queue_names.append(queue_name)
            queue, created = self._ensure_queue(name=queue_name, tenant=tenant, dry_run=dry_run)
            if created:
                self.logger.info("Tenant %s maps to queue %s.", tenant.name, queue_name)
            if queue is not None:
                managed_queues.append(queue)
            self._ensure_assignments(queue=queue, queue_name=queue_name, jobs=jobs, dry_run=dry_run)

        if include_generic_queue:
            generic_queue, _ = self._ensure_queue(name=VPN_GENERIC_QUEUE, tenant=None, dry_run=dry_run)
            if generic_queue is not None:
                managed_queues.append(generic_queue)
            self._ensure_assignments(
                queue=generic_queue,
                queue_name=VPN_GENERIC_QUEUE,
                jobs=jobs,
                dry_run=dry_run,
            )

        legacy_queue = JobQueue.objects.filter(name=VPN_LEGACY_QUEUE).first()
        if legacy_queue is not None:
            managed_queues.append(legacy_queue)

        self._persist_job_queue_override(jobs=jobs, managed_queues=managed_queues, dry_run=dry_run)

        if cleanup_unselected_tenant_queues:
            self._cleanup_stale_queues(expected_names=expected_tenant_queue_names, dry_run=dry_run)

        result = {
            "tenant_count": len(target_tenants),
            "vpn_job_count": len(jobs),
            "tenant_queues": expected_tenant_queue_names,
            "generic_queue": include_generic_queue,
            "dry_run": dry_run,
        }
        self.logger.info("VPN tenant queue reconciliation completed: %s", result)
        return result


register_jobs(ReconcileVpnTenantQueues)
