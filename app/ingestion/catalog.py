# ruff: noqa: E501 -- dense static catalog rows are intentionally one line
from __future__ import annotations

from app.ingestion.models import SourceDefinition

CATALOG_SNAPSHOT_DATE = "2026-08-22"
CATALOG_ORG = "eclipse-tractusx"

_COMMON_INCLUDE = [
    "README.md",
    "README.*",
    "docs/**/*.md",
    "**/*.md",
    "**/*.adoc",
    "**/*.java",
    "**/*.kt",
    "**/*.kts",
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.js",
    "**/*.jsx",
    "**/*.json",
    "**/*.jsonld",
    "**/*.yaml",
    "**/*.yml",
    "**/*.properties",
    "**/*.toml",
    "**/*.ttl",
    "**/*.graphql",
    "**/*.proto",
    "**/*.tf",
    "**/*.hcl",
    "**/*.sh",
    "Dockerfile",
    "**/Dockerfile",
]

_COMMON_EXCLUDE = [
    "**/.git/**",
    "**/.venv/**",
    "**/__pycache__/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/target/**",
    "**/coverage/**",
    "**/vendor/**",
    "**/generated/**",
    "**/gen/**",
    "**/static/**",
    "**/assets/**",
    "**/.gradle/**",
    "**/*.min.js",
    "**/package-lock.json",
    "**/yarn.lock",
    "**/pnpm-lock.yaml",
]

# repo, source_id, domain, source_type, catalog_state, enabled, priority
#
# This is a full organization snapshot excluding the six hand-tuned core sources
# that remain in config/sources.toml. Disabled repositories stay visible in
# Mission Control but are not ingested into the retrieval corpus.
_CATALOG = (
    ("digital-product-pass", "digital-product-pass", "product-pass", "application", "archived", False, "medium"),
    ("tractus-x-umbrella", "tractus-x-umbrella", "platform", "infrastructure", "active", True, "high"),
    ("industry-core-hub", "industry-core-hub", "industry-core", "application", "active", True, "high"),
    ("puris", "puris", "supply-chain", "application", "active", True, "high"),
    ("tutorial-resources", "tutorial-resources", "documentation", "documentation", "active", True, "medium"),
    ("traceability-foss", "traceability-foss", "traceability", "application", "active", True, "high"),
    ("bpdm", "bpdm", "business-partner", "application", "active", True, "high"),
    ("portal-backend", "portal-backend", "portal", "service", "active", True, "high"),
    ("sig-release", "sig-release", "governance", "governance", "active", True, "medium"),
    ("tractusx-identityhub", "tractusx-identityhub", "identity", "service", "active", True, "high"),
    ("managed-identity-wallet", "managed-identity-wallet", "identity", "service", "archived", False, "low"),
    ("portal-frontend", "portal-frontend", "portal", "application", "active", True, "medium"),
    ("item-relationship-service", "item-relationship-service", "traceability", "service", "active", True, "high"),
    ("portal-assets", "portal-assets", "portal", "asset", "active", False, "low"),
    ("ssi-dim-wallet-stub", "ssi-dim-wallet-stub", "identity", "test", "active", False, "low"),
    ("portal", "portal", "portal", "documentation", "active", True, "medium"),
    ("sldt-semantic-hub", "sldt-semantic-hub", "semantics", "service", "active", True, "high"),
    ("managed-service-orchestrator", "managed-service-orchestrator", "managed-services", "service", "active", True, "medium"),
    ("sig-architecture", "sig-architecture", "architecture", "governance", "active", True, "high"),
    ("portal-frontend-registration", "portal-frontend-registration", "portal", "application", "active", True, "medium"),
    ("demand-capacity-mgmt", "demand-capacity-mgmt", "supply-chain", "application", "archived", False, "low"),
    ("ssi-credential-issuer", "ssi-credential-issuer", "identity", "service", "active", True, "high"),
    ("policy-hub", "policy-hub", "policy", "service", "archived", False, "low"),
    ("SSI-agent-lib", "ssi-agent-lib", "identity", "library", "archived", False, "low"),
    ("ssi-authority-schema-registry", "ssi-authority-schema-registry", "identity", "service", "archived", False, "low"),
    ("bpn-did-resolution-service", "bpn-did-resolution-service", "identity", "service", "active", True, "high"),
    ("managed-simple-data-exchanger-backend", "managed-simple-data-exchanger-backend", "data-exchange", "service", "active", True, "high"),
    ("sldt-discovery-finder", "sldt-discovery-finder", "discovery", "service", "active", True, "high"),
    ("knowledge-agents-edc", "knowledge-agents-edc", "knowledge-agents", "service", "active", True, "high"),
    ("charts", "charts", "deployment", "infrastructure", "active", True, "high"),
    ("tractusx-edc-kafka-extension", "tractusx-edc-kafka-extension", "data-exchange", "extension", "active", True, "medium"),
    ("tractusx-sdk-services", "tractusx-sdk-services", "sdk", "service", "active", True, "high"),
    ("sig-infra", "sig-infra", "infrastructure", "governance", "active", True, "medium"),
    ("ssi-docu", "ssi-docu", "identity", "documentation", "archived", False, "low"),
    ("aas-suite", "aas-suite", "digital-twin", "application", "active", True, "medium"),
    ("portal-iam", "portal-iam", "identity", "service", "active", True, "high"),
    ("portal-shared-components", "portal-shared-components", "portal", "library", "active", True, "medium"),
    ("vas-country-risk", "vas-country-risk", "value-added-services", "application", "archived", False, "low"),
    ("vas-country-risk-backend", "vas-country-risk-backend", "value-added-services", "service", "archived", False, "low"),
    ("managed-simple-data-exchanger-frontend", "managed-simple-data-exchanger-frontend", "data-exchange", "application", "active", True, "medium"),
    ("sldt-bpn-discovery", "sldt-bpn-discovery", "discovery", "service", "active", True, "high"),
    ("tractusx-edc-template", "tractusx-edc-template", "data-exchange", "template", "archived", False, "low"),
    ("traceability-foss-backend", "traceability-foss-backend", "traceability", "service", "archived", False, "low"),
    ("sd-factory", "sd-factory", "service-discovery", "service", "active", True, "medium"),
    ("tractusx-testlab", "tractusx-testlab", "testing", "test", "active", True, "medium"),
    ("eco-pass-kit", "eco-pass-kit", "product-pass", "application", "archived", False, "low"),
    ("emergingtechnologies", "emergingtechnologies", "research", "documentation", "archived", False, "low"),
    ("tractusx-edc-dashboard", "tractusx-edc-dashboard", "data-exchange", "application", "active", True, "medium"),
    ("tractusx-profiles", "tractusx-profiles", "identity", "configuration", "active", True, "high"),
    ("eclipse-tractusx.github.io.largefiles", "eclipse-tractusx.github.io.largefiles", "documentation", "asset", "active", False, "low"),
    ("api-hub", "api-hub", "api", "application", "active", True, "high"),
    ("tractusx-quality-checks", "tractusx-quality-checks", "quality", "tooling", "archived", False, "low"),
    ("managed-identity-wallets-archived", "managed-identity-wallets-archived", "identity", "legacy", "archived", False, "low"),
    ("data-exchange-test-service", "data-exchange-test-service", "data-exchange", "test", "active", False, "low"),
    ("sldt-ontology-model", "sldt-ontology-model", "semantics", "model", "active", True, "high"),
    ("knowledge-agents-aas-bridge", "knowledge-agents-aas-bridge", "knowledge-agents", "service", "active", True, "high"),
    ("app-dashboard", "app-dashboard", "portal", "application", "active", True, "low"),
    ("knowledge-agents", "knowledge-agents", "knowledge-agents", "application", "active", True, "high"),
    ("bpdm-certificate-management", "bpdm-certificate-management", "business-partner", "service", "archived", False, "low"),
    (".eclipsefdn", "eclipsefdn-meta", "governance", "meta", "meta", False, "low"),
    ("managed-simple-data-exchanger", "managed-simple-data-exchanger", "data-exchange", "documentation", "active", True, "medium"),
    ("tractusx-issuerservice", "tractusx-issuerservice", "identity", "service", "archived", False, "low"),
    ("tractusx-edc-compatibility-tests", "tractusx-edc-compatibility-tests", "data-exchange", "test", "archived", False, "low"),
    ("puris-frontend", "puris-frontend", "supply-chain", "application", "archived", False, "low"),
    ("daps-registration-service", "daps-registration-service", "identity", "service", "archived", False, "low"),
    ("puris-backend", "puris-backend", "supply-chain", "service", "archived", False, "low"),
    ("engineering-use-case-demonstrator", "engineering-use-case-demonstrator", "engineering", "application", "active", True, "high"),
    (".github", "github-meta", "governance", "meta", "meta", False, "low"),
    ("tractusx-virtual-connector", "tractusx-virtual-connector", "data-exchange", "service", "empty", False, "low"),
    ("bpdm-upload-tool", "bpdm-upload-tool", "business-partner", "tooling", "archived", False, "low"),
    ("daps-helm-chart", "daps-helm-chart", "identity", "infrastructure", "archived", False, "low"),
    ("tractus-x-umbrella-iac", "tractus-x-umbrella-iac", "infrastructure", "infrastructure", "active", True, "high"),
    ("testdata-provider", "testdata-provider", "testing", "test", "active", False, "low"),
    ("sig-security", "sig-security", "security", "governance", "active", True, "high"),
)


def catalog_sources(existing_ids: set[str] | None = None) -> list[SourceDefinition]:
    existing = existing_ids or set()
    result: list[SourceDefinition] = []
    for repo, source_id, domain, source_type, state, enabled, priority in _CATALOG:
        if source_id in existing:
            continue
        result.append(
            SourceDefinition(
                id=source_id,
                owner=CATALOG_ORG,
                repo=repo,
                component=repo.lstrip("."),
                domain=domain,
                source_type=source_type,
                catalog_state=state,
                priority=priority,
                ref="main",
                enabled=enabled,
                allow_archived=False,
                max_file_bytes=1_000_000,
                include=list(_COMMON_INCLUDE),
                exclude=list(_COMMON_EXCLUDE),
            )
        )
    return result


def catalog_summary() -> dict[str, int | str]:
    enabled = sum(1 for item in _CATALOG if item[5])
    return {
        "snapshot_date": CATALOG_SNAPSHOT_DATE,
        "catalog_entries": len(_CATALOG) + 6,
        "enabled_entries": enabled + 6,
    }
