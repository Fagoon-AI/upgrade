import json
from loguru import logger
from typing import Dict, List, Union
from datetime import datetime, timezone

from src.schemas.common import (ConversationRoleEnum,
                                UpgradeChatInsertModel,
                                AgentChatInsertModel)
from src.utils.common import generate_uuid


def prepare_chat_insert_model(
    insert_message: Union[List[Union[str, Dict]], str],
    conversation_id: str,
    role: ConversationRoleEnum,
    is_upgrade_chat: bool = False,
) -> Union[AgentChatInsertModel, UpgradeChatInsertModel, None]:
    def normalize_message(item: Union[str, Dict]) -> Union[Dict, None]:
        if isinstance(item, str):
            try:
                return json.loads(item)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON skipped: {item}")
                return None
        if isinstance(item, dict):
            return {"type": "chat", "data": item["chat"]} if "chat" in item else item
        return None

    ModelCls = UpgradeChatInsertModel if is_upgrade_chat else AgentChatInsertModel
    current_timestamp = datetime.now(timezone.utc)

    if isinstance(insert_message, str):
        return ModelCls(
            uuid=conversation_id,
            role=role.value,
            message=insert_message,
            created_at=current_timestamp,
            updated_at=current_timestamp
        )

    elif isinstance(insert_message, list):
        normalized = list(filter(None, map(normalize_message, insert_message)))
        message_parts = []
        image_data = None
        tool_selection = None
        status_list = []
        additional_metadata_items = []

        for item in normalized:
            msg_type, data = item.get("type"), item.get("data")
            if msg_type == "chat":
                if isinstance(data, str):
                    message_parts.append(data)
            elif msg_type == "image":
                image_data = {"image": data}
            elif msg_type == "tool_selection":
                tool_selection = {"type": msg_type, "data": data}
            elif msg_type == "status":
                if isinstance(data, str) and len(data) < 1024: # Cap status item length
                    status_list.append(data)
            else:
                additional_metadata_items.append({"type": msg_type, "data": data})

        message = "\n".join(message_parts)
        metadata = []
        if status_list:
            metadata.append({"type": "status", "data": status_list})
        if additional_metadata_items:
            metadata.extend(additional_metadata_items)

        return ModelCls(
            uuid=conversation_id,
            role=role.value,
            message=message,
            images=image_data,
            tool_selection=tool_selection,
            metadata=metadata or None,
            created_at=current_timestamp,
            updated_at=current_timestamp
        )

    logger.error(f"Unsupported insert_message type: {type(insert_message)}")
    return None