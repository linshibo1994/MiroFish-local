"""
地点实体过滤规则。

图谱中的实体用于社媒舆论模拟和人设 Agent 构建，纯地点、地址、区域等
不能独立发声的节点不应进入本体、前端展示或 Agent 构建链路。
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


GENERIC_NODE_LABELS = {"Entity", "Node"}

LOCATION_ENTITY_TYPE_NAMES = {
    "Address",
    "AdministrativeArea",
    "AdministrativeRegion",
    "Area",
    "City",
    "Country",
    "County",
    "District",
    "GeoLocation",
    "GeographicLocation",
    "Landmark",
    "Location",
    "Municipality",
    "Neighborhood",
    "Place",
    "Province",
    "Region",
    "Site",
    "State",
    "Street",
    "Territory",
    "Town",
    "Venue",
    "Village",
    "Zone",
    "区域",
    "地址",
    "地点",
    "地标",
    "地区",
    "城市",
    "场所",
    "位置",
    "省份",
    "行政区",
}

LOCATION_ENTITY_TYPE_TOKENS = {
    "address",
    "area",
    "city",
    "country",
    "county",
    "district",
    "geo",
    "geographic",
    "geolocation",
    "landmark",
    "location",
    "municipality",
    "neighborhood",
    "place",
    "province",
    "region",
    "site",
    "state",
    "street",
    "territory",
    "town",
    "venue",
    "village",
    "zone",
}

LOCATION_ENTITY_TYPE_KEYWORDS = {
    "位置",
    "地址",
    "地点",
    "地标",
    "地理",
    "地区",
    "城市",
    "场所",
    "省份",
    "区域",
    "行政区",
}

LOCATION_NAME_SUFFIXES = (
    "自治区",
    "特别行政区",
    "自治州",
    "街道",
    "大道",
    "广场",
    "机场",
    "车站",
    "港口",
    "公园",
    "省",
    "市",
    "县",
    "区",
    "镇",
    "乡",
    "村",
    "州",
    "国",
    "路",
    "街",
    "山",
    "河",
    "湖",
    "海",
    "湾",
    "岛",
)

SPEAKING_ACTOR_TYPE_NAMES = {
    "Agency",
    "Association",
    "Brand",
    "Bureau",
    "Club",
    "Committee",
    "Company",
    "Council",
    "Court",
    "Department",
    "Enterprise",
    "Government",
    "GovernmentAgency",
    "Group",
    "Hospital",
    "Institution",
    "MediaOutlet",
    "Ministry",
    "NGO",
    "Organization",
    "Person",
    "Platform",
    "Police",
    "Public",
    "Resident",
    "School",
    "Team",
    "University",
}

SPEAKING_ACTOR_TYPE_TOKENS = {
    "agency",
    "association",
    "brand",
    "bureau",
    "club",
    "committee",
    "company",
    "corporation",
    "council",
    "court",
    "department",
    "enterprise",
    "government",
    "group",
    "hospital",
    "institution",
    "media",
    "ministry",
    "ngo",
    "organization",
    "organisation",
    "person",
    "platform",
    "police",
    "public",
    "resident",
    "school",
    "team",
    "university",
}

SPEAKING_ACTOR_KEYWORDS = {
    "协会",
    "医院",
    "单位",
    "品牌",
    "公众",
    "团队",
    "大学",
    "委员会",
    "媒体",
    "学校",
    "学院",
    "官方",
    "官员",
    "平台",
    "市民",
    "企业",
    "人群",
    "居民",
    "报社",
    "政府",
    "机构",
    "检察院",
    "法院",
    "电视台",
    "组织",
    "公司",
    "警方",
    "公安",
    "部门",
    "集团",
}

GRAPHITI_EXCLUDED_LOCATION_ENTITY_TYPES = tuple(sorted(LOCATION_ENTITY_TYPE_NAMES))


def is_speaking_actor_type(type_name: Any) -> bool:
    """判断实体类型是否明显属于可发声主体。"""
    text = str(type_name or "").strip()
    if not text:
        return False

    normalized = _normalize_type_name(text)
    if normalized in {_normalize_type_name(name) for name in SPEAKING_ACTOR_TYPE_NAMES}:
        return True

    tokens = _identifier_tokens(text)
    if tokens & SPEAKING_ACTOR_TYPE_TOKENS:
        return True

    return any(keyword in text for keyword in SPEAKING_ACTOR_KEYWORDS)


def is_location_entity_type(type_name: Any) -> bool:
    """判断实体类型是否属于纯地点/位置/地址类。"""
    text = str(type_name or "").strip()
    if not text or is_speaking_actor_type(text):
        return False

    normalized = _normalize_type_name(text)
    if normalized in {_normalize_type_name(name) for name in LOCATION_ENTITY_TYPE_NAMES}:
        return True

    tokens = _identifier_tokens(text)
    if tokens & LOCATION_ENTITY_TYPE_TOKENS:
        return True

    lowered = text.casefold()
    return any(keyword in lowered for keyword in LOCATION_ENTITY_TYPE_KEYWORDS)


def is_location_entity_node(node: Any) -> bool:
    """判断图谱节点是否应作为地点实体过滤掉。"""
    labels = _as_list(_get_value(node, "labels", []))
    custom_labels = [
        str(label).strip()
        for label in labels
        if str(label).strip() and str(label).strip() not in GENERIC_NODE_LABELS
    ]

    if any(is_speaking_actor_type(label) for label in custom_labels):
        return False
    if any(is_location_entity_type(label) for label in custom_labels):
        return True

    attributes = _get_value(node, "attributes", {}) or {}
    attribute_type_values = _iter_attribute_type_values(attributes)
    if any(is_speaking_actor_type(value) for value in attribute_type_values):
        return False
    if any(is_location_entity_type(value) for value in attribute_type_values):
        return True

    if custom_labels:
        return False

    name = str(_get_value(node, "name", "") or "").strip()
    return _is_name_like_location(name)


def filter_location_entities(nodes: List[Any], edges: List[Any]) -> Tuple[List[Any], List[Any]]:
    """过滤地点节点，并移除指向这些节点的边。"""
    if not nodes:
        return nodes, edges

    blocked_uuids = {
        str(_get_value(node, "uuid", "") or "")
        for node in nodes
        if is_location_entity_node(node)
    }
    blocked_uuids.discard("")

    if not blocked_uuids:
        return nodes, edges

    filtered_nodes = [
        node for node in nodes
        if str(_get_value(node, "uuid", "") or "") not in blocked_uuids
    ]
    filtered_edges = [
        edge for edge in (edges or [])
        if str(_get_value(edge, "source_node_uuid", "") or "") not in blocked_uuids
        and str(_get_value(edge, "target_node_uuid", "") or "") not in blocked_uuids
    ]
    return filtered_nodes, filtered_edges


def strip_location_entity_types_from_ontology(ontology: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """从本体定义中移除地点实体类型和引用地点类型的关系端点。"""
    cleaned = copy.deepcopy(ontology or {})
    entity_types = cleaned.get("entity_types") or []
    removed_type_names = {
        entity.get("name")
        for entity in entity_types
        if isinstance(entity, dict) and is_location_entity_type(entity.get("name"))
    }

    cleaned["entity_types"] = [
        entity for entity in entity_types
        if not (
            isinstance(entity, dict)
            and entity.get("name") in removed_type_names
        )
    ]

    cleaned_edges = []
    for edge in cleaned.get("edge_types") or []:
        if not isinstance(edge, dict):
            continue

        source_targets = edge.get("source_targets") or []
        had_source_targets = bool(source_targets)
        edge["source_targets"] = [
            source_target
            for source_target in source_targets
            if not _source_target_has_location_type(source_target, removed_type_names)
        ]

        if had_source_targets and not edge["source_targets"]:
            continue
        cleaned_edges.append(edge)
    cleaned["edge_types"] = cleaned_edges

    return cleaned


def _source_target_has_location_type(source_target: Any, removed_type_names: Iterable[str]) -> bool:
    if not isinstance(source_target, dict):
        return False
    removed = set(removed_type_names)
    source = source_target.get("source")
    target = source_target.get("target")
    return (
        source in removed
        or target in removed
        or is_location_entity_type(source)
        or is_location_entity_type(target)
    )


def _get_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _iter_attribute_type_values(attributes: Dict[str, Any]) -> List[Any]:
    values = []
    for key in ("entity_type", "type", "category", "kind", "label", "labels"):
        value = attributes.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value:
            values.append(value)
    return values


def _identifier_tokens(value: str) -> set[str]:
    with_spaces = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    with_spaces = re.sub(r"[^A-Za-z0-9]+", " ", with_spaces)
    return {token.casefold() for token in with_spaces.split() if token}


def _normalize_type_name(value: str) -> str:
    return re.sub(r"[\s_\-:：/\\]+", "", str(value or "")).casefold()


def _is_name_like_location(name: str) -> bool:
    if not name or any(keyword in name for keyword in SPEAKING_ACTOR_KEYWORDS):
        return False
    if any(keyword in name for keyword in LOCATION_ENTITY_TYPE_KEYWORDS):
        return True
    return any(
        name.endswith(suffix) and len(name) >= max(3, len(suffix) + 1)
        for suffix in LOCATION_NAME_SUFFIXES
    )
