import { scheduleTask } from "@/lib/cloud-scheduler";
import {  NextResponse } from "next/server";

export async function POST(request: Request) {
    try {
    const body = await request.json();
    const { date_time, workflow_id, api_input, api_key } = body;
    console.log('haheheh')
    if (!date_time || !workflow_id) {
      return NextResponse.json({
        message:"Missing Required Feilds"
      },{
        status: 400
      })
    }
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || "https://fagoon.tech";
    const targetUrl = `${baseUrl}/api/workflow/execute-api?workflow_id=${workflow_id}`

    const taskConfig = {
      targetUrl,
      payload: {
        input: api_input,
        api_key,
        executed_from: 'SCHEDULED'
      },
    };
    
    const jobName = await scheduleTask(date_time, taskConfig);
    return NextResponse.json({
        message:"Task Scheduled successfully",
        data: jobName
    })
    
  } catch (error) {
    console.error('Schedule task error:', error);
    return NextResponse.json({
        message:"Failed to schedule task"
    },{
        status: 500
    })
  }
}