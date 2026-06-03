from dataclasses import dataclass, field


@dataclass
class TaskGroup:
    bay: str = ""
    process: str = ""
    obj: str = ""
    requires: list[str] = field(default_factory=list)


Tasks: list[TaskGroup] = []


def load_preset(json_path: str):
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        groups = json.load(f)
    Tasks.clear()
    for group in groups:
        Tasks.append(TaskGroup(
            bay=group.get("bay", ""),
            process=group["process"],
            obj=group.get("obj", ""),
            requires=list(group["requires"]),
        ))


def save_preset(json_path: str):
    import json
    data = [
        {
            "bay": g.bay,
            "process": g.process,
            "obj": g.obj,
            "requires": list(g.requires),
        }
        for g in Tasks
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
