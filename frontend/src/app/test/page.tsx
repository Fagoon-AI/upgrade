"use client"

import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import React, { useState } from 'react'
import MarkdownIt from 'markdown-it/dist/markdown-it.js'
import DOMPurify from 'dompurify'

import { vscDarkPlus } from "react-syntax-highlighter/dist/cjs/styles/prism";
import { docco } from "react-syntax-highlighter/dist/esm/styles/hljs";
import { DateTimePicker } from "@/components/ui/date-time-picker";
import axios from "@/lib/api/axios";
import { API_ENDPOINTS } from "@/utils/api/api";
const md = new MarkdownIt()
const renderMarkdown = (text: string) => {
    try {
        return DOMPurify.sanitize(md.render(text))
    } catch {
        return DOMPurify.sanitize(text)
    }
}
const handleAPISEND = async () => {
    await axios.post(`${API_ENDPOINTS.AGENT}/upgrade/generate-title`, {
        conversation_id: '9a0bd572-4c9f-4c55-b936-f26f915203a1'
    })
}
const TestPage = () => {
    return (
        <div onClick={handleAPISEND}>Button</div>
    )
}

export default TestPage