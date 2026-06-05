from typing import Any, Dict, List, Optional


# def prepare_formatted_message(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
#     return [
#         {"role": msg["role"], "content": msg["message"]}
#         for msg in messages
#         if isinstance(msg, dict) and "role" in msg and "message" in msg
#     ]


def prepare_formatted_message(
    role: str,
    message: str,
    images: Optional[Dict[str, Any]] = None,
    tool_selection: Optional[Dict[str, Any]] = None,
    metadata: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:

    content_parts = [message]

    if images and images.get("urls"):
        image_urls = ", ".join(images["urls"])
        content_parts.append(f"\n\n[Image(s): {image_urls}]")

    if tool_selection and tool_selection.get("data"):
        content_parts.append(f"\n\n[Tool Used: {tool_selection['data']}]")

    if metadata:
        for item in metadata:
            if item.get("type") == "research_details" and item.get("data"):
                details = item["data"]
                detail_strings = []
                if details.get("task"): detail_strings.append(f"Task: {details['task']}")
                if details.get("report_type"): detail_strings.append(f"Report Type: {details['report_type']}")
                if details.get("source_urls"): detail_strings.append(f"Sources: {', '.join(details['source_urls'])}")
                if detail_strings:
                    content_parts.append(f"\n\n[Research Details: {'; '.join(detail_strings)}]")
            elif item.get("type") == "status" and item.get("data"):
                content_parts.append(f"\n\n[Status: {', '.join(item['data'])}]")

    final_content = "".join(content_parts).strip()
    return {"role": role, "content": final_content}