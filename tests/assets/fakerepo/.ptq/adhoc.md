# Fakerepo Task Agent

You are performing a task on a fakerepo codebase.

## Job Info
- **Job ID**: {job_id}
- **Mode**: adhoc

## Environment
- **Python**: `{workspace}/jobs/{job_id}/.venv/bin/python`
- **Source** (edit here): `{workspace}/jobs/{job_id}/fakerepo/`
- **Job artifacts**: `{workspace}/jobs/{job_id}/`

## Task

{task_description}

## Output
Write `report.md` to `{workspace}/jobs/{job_id}/`.
