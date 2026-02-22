from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterable


DEFAULT_MAX_DETAILED_READS = 3

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "by",
    "do",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "use",
    "when",
    "with",
    "you",
}

INTENT_TOKEN_ALIASES = {
    "deployment": (
        "deploy",
        "deployment",
        "release",
        "production",
        "pipeline",
        "上線",
        "部署",
        "正式環境",
        "發版",
    ),
    "planning": (
        "plan",
        "planning",
        "implement",
        "implementation",
        "how to",
        "規劃",
        "實作",
        "怎麼做",
    ),
    "environment": (
        "setup",
        "dependency",
        "dependencies",
        "module not found",
        "venv",
        "docker",
        "依賴",
        "安裝套件",
    ),
    "debugging": (
        "debug",
        "error",
        "exception",
        "crash",
        "bug",
        "錯誤",
        "當機",
        "除錯",
    ),
    "review": (
        "review",
        "feedback",
        "comment",
        "審查",
        "回饋",
        "建議",
    ),
    "evaluation": (
        "evaluate",
        "evaluation",
        "benchmark",
        "metrics",
        "評估",
        "分析結果",
        "比較實驗",
    ),
}


@dataclass
class SkillDefinition:
    identifier: str
    display_name: str
    description: str
    triggers: list[str]
    path: Path
    source_directory: Path
    aliases: set[str]
    keywords: set[str]
    details_loaded: bool = False

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "display_name": self.display_name,
            "description": self.description,
            "triggers": self.triggers,
            "path": str(self.path),
            "source_directory": str(self.source_directory),
            "aliases": sorted(self.aliases),
        }


@dataclass
class RouteHint:
    label: str
    skill_refs: list[str]
    keywords: set[str]


@dataclass
class ScheduleDecision:
    skill: SkillDefinition
    score: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill.identifier,
            "display_name": self.skill.display_name,
            "score": self.score,
            "reasons": self.reasons,
            "path": str(self.skill.path),
        }


@dataclass
class LoadReport:
    total_skills: int
    scanned_directories: dict[str, int]
    missing_directories: list[str]
    route_hints: int

    def to_dict(self) -> dict:
        return {
            "total_skills": self.total_skills,
            "scanned_directories": self.scanned_directories,
            "missing_directories": self.missing_directories,
            "route_hints": self.route_hints,
        }


@dataclass
class ScheduleDiagnostics:
    max_detailed_reads: int
    detailed_reads_used: int = 0
    initial_ranked_candidates: int = 0
    initial_unread_due_to_limit: int = 0
    second_pass_ranked_candidates: int = 0
    second_pass_unread_due_to_limit: int = 0
    skipped_skill_ids: list[str] = field(default_factory=list)
    second_pass_used: bool = False

    def to_dict(self) -> dict:
        skipped_total = self.initial_unread_due_to_limit + self.second_pass_unread_due_to_limit
        return {
            "max_detailed_reads": self.max_detailed_reads,
            "detailed_reads_used": self.detailed_reads_used,
            "initial_ranked_candidates": self.initial_ranked_candidates,
            "initial_unread_due_to_limit": self.initial_unread_due_to_limit,
            "second_pass_used": self.second_pass_used,
            "second_pass_ranked_candidates": self.second_pass_ranked_candidates,
            "second_pass_unread_due_to_limit": self.second_pass_unread_due_to_limit,
            "skipped_due_to_limit_total": skipped_total,
            "guardrail_triggered": skipped_total > 0,
            "sample_skipped_skill_ids": self.skipped_skill_ids,
        }


class SkillScheduler:
    def __init__(
        self,
        skill_directories: Iterable[Path],
        global_rule_files: Iterable[Path] | None = None,
        max_detailed_reads: int = DEFAULT_MAX_DETAILED_READS,
    ) -> None:
        self.skill_directories = [Path(path) for path in skill_directories]
        self.global_rule_files = [Path(path) for path in (global_rule_files or [])]
        self.max_detailed_reads = max(1, int(max_detailed_reads))
        self.skills: list[SkillDefinition] = []
        self.route_hints: list[RouteHint] = []
        self.last_schedule_diagnostics: ScheduleDiagnostics = ScheduleDiagnostics(
            max_detailed_reads=self.max_detailed_reads
        )
        self._loaded = False

    def load(self) -> LoadReport:
        self.skills = []
        self.route_hints = []

        scanned_directories: dict[str, int] = {}
        missing_directories: list[str] = []

        for directory in self.skill_directories:
            if not directory.exists():
                missing_directories.append(str(directory))
                scanned_directories[str(directory)] = 0
                continue

            files = sorted(
                path
                for path in directory.rglob("*")
                if path.is_file() and path.name.lower() == "skill.md"
            )
            scanned_directories[str(directory)] = len(files)

            for skill_file in files:
                skill = self._parse_skill_index(skill_file, directory)
                if skill:
                    self.skills.append(skill)

        for global_rule_file in self.global_rule_files:
            if global_rule_file.exists():
                self.route_hints.extend(self._parse_global_rules(global_rule_file))

        self._loaded = True
        return LoadReport(
            total_skills=len(self.skills),
            scanned_directories=scanned_directories,
            missing_directories=missing_directories,
            route_hints=len(self.route_hints),
        )

    def schedule(self, task_text: str, top_n: int = 5) -> list[ScheduleDecision]:
        if not self._loaded:
            self.load()

        if not task_text.strip():
            self.last_schedule_diagnostics = ScheduleDiagnostics(
                max_detailed_reads=self.max_detailed_reads
            )
            return []

        query = task_text.lower()
        normalized_query = _normalize_phrase(task_text)
        query_tokens = _tokenize(task_text)
        decisions: list[ScheduleDecision] = []
        preliminary: list[ScheduleDecision] = []
        read_budget = self.max_detailed_reads
        diagnostics = ScheduleDiagnostics(max_detailed_reads=self.max_detailed_reads)

        for skill in self.skills:
            score = 0
            reasons: list[str] = []

            alias_hits = sorted(
                alias for alias in skill.aliases if len(alias) >= 3 and alias in query
            )
            if alias_hits:
                score += 80
                reasons.append(f"task mentions `{alias_hits[0]}`")

            keyword_overlap = sorted(query_tokens & skill.keywords)
            if keyword_overlap:
                score += min(40, len(keyword_overlap) * 4)
                reasons.append(
                    f"keyword overlap: {', '.join(keyword_overlap[:4])}"
                )

            for hint in self.route_hints:
                if not (query_tokens & hint.keywords):
                    continue
                if any(self._ref_matches_skill(ref, skill) for ref in hint.skill_refs):
                    score += 35
                    reasons.append(f"global rule: {hint.label}")
                    break

            if score > 0:
                preliminary.append(ScheduleDecision(skill=skill, score=score, reasons=reasons))

        preliminary.sort(key=lambda item: (-item.score, item.skill.identifier))
        diagnostics.initial_ranked_candidates = len(preliminary)

        for candidate in preliminary:
            score = candidate.score
            reasons = list(candidate.reasons)
            if read_budget > 0:
                loaded_now = self._load_skill_details(candidate.skill)
                if loaded_now:
                    read_budget -= 1
                    diagnostics.detailed_reads_used += 1

                trigger_hits: list[str] = []
                for trigger in candidate.skill.triggers:
                    normalized_trigger = _normalize_phrase(trigger)
                    if len(normalized_trigger) >= 2 and normalized_trigger in normalized_query:
                        trigger_hits.append(trigger)
                if trigger_hits:
                    score += min(75, len(trigger_hits) * 25)
                    reasons.append(f"trigger match: {trigger_hits[0]}")
            elif not candidate.skill.details_loaded:
                diagnostics.initial_unread_due_to_limit += 1
                if len(diagnostics.skipped_skill_ids) < 8:
                    diagnostics.skipped_skill_ids.append(candidate.skill.identifier)

            decisions.append(
                ScheduleDecision(skill=candidate.skill, score=score, reasons=reasons)
            )

        decisions.sort(key=lambda item: (-item.score, item.skill.identifier))
        if decisions:
            self.last_schedule_diagnostics = diagnostics
            return decisions[:top_n]

        # Second pass: only if no indexed metadata matched.
        diagnostics.second_pass_used = True
        trigger_only_decisions, second_pass_stats = self._trigger_only_second_pass(
            task_text=task_text,
            top_n=top_n,
            read_budget=read_budget,
        )
        diagnostics.second_pass_ranked_candidates = second_pass_stats["ranked_candidates"]
        diagnostics.second_pass_unread_due_to_limit = second_pass_stats["unread_due_to_limit"]
        diagnostics.detailed_reads_used += second_pass_stats["reads_used"]
        for skill_id in second_pass_stats["skipped_skill_ids"]:
            if len(diagnostics.skipped_skill_ids) >= 8:
                break
            if skill_id not in diagnostics.skipped_skill_ids:
                diagnostics.skipped_skill_ids.append(skill_id)

        self.last_schedule_diagnostics = diagnostics
        if trigger_only_decisions:
            return trigger_only_decisions

        return self._fallback_decisions(top_n=top_n)

    def get_last_schedule_diagnostics(self) -> dict:
        return self.last_schedule_diagnostics.to_dict()

    def _fallback_decisions(self, top_n: int) -> list[ScheduleDecision]:
        defaults = ("planning-implementation", "planning", "managing-environment")
        fallback: list[ScheduleDecision] = []
        selected_identifiers: set[str] = set()
        for name in defaults:
            for skill in self.skills:
                if name in skill.aliases:
                    if skill.identifier in selected_identifiers:
                        break
                    selected_identifiers.add(skill.identifier)
                    fallback.append(
                        ScheduleDecision(
                            skill=skill,
                            score=1,
                            reasons=["fallback default for ambiguous task"],
                        )
                    )
                    break
        return fallback[:top_n]

    def _parse_skill_index(self, skill_file: Path, source_directory: Path) -> SkillDefinition | None:
        try:
            content_head = _read_head(skill_file, max_chars=10000)
        except OSError:
            return None

        frontmatter = _parse_frontmatter(content_head)
        identifier = _normalize_phrase(frontmatter.get("name", "")) or skill_file.parent.name.lower()
        display_name = frontmatter.get("name", skill_file.parent.name).strip()
        description = frontmatter.get("description", "").strip()
        triggers: list[str] = []

        aliases = {
            identifier,
            _normalize_phrase(skill_file.parent.name),
            _normalize_phrase(display_name),
        }
        aliases = {alias for alias in aliases if alias}

        keywords = _tokenize(" ".join([identifier, display_name, description, *triggers]))
        return SkillDefinition(
            identifier=identifier,
            display_name=display_name,
            description=description,
            triggers=triggers,
            path=skill_file,
            source_directory=source_directory,
            aliases=aliases,
            keywords=keywords,
            details_loaded=False,
        )

    def _load_skill_details(self, skill: SkillDefinition) -> bool:
        if skill.details_loaded:
            return False
        try:
            content = skill.path.read_text(encoding="utf-8")
        except OSError:
            skill.details_loaded = True
            return False

        triggers = _extract_triggers(content)
        skill.triggers = triggers
        skill.keywords |= _tokenize(" ".join(triggers))
        skill.details_loaded = True
        return True

    def _trigger_only_second_pass(
        self,
        task_text: str,
        top_n: int,
        read_budget: int,
    ) -> tuple[list[ScheduleDecision], dict]:
        stats = {
            "ranked_candidates": 0,
            "unread_due_to_limit": 0,
            "reads_used": 0,
            "skipped_skill_ids": [],
        }
        normalized_query = _normalize_phrase(task_text)
        if not normalized_query:
            return [], stats

        if read_budget <= 0:
            return [], stats

        query_tokens = _tokenize(task_text)
        decisions: list[ScheduleDecision] = []
        candidates = self._rank_second_pass_candidates(
            query=normalized_query,
            query_tokens=query_tokens,
        )
        stats["ranked_candidates"] = len(candidates)
        for skill in candidates:
            if read_budget <= 0:
                remaining = [item for item in candidates if not item.details_loaded]
                stats["unread_due_to_limit"] = len(remaining)
                stats["skipped_skill_ids"] = [item.identifier for item in remaining[:8]]
                break
            loaded_now = self._load_skill_details(skill)
            if loaded_now:
                read_budget -= 1
                stats["reads_used"] += 1
            trigger_hits: list[str] = []
            for trigger in skill.triggers:
                normalized_trigger = _normalize_phrase(trigger)
                if len(normalized_trigger) >= 2 and normalized_trigger in normalized_query:
                    trigger_hits.append(trigger)

            if not trigger_hits:
                continue

            score = min(75, len(trigger_hits) * 25)
            decisions.append(
                ScheduleDecision(
                    skill=skill,
                    score=score,
                    reasons=[f"trigger match (second pass): {trigger_hits[0]}"],
                )
            )

        decisions.sort(key=lambda item: (-item.score, item.skill.identifier))
        return decisions[:top_n], stats

    def _rank_second_pass_candidates(
        self,
        query: str,
        query_tokens: set[str],
    ) -> list[SkillDefinition]:
        ranked: list[tuple[int, SkillDefinition]] = []
        for skill in self.skills:
            alias_score = 0
            for alias in skill.aliases:
                if len(alias) < 2:
                    continue
                if alias in query:
                    alias_score += 20
            keyword_overlap = len(query_tokens & skill.keywords)
            score = alias_score + (keyword_overlap * 5)
            ranked.append((score, skill))

        ranked.sort(key=lambda item: (-item[0], item[1].identifier))
        return [skill for _, skill in ranked]

    def _parse_global_rules(self, global_rule_file: Path) -> list[RouteHint]:
        hints: list[RouteHint] = []
        try:
            lines = global_rule_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return hints

        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("-"):
                continue

            refs = [ref.strip().lower() for ref in re.findall(r"`([^`]+)`", stripped)]
            if not refs:
                continue

            left_side = re.split(r"→|->", stripped, maxsplit=1)[0]
            label = _strip_markdown(left_side.lstrip("- ").strip())
            keywords = _tokenize(label)
            if not keywords:
                keywords = _tokenize(stripped)

            hints.append(RouteHint(label=label, skill_refs=refs, keywords=keywords))
        return hints

    @staticmethod
    def _ref_matches_skill(ref: str, skill: SkillDefinition) -> bool:
        normalized_ref = _normalize_phrase(ref)
        if not normalized_ref:
            return False
        if normalized_ref in skill.aliases:
            return True
        if any(normalized_ref in alias or alias in normalized_ref for alias in skill.aliases):
            return True
        return normalized_ref == skill.identifier


def build_default_scheduler(
    repo_root: Path | None = None,
    max_detailed_reads: int = DEFAULT_MAX_DETAILED_READS,
) -> SkillScheduler:
    root = repo_root or Path.cwd()
    return SkillScheduler(
        skill_directories=[root / "skills", root / "my-agent-skills"],
        global_rule_files=[root / "my-agent-skills" / "global-rules.md"],
        max_detailed_reads=max_detailed_reads,
    )


def _parse_frontmatter(content: str) -> dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}

    frontmatter: dict[str, str] = {}
    for raw_line in lines[1:end_index]:
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("'\"")
    return frontmatter


def _read_head(path: Path, max_chars: int = 10000) -> str:
    with path.open("r", encoding="utf-8") as file:
        return file.read(max_chars)


def _extract_triggers(content: str) -> list[str]:
    lines = content.splitlines()
    start_index = None
    for index, line in enumerate(lines):
        if re.match(r"^##\s+when to use this skill\s*$", line.strip(), flags=re.IGNORECASE):
            start_index = index + 1
            break

    if start_index is None:
        return []

    triggers: list[str] = []
    for line in lines[start_index:]:
        stripped = line.strip()
        if re.match(r"^##\s+", stripped):
            break

        item = None
        if re.match(r"^[-*]\s+", stripped):
            item = re.sub(r"^[-*]\s+", "", stripped)
        elif re.match(r"^\d+\.\s+", stripped):
            item = re.sub(r"^\d+\.\s+", "", stripped)

        if not item:
            continue

        cleaned_item = _strip_markdown(item)
        if cleaned_item:
            triggers.append(cleaned_item)

        quoted_phrases = re.findall(r'"([^"]+)"', item)
        for phrase in quoted_phrases:
            cleaned_phrase = _strip_markdown(phrase)
            if cleaned_phrase:
                triggers.append(cleaned_phrase)

    # Preserve order while removing duplicates.
    seen: set[str] = set()
    deduped: list[str] = []
    for trigger in triggers:
        normalized = trigger.strip()
        if not normalized:
            continue
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = text.replace("**", "").replace("*", "")
    return " ".join(text.split()).strip()


def _normalize_phrase(text: str) -> str:
    text = _strip_markdown(text)
    text = text.lower()
    text = re.sub(r"[^\w\-\u4e00-\u9fff ]+", " ", text)
    text = text.replace("_", " ")
    return " ".join(text.split())


def _tokenize(text: str) -> set[str]:
    normalized = _normalize_phrase(text)
    raw_tokens = re.findall(r"[a-z0-9][a-z0-9\-]+|[\u4e00-\u9fff]{2,}", normalized)
    tokens: set[str] = set()
    for token in raw_tokens:
        if re.fullmatch(r"[a-z0-9\-]+", token):
            if token in STOP_WORDS or len(token) < 2:
                continue
        tokens.add(token)

    for canonical, aliases in INTENT_TOKEN_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalize_phrase(alias)
            if normalized_alias and normalized_alias in normalized:
                tokens.add(canonical)
                break
    return tokens
