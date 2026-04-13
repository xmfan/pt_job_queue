from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import tomllib

log = logging.getLogger("ptq.repo_profiles")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
REPOS_REGISTRY_PATH = Path.home() / ".ptq" / "repos.json"

# Placeholder contract for .ptq/ prompt templates:
#   investigate.md uses: {workspace}, {job_id}, {issue_number}, {issue_context}
#   adhoc.md uses: {workspace}, {job_id}, {task_description}


@dataclass(frozen=True)
class RepoProfile:
    name: str
    github_repo: str
    clone_url: str
    dir_name: str
    smoke_test_import: str
    repro_import_hint: str
    uses_custom_worktree_tool: bool
    needs_cpp_build: bool
    lint_cmd: str | None
    prompt_template: str
    adhoc_prompt_template: str
    install_cmd: str | None = None
    prompt_dir: Path | None = None


def _resolve_prompt_templates(name: str) -> tuple[str, str]:
    """Derive prompt filenames by convention, with pytorch backward compat."""
    if name == "pytorch":
        return "investigate.md", "adhoc.md"
    return f"investigate_{name}.md", f"adhoc_{name}.md"


def _validate_prompt_templates(profile: RepoProfile) -> None:
    if profile.prompt_dir is not None:
        for filename in ("investigate.md", "adhoc.md"):
            path = profile.prompt_dir / filename
            if not path.exists():
                raise ValueError(
                    f"Prompt template '{filename}' not found at {path}. "
                    f"Create it in the repo's .ptq/ directory."
                )
        return
    for attr in ("prompt_template", "adhoc_prompt_template"):
        filename = getattr(profile, attr)
        path = PROMPTS_DIR / filename
        if not path.exists():
            raise ValueError(
                f"Prompt template '{filename}' not found at {path}. "
                f"Create it to use the '{profile.name}' repo profile."
            )


# Built-in defaults — only pytorch. Other repos self-describe via .ptq/.
_DEFAULT_PROFILES: dict[str, RepoProfile] = {
    "pytorch": RepoProfile(
        name="pytorch",
        github_repo="pytorch/pytorch",
        clone_url="https://github.com/pytorch/pytorch.git",
        dir_name="pytorch",
        smoke_test_import="torch",
        repro_import_hint="import torch",
        uses_custom_worktree_tool=True,
        needs_cpp_build=True,
        lint_cmd="spin fixlint",
        prompt_template="investigate.md",
        adhoc_prompt_template="adhoc.md",
    ),
}


def load_dotptq(repo_dir: Path) -> RepoProfile:
    """Load a RepoProfile from a repo's .ptq/ directory."""
    ptq_dir = repo_dir / ".ptq"
    profile_path = ptq_dir / "profile.toml"
    if not profile_path.exists():
        raise ValueError(
            f"No .ptq/profile.toml found in {repo_dir}. "
            f"The repo must contain a .ptq/ directory with profile.toml."
        )
    data = tomllib.loads(profile_path.read_text())
    p = data.get("profile", {})

    required = ("name", "github_repo", "smoke_test_import", "repro_import_hint")
    missing = [f for f in required if not p.get(f)]
    if missing:
        raise ValueError(
            f".ptq/profile.toml in {repo_dir} missing required fields: {', '.join(missing)}"
        )

    name = p["name"]
    profile = RepoProfile(
        name=name,
        github_repo=p["github_repo"],
        clone_url=p.get("clone_url", ""),
        dir_name=p.get("dir_name", name),
        smoke_test_import=p["smoke_test_import"],
        repro_import_hint=p["repro_import_hint"],
        uses_custom_worktree_tool=p.get("uses_custom_worktree", False),
        needs_cpp_build=p.get("needs_cpp_build", False),
        lint_cmd=p.get("lint_cmd") or None,
        install_cmd=p.get("install_cmd") or None,
        prompt_template="investigate.md",
        adhoc_prompt_template="adhoc.md",
        prompt_dir=ptq_dir,
    )
    _validate_prompt_templates(profile)
    return profile


def load_profiles_from_config(repos_section: dict) -> dict[str, RepoProfile]:
    """Parse [repos.*] TOML sections into RepoProfile instances."""
    profiles: dict[str, RepoProfile] = {}
    for name, data in repos_section.items():
        if not isinstance(data, dict):
            continue
        investigate, adhoc = _resolve_prompt_templates(name)
        profiles[name] = RepoProfile(
            name=name,
            github_repo=data["github_repo"],
            clone_url=data["clone_url"],
            dir_name=data.get("dir_name", name),
            smoke_test_import=data["smoke_test_import"],
            repro_import_hint=data["repro_import_hint"],
            uses_custom_worktree_tool=data.get("uses_custom_worktree_tool", False),
            needs_cpp_build=data.get("needs_cpp_build", False),
            lint_cmd=data.get("lint_cmd"),
            install_cmd=data.get("install_cmd"),
            prompt_template=data.get("prompt_template", investigate),
            adhoc_prompt_template=data.get("adhoc_prompt_template", adhoc),
        )
    for profile in profiles.values():
        _validate_prompt_templates(profile)
    return profiles


def load_registered_repos() -> dict[str, RepoProfile]:
    """Load repos registered via `ptq repo add` from ~/.ptq/repos.json.

    The registry stores the full profile data from .ptq/profile.toml so
    profiles can be loaded without needing a local clone of the repo.
    """
    if not REPOS_REGISTRY_PATH.exists():
        return {}
    try:
        registry = json.loads(REPOS_REGISTRY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    profiles: dict[str, RepoProfile] = {}
    for name, entry in registry.items():
        # Support both old format (str clone_url) and new format (dict)
        if isinstance(entry, str):
            log.warning(
                "Registry entry for '%s' is in old format (URL only). "
                "Re-run 'ptq repo add' to update it.",
                name,
            )
            continue
        p = entry.get("profile", {})
        # Prompt templates are cached locally at ~/.ptq/prompts/{name}/
        local_prompt_dir = Path.home() / ".ptq" / "prompts" / name
        prompt_dir = local_prompt_dir if local_prompt_dir.exists() else None
        profiles[name] = RepoProfile(
            name=name,
            github_repo=p.get("github_repo", ""),
            clone_url=entry.get("clone_url", ""),
            dir_name=p.get("dir_name", name),
            smoke_test_import=p.get("smoke_test_import", name),
            repro_import_hint=p.get("repro_import_hint", f"import {name}"),
            uses_custom_worktree_tool=p.get("uses_custom_worktree", False),
            needs_cpp_build=p.get("needs_cpp_build", False),
            lint_cmd=p.get("lint_cmd") or None,
            install_cmd=p.get("install_cmd") or None,
            prompt_template="investigate.md",
            adhoc_prompt_template="adhoc.md",
            prompt_dir=prompt_dir,
        )
    return profiles


def save_repo_registration(name: str, clone_url: str, profile_data: dict | None = None) -> None:
    """Add a repo to the persistent registry (~/.ptq/repos.json).

    Stores clone_url and the parsed profile.toml data so the profile
    can be loaded without a local clone.
    """
    registry: dict = {}
    if REPOS_REGISTRY_PATH.exists():
        try:
            registry = json.loads(REPOS_REGISTRY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    registry[name] = {
        "clone_url": clone_url,
        "profile": profile_data or {},
    }
    REPOS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPOS_REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def remove_repo_registration(name: str) -> bool:
    """Remove a repo from the persistent registry. Returns True if it was present."""
    if not REPOS_REGISTRY_PATH.exists():
        return False
    try:
        registry = json.loads(REPOS_REGISTRY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    if name not in registry:
        return False
    del registry[name]
    REPOS_REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    return True


def registered_repo_urls() -> dict[str, str]:
    """Return {name: clone_url} from the registry file."""
    if not REPOS_REGISTRY_PATH.exists():
        return {}
    try:
        registry = json.loads(REPOS_REGISTRY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    result: dict[str, str] = {}
    for name, entry in registry.items():
        if isinstance(entry, str):
            result[name] = entry
        elif isinstance(entry, dict):
            result[name] = entry.get("clone_url", "")
    return result


_profiles_cache: dict[str, RepoProfile] | None = None


def _loaded_profiles() -> dict[str, RepoProfile]:
    global _profiles_cache
    if _profiles_cache is None:
        from ptq.config import load_config

        cfg = load_config()
        # Start with TOML-configured repos (pytorch)
        if cfg.repos:
            _profiles_cache = dict(cfg.repos)
        else:
            _profiles_cache = dict(_DEFAULT_PROFILES)
        # Layer on repos registered via `ptq repo add` (.ptq/ discovery)
        _profiles_cache.update(load_registered_repos())
    return _profiles_cache


def get_profile(name: str) -> RepoProfile:
    profiles = _loaded_profiles()
    profile = profiles.get(name)
    if profile is None:
        raise ValueError(
            f"Unknown repo '{name}'. Available: {', '.join(profiles)}"
        )
    return profile


def available_repos() -> list[str]:
    return list(_loaded_profiles())


def reset_cache() -> None:
    """Clear cached profiles (for testing)."""
    global _profiles_cache
    _profiles_cache = None
