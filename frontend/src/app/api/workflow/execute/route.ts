import { workflowExecutor } from "@/lib/services/workflow-executor";
import {  NextResponse } from "next/server";

export async function POST(request: Request) {
    const body = await request.json();
    const {nodes, edges, userInput, apiInput, user_id} = body;
    if(apiInput){
        nodes.forEach(node => {
            if(node.data.id == 'api-input'){
                node['data'].settings= [...node.data.settings, {
                    id: 'apiInputLabel',
                    name: 'API Input Prompt',
                    type: 'text',
                    description: 'API pronpt',
                    default: apiInput
                }];
            } 
        });
    }
    if (!nodes || !edges ) {
        return NextResponse.json(
            { error: "No nodes, edges or userInput is provided" },
            { status: 400 }
        );
    }
    const execution = await workflowExecutor.executeWorkflow(nodes, edges, userInput, user_id);
    return NextResponse.json(execution);
}