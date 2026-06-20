"use client"
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import WorkflowExecutionLogs from '@/components/workflow/dashboard/execution-logs'
import WorkflowDashboard from '@/components/workflow/dashboard/workflow-dashboard'
import React from 'react'

const WorkflowDashboardPage = () => {
  return (
    <div className='m-10'>
      <Tabs defaultValue="dashboard" className="w-full">
        <div className="px-6">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
            <TabsTrigger value="logs">Execution Logs</TabsTrigger>
          </TabsList>
        </div>
        <ScrollArea className="h-full px-6 py-4">
          <TabsContent value="dashboard" className="mt-0">
            <WorkflowDashboard />
          </TabsContent>
          <TabsContent value="logs" className="mt-0">
            <WorkflowExecutionLogs />
          </TabsContent>
        </ScrollArea>
      </Tabs>

    </div>
  )
}

export default WorkflowDashboardPage