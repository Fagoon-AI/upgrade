import * as userApi from "@/lib/api/user"
import React, { useEffect, useState } from 'react'
import LoadingPage from '../loading'
import { FaRegCopy } from 'react-icons/fa'
import { showSuccessToast } from "@/utils/toast"

const ApiKeyDialog = () => {

    const [isLoading, setLoading] = useState(true)
    const [apiKey, setApikey] = useState<undefined | { apiKey: string }>(undefined)
    useEffect(() => {
        getAPIKey()

    }, [])
    const getAPIKey = async () => {
        try {
            const response = await userApi.getApiKeys()
            setApikey(response.apiKey)
            setLoading(false)
            return response.apiKey
        } catch (e) {
            console.log(e)
            setLoading(false)
        }
    }

    const generateAPIKey = async () => {
        try {
            setLoading(true)
            const response = await userApi.generateApiKey()
            setApikey(response.apiKey)
            setLoading(false)
            return response.apiKey
        } catch (e) {
            setLoading(false)
            console.log(e)
        }
    }

    if (isLoading) {
        return <LoadingPage />
    }
    return (
        <div>
            {apiKey ?
                <div onClick={() => {
                    showSuccessToast('Api Key Copied To Clipboard')
                    navigator.clipboard.writeText(apiKey.apiKey)
                }}
                >
                    API Key Already Exists:
                    <div className='flex items-center gap-2 text-sm hover:underline cursor-pointer'>
                        <FaRegCopy />
                        Copy Key
                    </div>
                </div> :
                <div className='text-sm underline cursor-pointer'
                    onClick={generateAPIKey}
                >
                    Generate Key
                </div>}
        </div>
    )
}

export default ApiKeyDialog