'use client'
import { useEffect, useRef, useState, useCallback } from 'react'

export function useWebSocket() {
    const url = process.env.NEXT_PUBLIC_WEBSOCKET_URL
    if (!url) throw new Error('NEXT_PUBLIC_WEBSOCKET_URL is not defined')

    const socketRef = useRef<WebSocket | null>(null)
    const [isConnected, setIsConnected] = useState(false)
    const [messages, setMessages] = useState<string[]>([])
    const [error, setError] = useState<string | null>(null)
    const streamCallback = useRef<((data: string) => boolean | void) | null>(null)

    const sendMessage = useCallback((msg: string) => {
        const socket = socketRef.current
        if (socket?.readyState === WebSocket.OPEN) {
            console.log('[WebSocket] 📤 Sending:', msg)
            socket.send(msg)
        } else {
            console.warn('[WebSocket] ⚠️ Socket not open')
        }
    }, [])

    const streamMessage = useCallback((msg: string, onChunk: (chunk: string) => boolean | void) => {
        const socket = socketRef.current
        if (socket?.readyState === WebSocket.OPEN) {
            console.log('[WebSocket] 📤 Starting stream:', msg)
            streamCallback.current = onChunk
            socket.send(msg)
        } else {
            console.warn('[WebSocket] ⚠️ Socket not open for stream')
        }
    }, [])

    useEffect(() => {
        const socket = new WebSocket(url)
        socketRef.current = socket

        socket.addEventListener('open', () => {
            console.log('[WebSocket] ✅ Connected')
            setIsConnected(true)
        })

        socket.addEventListener('close', () => {
            console.log('[WebSocket] 🔌 Disconnected')
            setIsConnected(false)
        })

        socket.addEventListener('error', (e) => {
            console.log('[WebSocket] 💥 Error:', e)
            setError('Socket error')
        })

        socket.addEventListener('message', (event) => {
            const data = event.data
            console.log('[WebSocket] 📥 Received:', data)
            setMessages((prev) => [...prev, data])

            if (streamCallback.current) {
                const stop = streamCallback.current(data)
                if (stop === false || data === '[DONE]') {
                    console.log('[WebSocket] 🛑 Ending stream')
                    streamCallback.current = null
                }
            }
        })

        return () => {
            console.log('[WebSocket] 🧹 Cleaning up')
            socket.close()
        }
    }, [url])

    return {
        isSocketConnected: isConnected,
        socketMessages: messages,
        socketError: error,
        sendMessage,
        streamSocketMessage: streamMessage,
    }
}
