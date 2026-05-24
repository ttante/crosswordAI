"""Production hardening checks and deployment controls."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class HardeningResult:
    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SecretRef:
    name: str
    provider: str
    required: bool = True
    env_var: str | None = None


@dataclass(frozen=True, slots=True)
class SecretCheckResult:
    configured: bool
    missing: tuple[str, ...]
    provider: str


@dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    name: str
    database_url: str
    artifact_root: str
    allowed_hosts: tuple[str, ...]
    secrets_provider: str
    debug: bool = False
    log_level: str = "INFO"


@dataclass(frozen=True, slots=True)
class RolePermission:
    role: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BackupPolicy:
    enabled: bool
    schedule: str
    retention_days: int
    artifact_retention_days: int
    restore_test_interval_days: int


@dataclass(frozen=True, slots=True)
class DisasterRecoveryPlan:
    rpo_minutes: int
    rto_minutes: int
    runbook_ref: str
    escalation_contacts: tuple[str, ...]
    last_drill_at: str | None = None


@dataclass(frozen=True, slots=True)
class ProductionReadinessReport:
    environment: str
    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    controls: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ManagedSecretValue:
    name: str
    provider: str
    version: str
    redacted_value: str


@dataclass(frozen=True, slots=True)
class DeploymentManifest:
    environment: EnvironmentConfig
    required_secrets: tuple[SecretRef, ...]
    backup_policy: BackupPolicy
    disaster_recovery: DisasterRecoveryPlan
    egress_urls: tuple[str, ...]
    image_ref: str
    migration_ref: str
    config_checksums: dict[str, str] = field(default_factory=dict)


class SecretProvider(Protocol):
    provider: str

    def get_secret(self, ref: SecretRef) -> ManagedSecretValue | None:
        ...


class EnvSecretManager:
    def __init__(self, provider: str = "env") -> None:
        self.provider = provider

    def check(self, secrets: tuple[SecretRef, ...]) -> SecretCheckResult:
        missing = []
        for secret in secrets:
            if not secret.required:
                continue
            env_var = secret.env_var or secret.name
            if not os.environ.get(env_var):
                missing.append(secret.name)
        return SecretCheckResult(configured=not missing, missing=tuple(missing), provider=self.provider)

    def get_secret(self, ref: SecretRef) -> ManagedSecretValue | None:
        env_var = ref.env_var or ref.name
        value = os.environ.get(env_var)
        if value is None:
            return None
        return ManagedSecretValue(ref.name, self.provider, "env", _redact(value))


class StaticManagedSecretProvider:
    def __init__(self, secrets: dict[str, str], *, provider: str = "static-managed") -> None:
        self.secrets = secrets
        self.provider = provider

    def get_secret(self, ref: SecretRef) -> ManagedSecretValue | None:
        value = self.secrets.get(ref.name)
        if value is None:
            return None
        return ManagedSecretValue(ref.name, self.provider, "1", _redact(value))

    def check(self, secrets: tuple[SecretRef, ...]) -> SecretCheckResult:
        missing = tuple(secret.name for secret in secrets if secret.required and secret.name not in self.secrets)
        return SecretCheckResult(not missing, missing, self.provider)


class ManagedSecretManager:
    def __init__(self, provider: SecretProvider) -> None:
        self.provider = provider

    def resolve(self, secrets: tuple[SecretRef, ...]) -> tuple[ManagedSecretValue, ...]:
        resolved = []
        for secret in secrets:
            value = self.provider.get_secret(secret)
            if value is not None:
                resolved.append(value)
        return tuple(resolved)

    def check(self, secrets: tuple[SecretRef, ...]) -> SecretCheckResult:
        missing = []
        for secret in secrets:
            if secret.required and self.provider.get_secret(secret) is None:
                missing.append(secret.name)
        return SecretCheckResult(not missing, tuple(missing), self.provider.provider)


class NetworkAllowlist:
    def __init__(self, allowed_hosts: set[str]) -> None:
        self.allowed_hosts = allowed_hosts

    def validate_url(self, url: str) -> HardeningResult:
        parsed = urlparse(url)
        if parsed.scheme in {"file", "offline"}:
            return HardeningResult(True, ())
        if parsed.hostname in self.allowed_hosts:
            return HardeningResult(True, ())
        return HardeningResult(False, ("host_not_allowlisted",))

    def validate_urls(self, urls: tuple[str, ...]) -> HardeningResult:
        failures = []
        for url in urls:
            result = self.validate_url(url)
            failures.extend(f"{url}:{failure}" for failure in result.failures)
        return HardeningResult(not failures, tuple(failures))


class PermissionPolicy:
    def __init__(self, roles: tuple[RolePermission, ...]) -> None:
        self.roles = {role.role: set(role.permissions) for role in roles}

    def can(self, role: str, permission: str) -> bool:
        permissions = self.roles.get(role, set())
        return permission in permissions or "*" in permissions

    def validate_required_roles(self, required_roles: tuple[str, ...]) -> HardeningResult:
        missing = tuple(role for role in required_roles if role not in self.roles)
        return HardeningResult(not missing, tuple(f"missing_role:{role}" for role in missing))


def default_permission_policy() -> PermissionPolicy:
    return PermissionPolicy(
        (
            RolePermission("admin", ("*",)),
            RolePermission("editor", ("source_pack:read", "puzzle:review", "puzzle:publish")),
            RolePermission("operator", ("batch:run", "batch:inspect", "eval:run")),
            RolePermission("viewer", ("report:read",)),
        )
    )


def validate_environment(config: EnvironmentConfig) -> HardeningResult:
    failures = []
    warnings = []
    if config.name not in {"local", "dev", "staging", "prod"}:
        failures.append("unknown_environment")
    if config.name == "prod" and config.debug:
        failures.append("prod_debug_enabled")
    if config.name in {"staging", "prod"} and not config.database_url.startswith(("postgresql://", "postgres://")):
        warnings.append("non_postgres_database_for_hosted_environment")
    if not config.allowed_hosts:
        failures.append("missing_network_allowlist")
    if config.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        failures.append("invalid_log_level")
    return HardeningResult(not failures, tuple(failures), tuple(warnings))


def validate_backup_policy(policy: BackupPolicy) -> HardeningResult:
    failures = []
    warnings = []
    if not policy.enabled:
        failures.append("backup_disabled")
    if policy.retention_days < 7:
        failures.append("retention_too_short")
    if policy.artifact_retention_days < policy.retention_days:
        warnings.append("artifact_retention_shorter_than_metadata_retention")
    if policy.restore_test_interval_days > 30:
        warnings.append("restore_tests_too_infrequent")
    return HardeningResult(not failures, tuple(failures), tuple(warnings))


def validate_disaster_recovery(plan: DisasterRecoveryPlan) -> HardeningResult:
    failures = []
    warnings = []
    if plan.rpo_minutes > 60:
        warnings.append("rpo_above_one_hour")
    if plan.rto_minutes > 240:
        warnings.append("rto_above_four_hours")
    if not plan.runbook_ref:
        failures.append("missing_dr_runbook")
    if not plan.escalation_contacts:
        failures.append("missing_escalation_contacts")
    if not plan.last_drill_at:
        warnings.append("missing_drill_record")
    return HardeningResult(not failures, tuple(failures), tuple(warnings))


def assess_production_readiness(
    *,
    environment: EnvironmentConfig,
    secrets: tuple[SecretRef, ...],
    backup_policy: BackupPolicy,
    disaster_recovery: DisasterRecoveryPlan,
    permission_policy: PermissionPolicy | None = None,
    egress_urls: tuple[str, ...] = (),
) -> ProductionReadinessReport:
    permission_policy = permission_policy or default_permission_policy()
    secret_result = EnvSecretManager(environment.secrets_provider).check(secrets)
    env_result = validate_environment(environment)
    egress_result = NetworkAllowlist(set(environment.allowed_hosts)).validate_urls(egress_urls)
    role_result = permission_policy.validate_required_roles(("admin", "editor", "operator", "viewer"))
    backup_result = validate_backup_policy(backup_policy)
    dr_result = validate_disaster_recovery(disaster_recovery)
    results = {
        "environment": env_result,
        "secrets": HardeningResult(secret_result.configured, tuple(f"missing_secret:{name}" for name in secret_result.missing)),
        "egress": egress_result,
        "roles": role_result,
        "backup": backup_result,
        "disaster_recovery": dr_result,
    }
    failures = tuple(failure for result in results.values() for failure in result.failures)
    warnings = tuple(warning for result in results.values() for warning in result.warnings)
    return ProductionReadinessReport(
        environment=environment.name,
        passed=not failures,
        failures=failures,
        warnings=warnings,
        controls={
            "environment": asdict(environment),
            "secret_provider": secret_result.provider,
            "allowed_hosts": list(environment.allowed_hosts),
            "roles": {role: sorted(perms) for role, perms in permission_policy.roles.items()},
            "backup_policy": asdict(backup_policy),
            "disaster_recovery": asdict(disaster_recovery),
        },
    )


def production_readiness_payload(report: ProductionReadinessReport) -> dict[str, object]:
    return {
        "environment": report.environment,
        "passed": report.passed,
        "failures": list(report.failures),
        "warnings": list(report.warnings),
        "controls": report.controls,
    }


def validate_deployment_manifest(
    manifest: DeploymentManifest,
    *,
    secret_manager: ManagedSecretManager | EnvSecretManager | None = None,
    permission_policy: PermissionPolicy | None = None,
) -> ProductionReadinessReport:
    secret_manager = secret_manager or EnvSecretManager(manifest.environment.secrets_provider)
    secret_result = secret_manager.check(manifest.required_secrets)
    readiness = assess_production_readiness(
        environment=manifest.environment,
        secrets=(),
        backup_policy=manifest.backup_policy,
        disaster_recovery=manifest.disaster_recovery,
        permission_policy=permission_policy,
        egress_urls=manifest.egress_urls,
    )
    failures = list(readiness.failures)
    warnings = list(readiness.warnings)
    failures.extend(f"missing_secret:{name}" for name in secret_result.missing)
    if not manifest.image_ref:
        failures.append("missing_image_ref")
    if manifest.environment.name in {"staging", "prod"} and not manifest.migration_ref:
        failures.append("missing_migration_ref")
    if not manifest.config_checksums:
        warnings.append("missing_config_checksums")
    return ProductionReadinessReport(
        environment=manifest.environment.name,
        passed=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        controls={
            **readiness.controls,
            "image_ref": manifest.image_ref,
            "migration_ref": manifest.migration_ref,
            "config_checksums": dict(manifest.config_checksums),
            "secret_provider": secret_result.provider,
        },
    )


def deployment_manifest_payload(manifest: DeploymentManifest) -> dict[str, Any]:
    return {
        "environment": asdict(manifest.environment),
        "required_secrets": [asdict(secret) for secret in manifest.required_secrets],
        "backup_policy": asdict(manifest.backup_policy),
        "disaster_recovery": asdict(manifest.disaster_recovery),
        "egress_urls": list(manifest.egress_urls),
        "image_ref": manifest.image_ref,
        "migration_ref": manifest.migration_ref,
        "config_checksums": dict(manifest.config_checksums),
    }


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:2]}****{value[-2:]}"
