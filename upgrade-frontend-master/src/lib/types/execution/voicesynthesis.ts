/* eslint-disable @typescript-eslint/no-explicit-any */
import axios from '@/lib/api/axios';
import { NodeExecutor } from "./execution";

export const voicesynthesisExecutors: Record<string, NodeExecutor> = {
 'openai-tts': async (input, settings, user_id) => {

    console.log("openai-tts turbo input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("openai-tts update settings check:: ",settingsObj);
    // console.log("gpt-4 input check:: ",input);

        // Handle user input based on settings
        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
        let finalPrompt = input.prompt + " ";
        if(input.context){
          finalPrompt += input.context;
        }
        if(input.systemPrompt){
          finalPrompt += input.systemPrompt;
        }
    
    // const response = await axios.post('https://saugatregmi.ekrasunya.com/api/v1/tts', {
    const response = await axios.post('/api/v1/tts', {
      "user_prompt": input.text,
      "user_type": "pro",
      "user_id":user_id,
      "tts_config": {
        "model_type": "openai",
        "stream": false,
        "temperature": settings.temperature || 0.1,
        "max_token": settings.maxTokens || 0,
        "model_name": settings.modelName || "tts-1",
      }
    });
    return {
      success: true,
      data: response.data.file_path,
    };
  },
   'fagoon-tts': async (input, settings, user_id) => {

    console.log("fagoons-tts turbo input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("openai-tts update settings check:: ",settingsObj);
    // console.log("gpt-4 input check:: ",input);

        // Handle user input based on settings
        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
        let finalPrompt = input.prompt + " ";
        if(input.context){
          finalPrompt += input.context;
        }
        if(input.systemPrompt){
          finalPrompt += input.systemPrompt;
        }
    
    // const response = await axios.post('https://saugatregmi.ekrasunya.com/api/v1/tts', {
    const response = await axios.post('/api/v1/tts', {
      "user_prompt": input.text,
      "user_type": "pro",
      "user_id":user_id,
      "tts_config": {
        "model_type": "kokoro",
        "stream": false,
        "temperature": settings.temperature || 0.1,
        "max_token": settings.maxTokens || 0,
        "model_name": settings.modelName || "tts-1",
      }
    });
    return {
      success: true,
      data: response.data.file_path,
    };
  },
}