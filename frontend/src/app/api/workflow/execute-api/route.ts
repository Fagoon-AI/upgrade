"use server"
import { API_BASE_URL} from "@/utils/api/api";
import axios from "axios";
import {  NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest,context: { params: { workflow_id: string } }) {
    const body = await request.json();
    const searchParams= request.nextUrl.searchParams;
    const workflow_id = searchParams.get('workflow_id');

    const {  api_key, input } = body;
    let {executed_from} = body;
    if(!executed_from){
        executed_from = 'API'
    }
    const workflowResponse =  await axios.get(`${API_BASE_URL}/api/v1/workflow/${workflow_id}`);
    if(!workflowResponse.data) {
        return NextResponse.json(
            { error: "No workflow found, save your workflow before creating an API" },
            { status: 400 }
        );
    }
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || "https://fagoon.tech";
    const executionResponse = await axios.post(`${baseUrl}/api/workflow/execute`, {
        nodes: workflowResponse.data.workflow.nodes,
        edges: workflowResponse.data.workflow.edges,
        userInput: '',
        apiInput: input,
        user_id: api_key
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = (Object.values(executionResponse.data.nodes).at(-1) as { output?: any })?.output;

    await axios.post(`${API_BASE_URL}/api/v1/workflow/execute`, {
        workflow_id: workflow_id,
        result: result,
        api_key,
        executed_from: executed_from,
        status: 'COMPLETED',
    });
    return NextResponse.json({
        message: "Workflow created successfully",
        data: result, 
    });
}