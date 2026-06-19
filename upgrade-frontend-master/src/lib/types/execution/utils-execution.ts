/* eslint-disable @typescript-eslint/no-explicit-any */
import axios, { AxiosRequestConfig } from "axios";
import { NodeExecutor } from "./execution";

export const utilsExecutors: Record<string, NodeExecutor> = {
    'bg-remover': async (input, settings, user_id) => {

    console.log("bg-remover:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("reply email settings",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.post(`/api/v1/tool/bg-remover`,{
      file: input.file
    });
    return {
      success: true,
        data:response.data.message,
    };
  },
}