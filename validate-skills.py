#!/usr/bin/env python3
"""检查本包里每个技能是否会被 DSH 正确加载、正文引用的资源是否都存在。

DSH 的加载规则（按 dsh-skill-filesystem / dsh-tool-skill 的实现）：
- frontmatter 必须有 name 与 description；name 需匹配 ^[a-z0-9]+(?:-[a-z0-9]+)*$；
- description 进入模型目录时按 catalogDescriptionMaxLength（默认 500）截断，超了就等于没写完；
- `disable-model-invocation` / `user-invocable` 只接受布尔（true/false/yes/no/on/off/1/0），
  写错类型会让**整个技能被丢弃**；
- 驼峰旧键 `disableModelInvocation` / `modelInvocable` / `userInvocable` 会直接报错并丢弃技能；
- `whenToUse` 只出现在 SkillSummary / 会话 API / GUI，**不进模型上下文**，不要拿它承载路由信息。

用法:
    python3 validate-skills.py [技能目录 ...]

退出码: 0 = 无 error；1 = 有 error。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DESCRIPTION_HARD_LIMIT = 500  # dsh-tool-skill 的 catalogDescriptionMaxLength 默认值
DESCRIPTION_BUDGET = 300      # 超过就该考虑压缩，留出余量
BOOLEAN_KEYS = ("disable-model-invocation", "user-invocable")
BOOLEAN_VALUES = {"true", "false", "yes", "no", "on", "off", "1", "0"}
LEGACY_KEYS = ("disableModelInvocation", "modelInvocable", "userInvocable")
KNOWN_KEYS = {"name", "description", "whenToUse", "metadata", *BOOLEAN_KEYS}
RESOURCE_DIRS = ("references", "scripts", "assets")
RESOURCE_REF = re.compile(r"\b(?:references|scripts|assets)/[A-Za-z0-9._][A-Za-z0-9._/-]*")

errors: list[str] = []
warnings: list[str] = []


def error(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """解析扁平 YAML frontmatter；metadata 之类的嵌套块只记录键名。"""
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            data: dict[str, str] = {}
            for raw in lines[1:index]:
                if not raw.strip() or raw.lstrip().startswith("#"):
                    continue
                if raw[:1].isspace():  # 嵌套值，本检查不解析
                    continue
                key, sep, value = raw.partition(":")
                if not sep:
                    continue
                data[key.strip()] = value.strip().strip("'\"")
            return data, "\n".join(lines[index + 1:])
    return None


def check_skill(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    parsed = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if parsed is None:
        error("缺少 YAML frontmatter（技能会被丢弃）")
        return
    data, body = parsed

    name = data.get("name", "")
    if not name:
        error("frontmatter 缺少 name（技能会被丢弃）")
    elif not SKILL_NAME.match(name):
        error(f"name={name!r} 不是 kebab-case（技能会被丢弃）")
    elif name != skill_dir.name:
        warn(f"name={name!r} 与目录名 {skill_dir.name!r} 不一致；寻址用 name，容易混")

    description = data.get("description", "")
    if not description:
        error("frontmatter 缺少 description（技能会被丢弃）")
    elif len(description) > DESCRIPTION_HARD_LIMIT:
        error(f"description {len(description)} 字符超过 {DESCRIPTION_HARD_LIMIT}，会被截断")
    elif len(description) > DESCRIPTION_BUDGET:
        warn(f"description {len(description)} 字符偏长（预算 {DESCRIPTION_BUDGET}），只有它参与路由")
    if description and "不" not in description:
        warn("description 没写排除项；路由需要正反两面才能避免误触发")

    for key in LEGACY_KEYS:
        if key in data:
            error(f"frontmatter 含驼峰旧键 {key}，DSH 会直接报错并丢弃整个技能")

    for key in BOOLEAN_KEYS:
        if key in data and data[key].lower() not in BOOLEAN_VALUES:
            error(f"{key}={data[key]!r} 不是布尔值，DSH 会丢弃整个技能")

    for key in sorted(set(data) - KNOWN_KEYS - set(LEGACY_KEYS)):
        warn(f"frontmatter 含 DSH 不消费的键 {key}（会被忽略，别放关键语义）")

    mentioned = {match.rstrip(".,;:、。）】") for match in RESOURCE_REF.findall(body + "\n" + "\n".join(data.values()))}
    # 只校验本技能内部资源；指向别的技能或仓库的路径不在本技能职责范围。
    local_dirs = {d for d in RESOURCE_DIRS if (skill_dir / d).is_dir()}
    for relative in sorted(mentioned):
        if relative.split("/", 1)[0] not in local_dirs:
            continue
        if not (skill_dir / relative).exists():
            error(f"正文提到 {relative}，但文件不存在")

    for directory in RESOURCE_DIRS:
        target = skill_dir / directory
        if not target.is_dir():
            continue
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(skill_dir))
            if not any(relative == ref or relative.startswith(ref + "/") for ref in mentioned):
                warn(f"{relative} 没有被正文引用；模型不会知道什么时候打开它")


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent
    if len(argv) > 1:
        skills = [Path(arg).resolve() for arg in argv[1:]]
    else:
        skills = sorted(path.parent for path in root.glob("*/SKILL.md"))
    if not skills:
        print("没有找到任何技能（期望 <技能目录>/SKILL.md）", file=sys.stderr)
        return 1

    print(f"检查 {len(skills)} 个技能\n")
    for skill_dir in skills:
        errors.clear()
        warnings.clear()
        print(f"== {skill_dir.name} ==")
        check_skill(skill_dir)
        for message in warnings:
            print(f"  warning: {message}")
        for message in errors:
            print(f"  error:   {message}")
        if not errors and not warnings:
            print("  通过")
        print()
        if errors:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
