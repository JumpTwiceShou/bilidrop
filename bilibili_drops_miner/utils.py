from __future__ import annotations

import json
import re

COOKIE_PATTERN = re.compile(r"\s*([^=;\s]+)\s*=\s*([^;]*)")


def parse_room_ids(raw: str) -> list[int]:
    room_ids: list[int] = []
    for token in raw.replace("\n", ",").split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        if not cleaned.isdigit():
            raise ValueError(f"房间号格式错误: {cleaned}")
        room_id = int(cleaned)
        if room_id <= 0:
            raise ValueError(f"房间号必须大于 0: {cleaned}")
        room_ids.append(room_id)
    return room_ids


def parse_task_ids(raw: str) -> list[str]:
    # 1. 尝试从粘贴的 URL/参数中提取 task_ids 的值
    #    匹配开头、? 或 & 之后的 task_ids=...（直到下一个 & 或结束）
    match = re.search(r"(?:^|[?&])task_ids=([^&]+)", raw)
    if match:
        raw = match.group(1)  # 只保留逗号分隔的 ID 列表部分
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
    return task_ids


def _extract_json_object_after_marker(raw: str, marker: str) -> dict:
    marker_index = raw.find(marker)
    if marker_index < 0:
        raise ValueError(f"未找到标记: {marker}")

    object_start = raw.find("{", marker_index + len(marker))
    if object_start < 0:
        raise ValueError(f"标记后未找到 JSON 对象: {marker}")

    depth = 0
    in_string = False
    escape = False
    object_end = -1

    for index in range(object_start, len(raw)):
        char = raw[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
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

    return json.loads(raw[object_start:object_end])


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


def extract_bili_live_task_groups(page_html: str) -> list[dict[str, object]]:
    try:
        state = _extract_json_object_after_marker(page_html, "window.__initialState =")
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
