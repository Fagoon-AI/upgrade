AVAILABLE_TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": """Performs real-time web searches to retrieve the most current and relevant information 
                              from the internet. This tool is ideal for accessing breaking news, verifying facts, 
                              checking current events, or exploring topics beyond the model’s training data. 
                              Use when up-to-date or localized content is needed.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "(required) The search query to submit to the search engine.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "(optional) The number of search results to return. Default is 5.",
                    },
                    "lang": {
                        "type": "string",
                        "description": "(optional) Language code for search results (default: en).",
                    },
                    "country": {
                        "type": "string",
                        "description": "(optional) Country code for search results (default: us).",
                    },
                    "fetch_content": {
                        "type": "boolean",
                        "description": "(optional) Whether to fetch full content from result pages. Default is false.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_generation",
            "description": """Generates a high-quality, photorealistic, or artistic image based on a user's description. 
                              Use this tool when the user explicitly asks to create, draw, generate, or make an image, 
                              picture, or visual representation of a concept. Do not use it for requests that can be 
                              answered with text.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed, descriptive prompt of the image to be generated. This should capture the user's full intent.",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mermaid_diagram",
            "description": """Generates a Mermaid.js markdown diagram from a user's description.
                              Use this tool when the user asks to create a flowchart, sequence diagram, Gantt chart, mind map,
                              or any other visual process or structure. This tool is ideal for representing workflows,
                              hierarchies, or timelines.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed, descriptive prompt of the diagram to be generated. This should capture the user's full intent for the diagram's content and structure.",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]