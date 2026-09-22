"""Vocabulary shared by the agents, the validators and the API responses."""

SUPPORTED_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

SEVERITY_ORDER = {severity: index for index, severity in enumerate(SUPPORTED_SEVERITIES)}

SUPPORTED_CATEGORIES = [
    "SECURITY",
    "QUALITY",
    "PERFORMANCE",
    "TESTING",
    "ARCHITECTURE",
    "INTEGRATION",
]

# Severity aliases the models reach for even when told not to.
SEVERITY_ALIASES = {
    "INFO": "LOW",
    "INFORMATIONAL": "LOW",
    "MINOR": "LOW",
    "TRIVIAL": "LOW",
    "NOTE": "LOW",
    "WARNING": "MEDIUM",
    "MODERATE": "MEDIUM",
    "ERROR": "HIGH",
    "MAJOR": "HIGH",
    "SEVERE": "HIGH",
    "BLOCKER": "CRITICAL",
    "FATAL": "CRITICAL",
}

CATEGORY_ALIASES = {
    "PERF": "PERFORMANCE",
    "EFFICIENCY": "PERFORMANCE",
    "TEST": "TESTING",
    "TESTS": "TESTING",
    "DESIGN": "ARCHITECTURE",
    "COMPATIBILITY": "INTEGRATION",
    "DEPENDENCY": "INTEGRATION",
    "DEPENDENCIES": "INTEGRATION",
    "MIGRATION": "INTEGRATION",
}

DEFAULT_TEMPERATURE = 0.2

# Keys of the per-category issue buckets carried through the graph state.
ISSUE_BUCKETS = (
    "security_issues",
    "quality_issues",
    "performance_issues",
    "testing_issues",
    "architecture_issues",
    "integration_issues",
)
