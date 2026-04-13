"""Tests for .ptq/ folder discovery: loading profiles, prompts, and registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from ptq.agent import build_adhoc_prompt, build_system_prompt
from ptq.repo_profiles import load_dotptq, reset_cache

ASSETS_DIR = Path(__file__).parent / "assets"
FAKEREPO_DIR = ASSETS_DIR / "fakerepo"


class TestLoadDotptq:
    def test_loads_profile(self):
        profile = load_dotptq(FAKEREPO_DIR)
        assert profile.name == "fakerepo"
        assert profile.github_repo == "org/fakerepo"
        assert profile.smoke_test_import == "fakerepo"
        assert profile.repro_import_hint == "import fakerepo"
        assert profile.needs_cpp_build is False
        assert profile.uses_custom_worktree_tool is False
        assert profile.lint_cmd is None
        assert profile.dir_name == "fakerepo"
        assert profile.prompt_dir == FAKEREPO_DIR / ".ptq"

    def test_prompt_templates_exist(self):
        profile = load_dotptq(FAKEREPO_DIR)
        assert (profile.prompt_dir / "investigate.md").exists()
        assert (profile.prompt_dir / "adhoc.md").exists()

    def test_missing_profile_toml(self, tmp_path):
        with pytest.raises(ValueError, match="No .ptq/profile.toml found"):
            load_dotptq(tmp_path)

    def test_missing_required_fields(self, tmp_path):
        ptq_dir = tmp_path / ".ptq"
        ptq_dir.mkdir()
        (ptq_dir / "profile.toml").write_text("[profile]\nname = 'x'\n")
        (ptq_dir / "investigate.md").write_text("test")
        (ptq_dir / "adhoc.md").write_text("test")
        with pytest.raises(ValueError, match="missing required fields"):
            load_dotptq(tmp_path)

    def test_missing_prompt_files(self, tmp_path):
        ptq_dir = tmp_path / ".ptq"
        ptq_dir.mkdir()
        (ptq_dir / "profile.toml").write_text(
            '[profile]\nname = "x"\ngithub_repo = "o/x"\n'
            'smoke_test_import = "x"\nrepro_import_hint = "import x"\n'
        )
        with pytest.raises(ValueError, match="not found"):
            load_dotptq(tmp_path)

    def test_empty_lint_cmd_becomes_none(self):
        profile = load_dotptq(FAKEREPO_DIR)
        assert profile.lint_cmd is None


class TestDotptqPrompts:
    @pytest.fixture(autouse=True)
    def _inject_fakerepo(self, monkeypatch):
        """Make get_profile('fakerepo') return the test asset profile."""
        from ptq import repo_profiles

        profile = load_dotptq(FAKEREPO_DIR)
        reset_cache()
        original = repo_profiles._loaded_profiles

        def _patched():
            profiles = original()
            profiles["fakerepo"] = profile
            return profiles

        monkeypatch.setattr(repo_profiles, "_loaded_profiles", _patched)
        yield
        reset_cache()

    def test_system_prompt_uses_dotptq_template(self):
        issue_data = {
            "title": "Bug",
            "body": "crash",
            "labels": [],
            "comments": [],
        }
        result = build_system_prompt(issue_data, 42, "j-42", "/ws", repo="fakerepo")
        assert "Fakerepo" in result
        assert "j-42" in result
        assert "org/fakerepo#42" in result

    def test_adhoc_prompt_uses_dotptq_template(self):
        result = build_adhoc_prompt("fix bug", "j-99", "/ws", repo="fakerepo")
        assert "Fakerepo" in result
        assert "j-99" in result
        assert "fix bug" in result

    def test_pytorch_prompts_unchanged(self):
        issue_data = {
            "title": "Bug",
            "body": "desc",
            "labels": [],
            "comments": [],
        }
        result = build_system_prompt(issue_data, 42, "j-42", "/ws", repo="pytorch")
        assert "spin fixlint" in result

        result = build_adhoc_prompt("fix oom", "j-42", "/ws", repo="pytorch")
        assert "spin fixlint" in result


class TestRepoRegistry:
    def test_save_and_load(self, tmp_path, monkeypatch):
        from ptq.repo_profiles import (
            registered_repo_urls,
            remove_repo_registration,
            save_repo_registration,
        )

        registry_path = tmp_path / "repos.json"
        monkeypatch.setattr("ptq.repo_profiles.REPOS_REGISTRY_PATH", registry_path)

        save_repo_registration("myrepo", "https://github.com/org/myrepo.git")
        urls = registered_repo_urls()
        assert urls == {"myrepo": "https://github.com/org/myrepo.git"}

        assert remove_repo_registration("myrepo") is True
        assert registered_repo_urls() == {}

    def test_remove_nonexistent(self, tmp_path, monkeypatch):
        from ptq.repo_profiles import remove_repo_registration

        registry_path = tmp_path / "repos.json"
        monkeypatch.setattr("ptq.repo_profiles.REPOS_REGISTRY_PATH", registry_path)
        assert remove_repo_registration("nope") is False
