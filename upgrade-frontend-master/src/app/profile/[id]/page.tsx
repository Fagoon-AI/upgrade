"use client"
import { API_ENDPOINTS } from '@/utils/api/api'
import axios from 'axios'
import { useParams, useRouter } from 'next/navigation'
import React, { useEffect } from 'react'
import { showSuccessToast } from "@/utils/toast"

const GoogleValidationPage = () => {
    const params = useParams()
    const router = useRouter()
    const validateAndRedirect = async () => {
        const { id } = params
        if (!id) {
            console.error('No ID provided in the URL parameters.')
            return
        }
        try {
            const u = localStorage.getItem('user')
            if (!u) {
                console.error('User not found in local storage.')
                return
            }
            const user = JSON.parse(u)
            await axios.post(`${API_ENDPOINTS.AGENT}/google-auth/save`, { google_id: id, system_user_id: user._id })
        } catch (error) {
            console.error('Error validating Google ID:', error)
            showSuccessToast('Failed to validate Google ID. Please try again .')
        } finally {
            router.push('/profile')
        }
    }

    useEffect(() => {
        if (params && params.id) {
            validateAndRedirect()
        }
    }, [params])
    return (
        <div></div>
    )
}

export default GoogleValidationPage