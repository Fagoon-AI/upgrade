import { CloudSchedulerClient } from '@google-cloud/scheduler';
import { v4 as uuidv4 } from 'uuid';
import { protos } from '@google-cloud/scheduler';

const scheduler = new CloudSchedulerClient({
    keyFilename: 'src/lib/storage/bucket-key.json',
});

const projectId: string = process.env.GOOGLE_CLOUD_PROJECT_ID || 'fagoon-ai';
const location: string = process.env.GOOGLE_CLOUD_LOCATION || 'asia-southeast1';
const parent: string = scheduler.locationPath(projectId, location);
interface TaskConfig {
  targetUrl: string;
  payload: Record<string, unknown>;
  authToken?: string;
}

export async function scheduleTask(
  dateTime: string,
  taskConfig: TaskConfig,
  jobId: string | null = null
): Promise<string> {
  const id = jobId || `task-${uuidv4()}`;
  const name = scheduler.jobPath(projectId, location, id);

  const date = new Date(dateTime);

  const minutes = date.getUTCMinutes();
  const hours = date.getUTCHours();
  const dayOfMonth = date.getUTCDate();
  const month = date.getUTCMonth() + 1; // JavaScript months are 0-indexed
  const dayOfWeek = date.getUTCDay();

  const schedule = `${minutes} ${hours} ${dayOfMonth} ${month} ${dayOfWeek}`;

  const httpTarget: protos.google.cloud.scheduler.v1.IHttpTarget = {
    uri: taskConfig.targetUrl,
    httpMethod: protos.google.cloud.scheduler.v1.HttpMethod.POST,
    headers: {
      'Content-Type': 'application/json',
    },
    body: Buffer.from(JSON.stringify(taskConfig.payload)).toString('base64'),
  };

  if (taskConfig.authToken) {
    httpTarget.headers!['Authorization'] = `Bearer ${taskConfig.authToken}`;
  }

  const job: protos.google.cloud.scheduler.v1.IJob = {
    name,
    schedule,
    timeZone: 'UTC',
    httpTarget,
    attemptDeadline: { seconds: 180 },
  };

  try {
    const [response] = await scheduler.createJob({ parent, job });
    console.log(`Job created: ${response.name}`);
    return response.name!;
  } catch (error) {
    console.error('Error creating Cloud Scheduler job:', error);
    throw error;
  }
}

export async function cancelTask(jobName: string): Promise<boolean> {
  try {
    await scheduler.deleteJob({ name: jobName });
    console.log(`Job cancelled: ${jobName}`);
    return true;
  } catch (error) {
    console.error('Error cancelling job:', error);
    return false;
  }
}

export async function listJobs(): Promise<protos.google.cloud.scheduler.v1.IJob[]> {
  try {
    const [jobs] = await scheduler.listJobs({ parent });
    return jobs;
  } catch (error) {
    console.error('Error listing jobs:', error);
    throw error;
  }
}
