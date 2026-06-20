import LoadingPage from '@/app/loading'
import { Button } from '@/components/ui/button'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { API_BASE_URL } from '@/utils/api/api'
import axios from 'axios'
import React, { useEffect, useState } from 'react'
import { showSuccessToast } from "@/utils/toast"



const ScheduleDialog = ({ id }: { id: string | undefined }) => {
    const [apiKey, setApiKey] = useState<string | undefined>(undefined)

    useEffect(() => {
        const getAPIKey = async () => {
            try {
                const response = await axios.get(`${API_BASE_URL}/api/v1/apikey`,
                    { headers: { Authorization: `Bearer ${localStorage.getItem('upgrade-token')}` } }
                )
                setApiKey(response.data.apiKey.apiKey)
                return response.data.apiKey
            } catch (e) {
                console.log(e)
            }
        }
        getAPIKey()
    }, [])

    const [input, setInput] = useState('')
    const [dateTime, setDateTime] = useState<Date>()
    const handleSchedule = async () => {
        if (!dateTime) return;
        await axios.post(`/api/workflow/schedule`, {
            date_time: dateTime,
            workflow_id: id,
            api_input: input,
            api_key: apiKey,
        })
        showSuccessToast('Workflow Scheduled')
    }
    if (!apiKey) {
        return <LoadingPage />
    }
    if (!id) {
        return <></>
    }
    return (
        <div className='flex flex-col gap-4'>
            <h4>Schedule Workflow:</h4>
            <div className='flex flex-col gap-2'>
                <Label>Set Schedule Date Time</Label>
                <DateTimePicker onChange={(val) => setDateTime(val)} />
            </div>
            <div className='flex flex-col gap-2'>
                <Label>Enter Api input</Label>
                <Input value={input} onChange={(e) => setInput(e.target.value)} />
            </div>
            <Button onClick={() => handleSchedule()} >Schedule</Button>
        </div>
    )
}

export default ScheduleDialog