from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger("skill_loader")


@dataclass
class SkillMeta:
    key: str
    name: str
    description: str
    tool_budget: int
    section_name: str | None    # None for scoring, alternatives, conversation
    instructions: str           # full markdown body, injected into system prompt


def load_skill(path: Path) -> SkillMeta | None:
    """Parse a SKILL.md file.

    Returns a SkillMeta if the file is valid, or None if it should be skipped.
    Logs a warning for every skipped file — silent failures are not acceptable.

    The file must begin with a YAML frontmatter block delimited by '---'.
    Any content after the second '---' is treated as the markdown body.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_loader | cannot read %s: %s", path, exc)
        return None
    
    raw = raw.replace("\r\n", "\n")  # Normalize line endings before splitting


    # Split on frontmatter delimiters.
    # A valid file looks like: "---\n<yaml>\n---\n<body>"
    # Split into at most 3 parts: ["", yaml_block, body]
    parts = raw.split("---", maxsplit=2)
    if len(parts) < 3:
        logger.warning(
            "skill_loader | %s: missing frontmatter delimiters — skipping", path
        )
        return None

    yaml_block = parts[1].strip()
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        logger.warning("skill_loader | %s: YAML parse error: %s — skipping", path, exc)
        return None

    if not isinstance(meta, dict):
        logger.warning("skill_loader | %s: frontmatter is not a mapping — skipping", path)
        return None

    # Validate required fields.
    required = ("key", "name", "description", "tool_budget")
    missing = [f for f in required if f not in meta or meta[f] is None]    
    if missing:
        logger.warning(
            "skill_loader | %s: missing required fields %s — skipping", path, missing
        )
        return None

    try:
        tool_budget = int(meta["tool_budget"])
    except (TypeError, ValueError):
        logger.warning(
            "skill_loader | %s: tool_budget must be an integer — skipping", path
        )
        return None

    skill = SkillMeta(
        key=str(meta["key"]).lower(),
        name=str(meta["name"]),
        description=str(meta["description"]),
        tool_budget=tool_budget,
        section_name=meta.get("section_name") or None,
        instructions=body,
    )
    logger.info("skill_loader | loaded %s", path)
    return skill


def scan_skills_dir(skills_dir: Path) -> dict[str, SkillMeta]:
    """Scan the skills/ directory and return all valid SkillMeta entries.

    Each immediate subdirectory of skills_dir is expected to contain a SKILL.md.
    Subdirectories without a SKILL.md are silently skipped.

    Returns a dict keyed by skill.key. Duplicate keys emit a warning; the first
    entry found wins.
    """
    result: dict[str, SkillMeta] = {}

    if not skills_dir.is_dir():
        logger.warning(
            "skill_loader | skills dir %s does not exist — no skills loaded", skills_dir
        )
        return result

    for subdir in sorted(skills_dir.iterdir()):
        if not subdir.is_dir():
            continue
        skill_file = subdir / "SKILL.md"
        if not skill_file.exists():
            continue
        skill = load_skill(skill_file)
        if skill is None:
            continue
        if skill.key in result:
            logger.warning(
                "skill_loader | duplicate key %r in %s — first entry wins",
                skill.key, skill_file,
            )
            continue
        result[skill.key] = skill

    return result