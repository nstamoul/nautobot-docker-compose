"""Bootstrap SHMS Git-backed Nautobot integrations.

Creates the Vault-backed Git auth secrets/groups and the GitRepository records
that exist on wyze, then optionally enqueues sync jobs for each repository.
Run this inside Nautobot's Django context, for example:

    nautobot-server nbshell --command "exec(open('/opt/nautobot/scripts/bootstrap_shms_git_repositories.py').read())"
"""

import os

from django.contrib.auth import get_user_model
from django.db import transaction

from nautobot.extras.models.datasources import GitRepository
from nautobot.extras.models.secrets import Secret, SecretsGroup, SecretsGroupAssociation
from nautobot.extras.secrets import register_secrets_provider

import nautobot_secrets_providers.secrets as plugin_secrets

for provider in plugin_secrets.secrets_providers:
    register_secrets_provider(provider)


SYNC_REPOS = os.getenv("SHMS_SYNC_GIT_REPOS", "true").lower() in {"1", "true", "yes", "on"}

SECRET_DEFS = {
    "NSTAM_GITHUB_HCKV_TOKEN": {
        "provider": "hashicorp-vault",
        "parameters": {
            "key": "token",
            "path": "NSTAM_GITHUB_HCKV_TOKEN",
            "vault": "default",
            "kv_version": "v2",
            "mount_point": "kv",
        },
    },
    "NSTAM_GITLAB_HCKV_TOKEN": {
        "provider": "hashicorp-vault",
        "parameters": {
            "key": "token",
            "path": "NSTAM_GITLAB_HCKV_TOKEN",
            "vault": "default",
            "kv_version": "v2",
            "mount_point": "kv",
        },
    },
    "NSTAM_GITLAB_HCKV_USERNAME": {
        "provider": "hashicorp-vault",
        "parameters": {
            "key": "username",
            "path": "NSTAM_GITLAB_HCKV_TOKEN",
            "vault": "default",
            "kv_version": "v2",
            "mount_point": "kv",
        },
    },
}

GROUP_DEFS = {
    "NSTAM_GITHUB_HCKV_TOKEN": [
        ("HTTP(S)", "token", "NSTAM_GITHUB_HCKV_TOKEN"),
    ],
    "NSTAM_GITLAB_HCKV_TOKEN": [
        ("HTTP(S)", "token", "NSTAM_GITLAB_HCKV_TOKEN"),
        ("HTTP(S)", "username", "NSTAM_GITLAB_HCKV_USERNAME"),
    ],
}

REPO_DEFS = [
    {
        "name": "Devicetype-library",
        "slug": "devicetype_library",
        "remote_url": "https://github.com/nstamoul/devicetype-library.git",
        "branch": "master",
        "provided_contents": ["welcome_wizard.import_wizard"],
        "secrets_group": "NSTAM_GITHUB_HCKV_TOKEN",
    },
    {
        "name": "SHMS_nautobot_backup_repo",
        "slug": "shms_nautobot_backup_repo",
        "remote_url": "http://git.shms.local/nstam/nautobot_backup_repo.git",
        "branch": "main",
        "provided_contents": ["nautobot_golden_config.backupconfigs"],
        "secrets_group": "NSTAM_GITLAB_HCKV_TOKEN",
    },
    {
        "name": "SHMS_nautobot_command_mappers_repo",
        "slug": "shms_nautobot_command_mappers_repo",
        "remote_url": "http://git.shms.local/nstam/nautobot_command_mappers_repo.git",
        "branch": "main",
        "provided_contents": ["nautobot_device_onboarding.onboarding_command_mappers"],
        "secrets_group": "NSTAM_GITLAB_HCKV_TOKEN",
    },
    {
        "name": "SHMS_nautobot_config_context_repo",
        "slug": "shms_nautobot_config_context_repo",
        "remote_url": "http://git.shms.local/nstam/nautobot_config_context_repo.git",
        "branch": "main",
        "provided_contents": ["extras.configcontext", "extras.configcontextschema"],
        "secrets_group": "NSTAM_GITLAB_HCKV_TOKEN",
    },
    {
        "name": "SHMS_nautobot_intended_repo",
        "slug": "shms_nautobot_intended_repo",
        "remote_url": "http://git.shms.local/nstam/nautobot_intended_repo.git",
        "branch": "main",
        "provided_contents": ["nautobot_golden_config.intendedconfigs"],
        "secrets_group": "NSTAM_GITLAB_HCKV_TOKEN",
    },
    {
        "name": "SHMS_nautobot_jobs_repo",
        "slug": "shms_nautobot_jobs_repo",
        "remote_url": "http://git.shms.local/nstam/nautobot_jobs_repo.git",
        "branch": "nautobot3-main",
        "provided_contents": ["extras.job"],
        "secrets_group": "NSTAM_GITLAB_HCKV_TOKEN",
    },
    {
        "name": "SHMS_nautobot_template_repo",
        "slug": "shms_nautobot_template_repo",
        "remote_url": "http://git.shms.local/nstam/nautobot_template_repo.git",
        "branch": "main",
        "provided_contents": ["nautobot_golden_config.jinjatemplate"],
        "secrets_group": "NSTAM_GITLAB_HCKV_TOKEN",
    },
]


def _get_bootstrap_user():
    User = get_user_model()
    return User.objects.filter(is_superuser=True).order_by("username").first()


@transaction.atomic
def ensure_vault_secrets():
    groups = {}
    for name, data in SECRET_DEFS.items():
        secret, created = Secret.objects.update_or_create(
            name=name,
            defaults={
                "description": "",
                "provider": data["provider"],
                "parameters": data["parameters"],
            },
        )
        print(("Created" if created else "Updated"), "secret", secret.name)

    for group_name, associations in GROUP_DEFS.items():
        group, created = SecretsGroup.objects.update_or_create(
            name=group_name,
            defaults={"description": ""},
        )
        groups[group_name] = group
        print(("Created" if created else "Updated"), "secrets group", group.name)

        current = set()
        for access_type, secret_type, secret_name in associations:
            secret = Secret.objects.get(name=secret_name)
            SecretsGroupAssociation.objects.update_or_create(
                secrets_group=group,
                access_type=access_type,
                secret_type=secret_type,
                defaults={"secret": secret},
            )
            current.add((access_type, secret_type))
            print("Ensured association", group.name, access_type, secret_type, "->", secret.name)

        stale = SecretsGroupAssociation.objects.filter(secrets_group=group).exclude(
            access_type__in=[a[0] for a in associations],
            secret_type__in=[a[1] for a in associations],
        )
        if stale.exists():
            stale.delete()

    return groups


@transaction.atomic
def ensure_git_repositories(groups):
    repos = []
    for data in REPO_DEFS:
        group = groups[data["secrets_group"]]
        repo, created = GitRepository.objects.update_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "remote_url": data["remote_url"],
                "branch": data["branch"],
                "provided_contents": data["provided_contents"],
                "secrets_group": group,
            },
        )
        repos.append(repo)
        print(("Created" if created else "Updated"), "git repository", repo.name)
    return repos


groups = ensure_vault_secrets()
repos = ensure_git_repositories(groups)

if SYNC_REPOS:
    user = _get_bootstrap_user()
    if user is None:
        raise RuntimeError("No superuser found to enqueue Git repository sync jobs.")
    for repo in repos:
        job_result = repo.sync(user=user, dry_run=False)
        print("Enqueued sync", repo.name, job_result.pk)
