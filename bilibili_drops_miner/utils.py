from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import json5

COOKIE_PATTERN = re.compile(r"\s*([^=;\s]+)\s*=\s*([^;]*)")
ACTIVITY_WINDOW_PATTERN = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*"
    r"(\d{1,2})[：:](\d{2})\s*[-—~～至]+\s*"
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*"
    r"(\d{1,2})[：:](\d{2})"
)


def _dedupe_preserving_order(values: Iterable[str | int]) -> list:
    seen: set[str | int] = set()
    result: list = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def parse_room_ids(raw: str) -> list[int]:
    room_ids: list[int] = []
    for token in raw.replace("\n", ",").split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        match = re.search(r"(?:https?://)?live\.bilibili\.com/(?:blanc/)?(\d+)", cleaned)
        if match:
            cleaned = match.group(1)
        if not cleaned.isdigit():
            raise ValueError(f"房间号格式错误: {cleaned}")
        room_id = int(cleaned)
        if room_id <= 0:
            raise ValueError(f"房间号必须大于 0: {cleaned}")
        room_ids.append(room_id)
    return _dedupe_preserving_order(room_ids)


def parse_task_ids(raw: str) -> list[str]:
    # 1. 尝试从粘贴的 URL/参数中提取 task_ids 的值
    #    匹配开头、? 或 & 之后的 task_ids=...（直到下一个 & 或结束）
    match = re.search(r"(?:^|[?&])task_ids=([^&]+)", raw)
    if match:
        raw = unquote(match.group(1))  # 只保留并解码逗号分隔的 ID 列表部分
    # 2. 原有逻辑：统一分隔符并逐项清洗
    task_ids: list[str] = []
    for token in raw.replace("\n", ",").split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        # 3. 二次防护：如果 token 还包含 &，截断取前半部分
        if '&' in cleaned:
            cleaned = cleaned.split('&', 1)[0].strip()
        if cleaned:
            task_ids.append(cleaned)
    return _dedupe_preserving_order(task_ids)


def parse_notification_urls(raw: str) -> list[str]:
    """Parse the GUI/CLI notification list without applying task-id semantics."""
    values: list[str] = []
    for token in raw.replace("\n", ",").split(","):
        cleaned = token.strip()
        if cleaned:
            values.append(cleaned)
    return _dedupe_preserving_order(values)


def _is_javascript_identifier_char(char: str) -> bool:
    return char.isalnum() or char in "_$"


def _normalize_javascript_literals(raw: str) -> str:
    """Convert the small set of minifier literals unsupported by JSON5.

    The replacement is lexical and never touches quoted strings.  Embedded
    activity state is data, so deliberately do not execute it with ``eval``.
    """
    normalized: list[str] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(raw):
        char = raw[index]
        if quote:
            normalized.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue

        if char in {'"', "'"}:
            quote = char
            normalized.append(char)
            index += 1
            continue

        if raw.startswith("!0", index):
            next_index = index + 2
            if (
                next_index >= len(raw)
                or not _is_javascript_identifier_char(raw[next_index])
            ):
                normalized.append("true")
                index = next_index
                continue
        if raw.startswith("!1", index):
            next_index = index + 2
            if (
                next_index >= len(raw)
                or not _is_javascript_identifier_char(raw[next_index])
            ):
                normalized.append("false")
                index = next_index
                continue
        if raw.startswith("undefined", index):
            previous = raw[index - 1] if index else ""
            next_index = index + len("undefined")
            following = raw[next_index] if next_index < len(raw) else ""
            if (
                not _is_javascript_identifier_char(previous)
                and not _is_javascript_identifier_char(following)
            ):
                normalized.append("null")
                index = next_index
                continue

        normalized.append(char)
        index += 1
    return "".join(normalized)


def _parse_embedded_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = json5.loads(_normalize_javascript_literals(raw))
    if not isinstance(value, dict):
        raise ValueError("页面内嵌状态不是对象")
    return value


def _extract_json_object_after_marker(raw: str, marker: str) -> dict:
    marker_index = raw.find(marker)
    if marker_index < 0:
        raise ValueError(f"未找到标记: {marker}")

    object_start = raw.find("{", marker_index + len(marker))
    if object_start < 0:
        raise ValueError(f"标记后未找到 JSON 对象: {marker}")

    depth = 0
    quote = ""
    escape = False
    object_end = -1

    for index in range(object_start, len(raw)):
        char = raw[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue

        if char in {'"', "'"}:
            quote = char
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                object_end = index + 1
                break

    if object_end <= object_start:
        raise ValueError(f"标记后的 JSON 对象不完整: {marker}")

    return _parse_embedded_object(raw[object_start:object_end])


def _extract_json_object_for_variable(raw: str, variable: str) -> dict:
    assignment = re.search(rf"{re.escape(variable)}\s*=\s*", raw)
    if assignment is None:
        raise ValueError(f"未找到变量: {variable}")
    return _extract_json_object_after_marker(raw, assignment.group(0))


def _task_group_position(position_boxes: list, index: int) -> tuple[float, float] | None:
    if index >= len(position_boxes):
        return None
    position_box = position_boxes[index]
    if not isinstance(position_box, dict):
        return None
    left = position_box.get("left")
    top = position_box.get("top")
    if not isinstance(left, (int, float)) or not isinstance(top, (int, float)):
        return None
    return float(left), float(top)


def _is_same_panel_column(
    prev_position: tuple[float, float] | None,
    cur_position: tuple[float, float] | None,
) -> bool:
    if prev_position is None or cur_position is None:
        return False

    prev_left, prev_top = prev_position
    cur_left, cur_top = cur_position
    return abs(prev_top - cur_top) <= 10 and abs(prev_left - cur_left) >= 200


def _partition_task_group_indexes(
    task_groups: list,
    panels: list,
    position_boxes: list,
) -> list[list[int]]:
    if not panels:
        return []
    if len(task_groups) <= len(panels):
        return [[index] for index in range(len(task_groups))]

    blocks: list[list[int]] = []
    for index in range(len(task_groups)):
        prev_position = _task_group_position(position_boxes, index - 1)
        cur_position = _task_group_position(position_boxes, index)
        if blocks and _is_same_panel_column(prev_position, cur_position):
            blocks[-1].append(index)
            continue
        blocks.append([index])

    if len(blocks) == len(panels):
        return blocks

    # 页面状态缺少明确的父子关系时，保底按顺序分配：
    # 前面的标签页各取一组，最后一个标签页合并剩余任务列表，避免漏掉多列任务。
    partitioned = [[index] for index in range(min(len(panels) - 1, len(task_groups)))]
    remaining_start = len(partitioned)
    if remaining_start < len(task_groups):
        partitioned.append(list(range(remaining_start, len(task_groups))))
    return partitioned


def _extract_task_ids_from_task_group(task_group: dict, seen: set[str]) -> list[str]:
    task_ids: list[str] = []
    for task in task_group.get("tasklist") or []:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("taskId") or "").strip()
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        task_ids.append(task_id)
    return task_ids


def _component_props(component: dict) -> dict:
    props = component.get("props")
    return props if isinstance(props, dict) else {}


def _component_children(component: dict) -> list[dict]:
    children: list[dict] = []
    slots = component.get("slots")
    if not isinstance(slots, list):
        return children
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_children = slot.get("children")
        if not isinstance(slot_children, list):
            continue
        children.extend(
            child for child in slot_children if isinstance(child, dict)
        )
    return children


def _walk_components(value) -> Iterable[dict]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_components(item)
        return
    if not isinstance(value, dict):
        return
    if isinstance(value.get("name"), str):
        yield value
    for child in _component_children(value):
        yield from _walk_components(child)


def _normalize_activity_text(value: str) -> str:
    text = value.strip()
    candidates = [text]
    for source_encoding in ("latin1", "cp949"):
        try:
            candidates.append(text.encode(source_encoding).decode("gb18030"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    def score(candidate: str) -> tuple[int, int]:
        cjk_count = sum("\u4e00" <= char <= "\u9fff" for char in candidate)
        replacement_count = candidate.count("\ufffd")
        return cjk_count, -replacement_count

    return max(candidates, key=score)


def _panel_label(panel: dict, fallback: str) -> str:
    tab_item = _component_props(panel).get("tabItem")
    if not isinstance(tab_item, dict):
        tab_item = {}
    for key in ("tabItemProps", "activatedTabItemProps"):
        item_props = tab_item.get(key)
        if not isinstance(item_props, dict):
            continue
        text_content = item_props.get("textContent")
        if not isinstance(text_content, dict):
            continue
        content = str(text_content.get("content") or "").strip()
        if content:
            return _normalize_activity_text(content)
    return fallback


def _task_ids_from_components(components: Iterable[dict]) -> list[str]:
    task_ids: list[str] = []
    seen: set[str] = set()
    for component in components:
        if component.get("name") != "EraTasklistPc":
            continue
        task_ids.extend(
            _extract_task_ids_from_task_group(_component_props(component), seen)
        )
    return task_ids


def parse_activity_time_window(
    text: str,
) -> tuple[datetime, datetime] | None:
    match = ACTIVITY_WINDOW_PATTERN.search(str(text or ""))
    if match is None:
        return None
    values = [int(value) for value in match.groups()]
    timezone = ZoneInfo("Asia/Shanghai")
    start_at = datetime(*values[:5], tzinfo=timezone)
    end_at = datetime(*values[5:], tzinfo=timezone)
    if end_at <= start_at:
        return None
    return start_at, end_at


def _panel_time_window(panel: dict) -> tuple[datetime, datetime] | None:
    for component in _walk_components(panel):
        props = _component_props(component)
        candidates = [
            props.get("content"),
            props.get("text"),
            props.get("textContent"),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("content")
            window = parse_activity_time_window(str(candidate or ""))
            if window is not None:
                return window
    return None


def _extract_nested_eva_task_groups(state: dict) -> list[dict[str, object]]:
    roots = state.get("layerTree")
    if not isinstance(roots, list):
        roots = [state]

    groups: list[dict[str, object]] = []
    consumed_task_components: set[int] = set()
    all_components = list(_walk_components(roots))
    for tabs in (item for item in all_components if item.get("name") == "EvaTabs"):
        active_panel_id = str(
            _component_props(tabs).get("activatedTabPanelId") or ""
        )
        panels = [
            item
            for item in _component_children(tabs)
            if item.get("name") == "EvaTabs.Panel"
        ]
        for index, panel in enumerate(panels, start=1):
            task_components = [
                item
                for item in _walk_components(panel)
                if item.get("name") == "EraTasklistPc"
            ]
            task_ids = _task_ids_from_components(task_components)
            consumed_task_components.update(id(item) for item in task_components)
            if not task_ids:
                continue
            panel_id = str(_component_props(panel).get("id") or "")
            group: dict[str, object] = {
                "label": _panel_label(panel, f"任务组 {index}"),
                "task_ids": task_ids,
                "active": bool(panel_id and panel_id == active_panel_id),
            }
            time_window = _panel_time_window(panel)
            if time_window is not None:
                group["start_at"] = time_window[0].isoformat()
                group["end_at"] = time_window[1].isoformat()
            groups.append(group)

    orphan_components = [
        item
        for item in all_components
        if item.get("name") == "EraTasklistPc"
        and id(item) not in consumed_task_components
    ]
    orphan_task_ids = _task_ids_from_components(orphan_components)
    if orphan_task_ids:
        groups.append(
            {
                "label": "当前任务",
                "task_ids": orphan_task_ids,
                "active": not groups,
            }
        )
    return groups


def extract_bili_live_task_groups(page_html: str) -> list[dict[str, object]]:
    try:
        eva_state = _extract_json_object_for_variable(
            page_html,
            "window.__BILIACT_EVAPAGEDATA__",
        )
        groups = _extract_nested_eva_task_groups(eva_state)
        if groups:
            return groups
    except (ValueError, json.JSONDecodeError):
        pass

    try:
        state = _extract_json_object_for_variable(
            page_html,
            "window.__initialState",
        )
    except (ValueError, json.JSONDecodeError):
        return []

    task_groups = state.get("EraTasklistPc") or []
    position_boxes = state.get("EvaPositionBox") or []
    panels = state.get("EvaTabs.Panel") or []
    tabs = state.get("EvaTabs") or []
    if not isinstance(task_groups, list) or not isinstance(panels, list):
        return []
    if not isinstance(position_boxes, list):
        position_boxes = []

    active_panel_id = ""
    if tabs and isinstance(tabs[0], dict):
        active_panel_id = str(tabs[0].get("activatedTabPanelId") or "")

    groups: list[dict[str, object]] = []
    task_group_indexes_by_panel = _partition_task_group_indexes(
        task_groups,
        panels,
        position_boxes,
    )
    for index, panel in enumerate(panels):
        if not isinstance(panel, dict) or index >= len(task_group_indexes_by_panel):
            continue

        tab_item = panel.get("tabItem") or {}
        if not isinstance(tab_item, dict):
            tab_item = {}
        tab_item_props = tab_item.get("tabItemProps") or {}
        activated_props = tab_item.get("activatedTabItemProps") or {}
        if not isinstance(tab_item_props, dict):
            tab_item_props = {}
        if not isinstance(activated_props, dict):
            activated_props = {}
        tab_text = tab_item_props.get("textContent") or {}
        activated_text = activated_props.get("textContent") or {}
        if not isinstance(tab_text, dict):
            tab_text = {}
        if not isinstance(activated_text, dict):
            activated_text = {}
        label = (
            str(
                tab_text.get("content")
                or activated_text.get("content")
                or f"任务组 {index + 1}"
            ).strip()
            or f"任务组 {index + 1}"
        )
        label = _normalize_activity_text(label)
        panel_id = str(panel.get("id") or "")

        task_ids: list[str] = []
        seen: set[str] = set()
        for task_group_index in task_group_indexes_by_panel[index]:
            if task_group_index >= len(task_groups):
                continue
            task_group = task_groups[task_group_index]
            if not isinstance(task_group, dict):
                continue
            task_ids.extend(_extract_task_ids_from_task_group(task_group, seen))

        if not task_ids:
            continue

        groups.append(
            {
                "label": label,
                "task_ids": task_ids,
                "active": panel_id == active_panel_id,
            }
        )

    return groups


def parse_cookie(cookie_text: str) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for key, value in COOKIE_PATTERN.findall(cookie_text):
        cookie_map[key] = value
    return cookie_map


def get_cookie_value(cookie_text: str, key: str) -> str:
    return parse_cookie(cookie_text).get(key, "")


def join_cookie(cookie_map: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookie_map.items())
