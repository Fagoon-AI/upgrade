/* eslint-disable @typescript-eslint/no-explicit-any */
import axios from 'axios';
import { api_base_url, NodeExecutor } from "./execution";

export const languageExecutors: Record<string, NodeExecutor> = {

  'nano-banana-pro-preview': async (input, settings, user_id) => {
    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    let processedInput = input;
    if (!input && settingsObj.defaultValue) {
      processedInput = settingsObj.defaultValue;
    }
    if (settingsObj.promptTemplate && processedInput) {
      processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
    }
    let finalPrompt = (input.prompt || '') + " ";
    if(input.systemPrompt){
      finalPrompt += input.systemPrompt;
    }
    if(input.context){
      finalPrompt += input.context;
    }
    const response = await axios.post(`${api_base_url}/chat`, {
      "llm_config": {
        "model": "nano-banana-pro-preview",
        "provider":"google",
      },
      "user_prompt": finalPrompt,
    }); 
    return {
      success: true,
      data: response.data.data.result || response.data.data.response,
    };
  },

  'gemini-3.1-pro-preview': async (input, settings, user_id) => {
    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    let processedInput = input;
    if (!input && settingsObj.defaultValue) {
      processedInput = settingsObj.defaultValue;
    }
    if (settingsObj.promptTemplate && processedInput) {
      processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
    }
    let finalPrompt = (input.prompt || '') + " ";
    if(input.systemPrompt){
      finalPrompt += input.systemPrompt;
    }
    if(input.context){
      finalPrompt += input.context;
    }
    const response = await axios.post(`${api_base_url}/chat`, {
      "llm_config": {
        "model": "gemini-3.1-pro-preview",
        "provider":"google",
      },
      "user_prompt": finalPrompt,
    }); 
    return {
      success: true,
      data: response.data.data.result || response.data.data.response,
    };
  },
     'gpt-4': async (input, settings, user_id) => {

    console.log("gpt-4 input check:: ",input);
    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("gpt-4 update settings check:: ",settingsObj);
    // console.log("gpt-4 input check:: ",input);

        // Handle user input based on settings
        let processedInput = input;
      console.log("gpt-4 processedInput check:: ",processedInput);
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
        let finalPrompt = input.prompt + " ";
        if(input.systemPrompt){
          finalPrompt += input.systemPrompt;
        }
        if(input.context){
          finalPrompt += input.context;
        }
        console.log("gpt-4 finalPrompt check:: ", finalPrompt);
    const response = await axios.post(`${api_base_url}/chat`, {
      "llm_config": {
        "max_tokens": settings.maxTokens || 1024,
        "model": settings.modelName || "gpt-4o",
        "provider":"openai",
        "temperature": settings.temperature || 0.1,
        "top_p": 0.1,
      },
      "user_id": user_id,
      "user_prompt": finalPrompt,
    },{
      headers:{
        Authorization: `Bearer ${user_id}`
      }
    }); 
    return {
      success: true,
      data: response.data.data.result.replace(/[\n\t\r]+/g, ' ').replace(/\s+/g, ' ').trim(),
    };
  },

  'gpt-3.5-turbo': async (input, settings, user_id) => {

    console.log("gpt-3.5 turbo input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("gpt-3.5turbo update settings check:: ",settingsObj);
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
    const response = await axios.post(`${api_base_url}/chat`, {
      "user_prompt": finalPrompt,
      "user_type": "pro",
      "llm_config": {
        "model_type": "openai",
        "stream": false,
        "temperature": settings.temperature || 0.1,
        "max_token": settings.maxTokens || 0,
        "model_name": settings.modelName || "gpt-3.5-turbo",
      }
    },{
      headers:{
        Authorization: `Bearer ${user_id}`
      }
    });
    
    return {
      success: true,
      data: response.data.data.response.replace(/[\n\t\r]+/g, ' ').replace(/\s+/g, ' ').trim(),
    };
  },



  'vertex-ai': async (input, settings, user_id) => {
    console.log("vertex-ai input check:: ", input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    let processedInput = input;
    if (!input && settingsObj.defaultValue) {
      processedInput = settingsObj.defaultValue;
    }
    
    if (settingsObj.promptTemplate && processedInput) {
      processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
    }

    let finalPrompt = (input.prompt || "") + " ";
    if(input.context){
      finalPrompt += input.context;
    }
    if(input.systemPrompt){
      finalPrompt += input.systemPrompt;
    }

    try {
      const fetch = require('node-fetch');
      const vertex_ai = new VertexAI({project: 'openclaw-gateway-491419', location: 'us-central1'});
      const model = settings.modelName || 'gemini-1.5-pro-preview-0409';
      
      const generativeModel = vertex_ai.preview.getGenerativeModel({
        model: model,
        generationConfig: {
          maxOutputTokens: settings.maxTokens || 1024,
          temperature: settings.temperature || 0.1,
          topP: 0.1,
        },
      });

      const request = {
        contents: [{role: 'user', parts: [{text: finalPrompt}]}],
      };
      const streamingResp = await generativeModel.generateContentStream(request);
      const response = await streamingResp.response;
      const resultText = response.candidates[0].content.parts[0].text;

      return {
        success: true,
        data: resultText.replace(/[\n\t\r]+/g, ' ').replace(/\s+/g, ' ').trim(),
      };
    } catch (error: any) {
      return {
        success: false,
        error: error.message
      }
    }
  },
  "claude-3-turbo": async (input, settings, user_id) => {

    // console.log("claude-3 turbo input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("claude-3 update settings check:: ",settingsObj);
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
        const response = await axios.post(`${api_base_url}/chat`, {
      "llm_config": {
        "max_tokens": 1024,
        "model": settings.modelName || "claude-3-5-sonnet-latest",
        "provider":"anthropic",
        "temperature": settings.temperature || 0.1,
        "top_p": 0.1,
      },
      "user_id": user_id,
      "user_prompt": finalPrompt,
    },{
      headers:{
        Authorization: `Bearer ${user_id}`
      }
    });  
    
    return {
      success: true,
      data: response.data.data.result.replace(/[\n\t\r]+/g, ' ').replace(/\s+/g, ' ').trim(),
    };
  },

  'llama-3': async (input, settings,user_id) => {

    console.log("llama-3 turbo input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("llama-3 update settings check:: ",settingsObj);
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
    const response = await axios.post(`${api_base_url}/chat`, {
      "user_prompt": finalPrompt,
      "user_type": "pro",
      "llm_config": {
        "model_type": "groq",
        "stream": false,
        "temperature": settings.temperature || 0.1,
        "max_token": settings.maxTokens || 0,
        "model_name": settings.modelName || "llama3-70b-8192",
      }
    },{
      headers:{
        Authorization: `Bearer ${user_id}`
      }
    });
    
    return {
      success: true,
      data: response.data.data.response.replace(/[\n\t\r]+/g, ' ').replace(/\s+/g, ' ').trim(),
    };
  },

  'web-search': async (input, settings,user_id) => {

    console.log("llama-3 turbo input check:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("llama-3 update settings check:: ",settingsObj);
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
        try {
          new URL(input.url);
        } catch {
          return {
            success: false,
            data: 'Input Should be a valid url'
          }
        }
    const response = await axios.post(`${api_base_url}/fetch`, {
      "urls": [input.url],
    },{
      headers:{
        Authorization: `Bearer ${user_id}`
      }
    });
    return {
      success: true,
      data: response.data.data.content[0].data.content,
    };
  },
}