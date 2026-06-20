
/* eslint-disable @typescript-eslint/no-explicit-any */
import axios from '@/lib/api/axios';
import { NodeExecutor } from "./execution";

export const imagegenExecutors: Record<string, NodeExecutor> = {

  'veo-3.0-generate-001': async (input, settings, user_id) => {
    const response = await axios.post(`/api/v1/video-generation/videos?user_id=${user_id}`, {
      "text": input.prompt,
      "enhance_prompt": false
    });
    return {
      success: true,
      data: response.data.data,
    };
  },

  'dalle-3': async (input, settings, user_id) => {

    console.log("dalle-3 input check:: ",input);
    
    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("dalle-3 update settings check:: ",settingsObj);

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
        //TODO: This is a temporary fix, we need to remove the context from the input
    const response = await axios.post('/api/v1/generate-image', {
    // const response = await axios.post('https://saugatregmi.ekrasunya.com/api/v1/generate-image', {
      "prompt": input.prompt,
      "user_id":user_id,
      "diffusion_model_config": {
      // "api_key": "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",
      "provider": "openai",
      "model": "dall-e-3"
  }
    }
  );
    return {
      success: true,
      data:response.data.data.file_path,
    };
  },



  
  'stable-diffusion-xl': async (input, settings, user_id) => {

    console.log("stable-diffusion input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("stable-diffusion update settings check:: ",settingsObj);
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
        //TODO: This is a temporary fix, we need to remove the context from the input
    const response = await axios.post('/api/v1/generate-image', {
      "user_prompt": input.prompt,
      "user_type": "pro",
      "user_id": user_id,
      "diffusion_model_config": {
      // "api_key": "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",
      "model_type": "hugging_face",
      "model_name": "stabilityai/stable-diffusion-xl-base-1.0"
  }
    },
  );

    return {
      success: true,
        data:response.data.file_path,
    };
  },
 'video-gen': async (input, settings, user_id) => {
    // The log output shows that settings is an array of configuration objects
    // We need to convert it to an object with keys based on the 'id' property
    const settingsObj = Array.isArray(settings) 
      ? settings.reduce((acc, setting) => {
          acc[setting.id] = setting.default || '';
          return acc;
        }, {} as Record<string, any>)
      : settings;

      console.log("video-gen update settings check:: ",settingsObj);
      await new Promise(resolve => setTimeout(resolve, 2000));
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
    const response = await axios.post(`/api/v1/video-generation/videos?user_id=${user_id}`, {
      "text": input.prompt,
      "enhance_prompt":false
  
    },
  );
    // Return processed input as a prompt
    return {
      success: true,
      data: 'Video Generation Started, Please Check the workflow logs for output',
    };
  },

}